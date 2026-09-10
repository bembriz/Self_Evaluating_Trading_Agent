"""Reconciliación contable Decimal espejo del Paper Engine (16c.6 / Task 4 + 8c F2).

Reconstruye el estado contable del paper engine a partir ÚNICAMENTE de los
eventos persistidos (`PaperTradeEvent`) y del capital inicial; la reconstrucción
full (todos los eventos) y la reconstrucción incremental (checkpoint previo +
`events_since` por cursor) deben coincidir bit a bit entre sí y con la equity
contable persistida (la del último evento, `book_equity`) con aritmética Decimal
exacta: PASS sólo si `residual == 0`.

La matemática replicada es la del engine real:

- `src/application/services/paper_engine.py`
    - `_open_position` (251-270): `exec_price = price*(1+rate)`,
      `notional = quantity*exec_price`, `fee = fee_model.fee(notional)`,
      y delega en `Portfolio.apply_buy`.
    - `_make_fill` (282-300): BUY `exec_price = price*(1+rate)`,
      SELL `exec_price = price*(1-rate)`; `notional = quantity*exec_price`.
    - `_close_position` (227-240): vende TODA la posición y delega en
      `Portfolio.apply_sell`.
    - La equity persistida por evento es
      `portfolio.equity(close) = cash + position*close` calculada DESPUÉS de
      procesar la vela (ver `paper_runner._process`, paper_runner.py:478).
- `src/domain/portfolio/portfolio.py`
    - `apply_buy` (42-61): si `position == 0` => `avg_entry = exec_price`; si no,
      `avg_entry = (avg_entry*position + exec_price*quantity)/(position+quantity)`
      (siempre con la posición ANTERIOR al fill). Luego
      `position += quantity` y `cash -= notional + fee`. `total_fees += fee`.
    - `apply_sell` (63-104): `quantity = min(fill.quantity, position)`,
      `fraction = quantity/position`, `scale = quantity/fill.quantity`,
      `exit_fee = fee*scale`, `cash += notional*scale - exit_fee`,
      `position -= quantity`, `realized_pnl += gross_pnl - fees`,
      donde `gross_pnl = (exec_price - avg_entry)*quantity` y
      `fees = allocated_entry_fees + exit_fee`. Si `position <= 1e-12` se
      normaliza a `0.0` y `avg_entry = None`.
    - `equity` (106-107): `cash + position*price`.

Orden exacto replicado (paso a paso, operando a operando):
    BUY : cash -= quantity*exec_price + fee          (cash = cash - (notional + fee))
    SELL: cash += (quantity*exec_price)*scale - exit_fee
    realizado += (exec_price - avg_entry)*quantity - (alloc_entry_fees + exit_fee)

Semántica de costes:
- `exec_price` embebe slippage: el flujo de caja del fill usa `exec_price` y NUNCA
  resta `slippage_cost` aparte (portfolio.py:77-79). `slippage_cost` se ignora en
  la reconstrucción (sólo es métrica analítica).
- `fee` se deduce una sola vez por fill.
- Promedio por lotes: `apply_buy` ponderado por posición previa; `apply_sell`
  reduce posición y asigna fees de entrada por `fraction`.

POR QUÉ ESTA IMPLEMENTACIÓN ES FLOAT-INTERNA (y por qué es lo correcto):
el engine contabiliza en float64 IEEE-754 redondeando en CADA operación. La
replicación Decimal exacta operación a operación NO reproduce ese redondeo
binsario (Decimal es aritmética decimal exacta, sin redondeo a 53 bits), así que
un espejo 100% Decimal deja un residual de ~1e-12 incluso con eventos idénticos.
Para que `residual == 0` sea EXACTO (requisito), este módulo replica la cadena
float del engine (mismos operandos persistidos, mismo orden de operaciones) y
convierte cada resultado a Decimal con `Decimal(str(...))` en la frontera del
ledger. Como los mismos operandos float y el mismo orden producen los mismos bits
que el engine, `Decimal(str(reconstruida)) == Decimal(str(persistida))` y el
residual es exactamente cero, sin tolerancias ni ceros artificiales. La conversión
`float(Decimal(str(f)))` es lossless (str(float) round-trip), por lo que el
incremental puede reanudar desde un checkpoint serializado bit a bit.

Con posición abierta la reconstrucción marca a mercado con `mark_price` = close de
la última vela persistida (`latest_persisted_mark`); si hay posición abierta y no
hay mark persistido se eleva `MissingMarkError` (el productor lo traduce a un
check de fallo, nunca a crash).

Reconciliación three-way con checkpoint (16c.6 / Task 8c F2):
    current live book (equity del último evento persistido)
        ==
    full reconstruction (TODOS los eventos persistidos)
        ==
    incremental reconstruction (checkpoint previo + events_since por cursor)

El checkpoint (`BookState` persistido en ``accounting_book``) guarda el estado
contable al cierre del cursor (`last_event_ms`) más el estado interno del mirror
necesario para reanudar (`entry_fees`); SOLO avanza en PASS. El cursor convierte
la corrupción en algo detectable: un evento viejo (ts <= cursor) corrompido o
borrado lo rejuega full pero NO incremental (que parte del checkpoint ya
validado) ⇒ full != incremental ⇒ FAIL por componentes. Un evento nuevo (ts >
cursor) corrompido lo rejuegan full e incremental por igual, pero su equity
reconstruida diverge de la equity live persistida por el engine ⇒ FAIL.

Semántica fail-closed del checkpoint ausente/ilegible (16c.6 / Task 8c F2): un
checkpoint previo GENUINAMENTE AUSENTE (``None``: primer ancla / sesión nueva) o
sin cursor usable (serialización pre-8c, ``last_event_ms`` ausente) ⇒ baseline
PASS con checkpoint = mirror completo + cursor (re-base documentado: nada fue
desplegado, no hay migración real). Un checkpoint PRESENTE pero ILEGIBLE
(``BookState.from_dict`` -> None: falta una clave esencial / valor no
parseable) NO es baseline end-to-end: ``from_dict`` lo SUPERA como ``None`` y el
caller (productor) — que conserva el mapping crudo — valida presencia +
parseabilidad y hace FAIL-closed (``accounting_status = "FAIL"``, reason
``"unparseable_accounting_book"``, critical_error) antes de confiar en ningún
PASS. Este módulo devuelve baseline para ilegible sólo como carveout del kernel;
esa vía sólo es segura bajo el gate fail-closed del productor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from operator import attrgetter
from typing import Any

from application.ports.paper_trading import PaperTradeEvent
from domain.market.candle import Candle


class MissingMarkError(Exception):
    """Posición abierta sin mark de mercado persistido para marcar a mercado."""


@dataclass(frozen=True, slots=True)
class AccountingLedger:
    """Estado contable reconstruido, con los valores del engine en Decimal."""

    cash: Decimal
    position_qty: Decimal
    average_entry: Decimal
    realized_pnl: Decimal
    fees: Decimal
    reconstructed_equity: Decimal


def _d(value: float) -> Decimal:
    """Convierte un float persistido a Decimal vía su representación exacta str()."""
    return Decimal(str(value))


def latest_persisted_mark(candles: Sequence[Candle]) -> float | None:
    """Close de la última vela persistida (evidencia de mercado); None si vacío."""
    if not candles:
        return None
    return candles[-1].close


# ---------------------------------------------------------------------------
# Kernel espejo del engine: estado float + avance por eventos ordenados
# ---------------------------------------------------------------------------

# Estado interno del mirror: cash, position, avg_entry, entry_fees,
# entry_slippage, realized_pnl, total_fees, total_slippage. entry_fees/entry_
# slippage son el estado acumulado que Portfolio necesita para repartir costes de
# entrada en un SELL (portfolio.py:66-67); entry_slippage no afecta a cash/pnl.
_MirrorState = tuple[
    float,
    float,
    float | None,
    float,
    float,
    float,
    float,
    float,
]


def _mirror_start(cash: float) -> _MirrorState:
    return (cash, 0.0, None, 0.0, 0.0, 0.0, 0.0, 0.0)


def _advance(state: _MirrorState, ordered_events: Sequence[PaperTradeEvent]) -> _MirrorState:
    """Replica el bucle del engine sobre `ordered_events` (ya ordenados por ts).

    Sólo los eventos con fill (`filled` y `exec_price`/`quantity`) y acción
    BUY/SELL mutan el estado; el resto (HOLD/rechazos) no toca la caja. El orden
    de operaciones float es el mismo que el de `reconcile_accounting`/el engine.
    """
    (
        cash,
        position,
        avg_entry,
        entry_fees,
        entry_slippage,
        realized_pnl,
        total_fees,
        total_slippage,
    ) = state
    for event in ordered_events:
        if not event.filled or event.exec_price is None or event.quantity is None:
            continue
        if event.action == "BUY":
            cash, position, avg_entry, entry_fees, entry_slippage, total_fees, total_slippage = (
                _apply_buy(
                    cash=cash,
                    position=position,
                    avg_entry=avg_entry,
                    entry_fees=entry_fees,
                    entry_slippage=entry_slippage,
                    total_fees=total_fees,
                    total_slippage=total_slippage,
                    exec_price=event.exec_price,
                    quantity=event.quantity,
                    fee=event.fee,
                    slippage_cost=event.slippage_cost,
                )
            )
        elif event.action == "SELL":
            (
                cash,
                position,
                avg_entry,
                entry_fees,
                entry_slippage,
                realized_pnl,
                total_fees,
                total_slippage,
            ) = _apply_sell(
                cash=cash,
                position=position,
                avg_entry=avg_entry,
                entry_fees=entry_fees,
                entry_slippage=entry_slippage,
                realized_pnl=realized_pnl,
                total_fees=total_fees,
                total_slippage=total_slippage,
                exec_price=event.exec_price,
                quantity=event.quantity,
                fee=event.fee,
                slippage_cost=event.slippage_cost,
            )
    return (
        cash,
        position,
        avg_entry,
        entry_fees,
        entry_slippage,
        realized_pnl,
        total_fees,
        total_slippage,
    )


def _ledger_from_state(state: _MirrorState, *, mark_price: float | None) -> AccountingLedger:
    """Equity final (mark a mercado) + conversión Decimal en la frontera del ledger."""
    (
        cash,
        position,
        avg_entry,
        _entry_fees,
        _entry_slippage,
        realized_pnl,
        total_fees,
        _total_slippage,
    ) = state
    if position != 0.0 and mark_price is None:
        raise MissingMarkError(
            "posición abierta (qty="
            f"{position!r}) sin mark_price persistido; la equity no es auditable"
        )
    if position != 0.0 and mark_price is not None:
        reconstructed_equity = cash + position * mark_price
    else:
        reconstructed_equity = cash
    return AccountingLedger(
        cash=_d(cash),
        position_qty=_d(position),
        average_entry=_d(avg_entry) if avg_entry is not None else Decimal("0"),
        realized_pnl=_d(realized_pnl),
        fees=_d(total_fees),
        reconstructed_equity=_d(reconstructed_equity),
    )


def reconcile_accounting(
    events: Sequence[PaperTradeEvent],
    *,
    initial_capital: float,
    mark_price: float | None,
    interval_ms: int,
) -> AccountingLedger:
    """Reconstruye la contabilidad espejo del engine desde los eventos persistidos.

    Los eventos se procesan en orden `timestamp_ms` ascendente (verdad de
    ejecución). `interval_ms` es el paso de mercado (bucket de vela) usado por el
    productor para acotar la evidencia; no participa en la aritmética del engine.

    Los fields del ledger se obtienen convirtiendo el resultado float con
    `Decimal(str(...))`, bit-idéntico al valor persistido del engine cuando los
    operandos son los mismos.
    """
    ordered = sorted(events, key=attrgetter("timestamp_ms"))
    final = _advance(_mirror_start(initial_capital), ordered)
    return _ledger_from_state(final, mark_price=mark_price)


def _apply_buy(
    *,
    cash: float,
    position: float,
    avg_entry: float | None,
    entry_fees: float,
    entry_slippage: float,
    total_fees: float,
    total_slippage: float,
    exec_price: float,
    quantity: float,
    fee: float,
    slippage_cost: float,
) -> tuple[float, float, float | None, float, float, float, float]:
    """Espejo de `Portfolio.apply_buy` (portfolio.py:42-61)."""
    if quantity <= 0.0:
        return (cash, position, avg_entry, entry_fees, entry_slippage, total_fees, total_slippage)
    notional = quantity * exec_price
    total_cost = notional + fee
    if position == 0.0:
        new_avg: float | None = exec_price
    else:
        old_entry = avg_entry if avg_entry is not None else 0.0
        new_avg = (old_entry * position + exec_price * quantity) / (position + quantity)
    new_position = position + quantity
    new_cash = cash - total_cost
    return (
        new_cash,
        new_position,
        new_avg,
        entry_fees + fee,
        entry_slippage + slippage_cost,
        total_fees + fee,
        total_slippage + slippage_cost,
    )


def _apply_sell(
    *,
    cash: float,
    position: float,
    avg_entry: float | None,
    entry_fees: float,
    entry_slippage: float,
    realized_pnl: float,
    total_fees: float,
    total_slippage: float,
    exec_price: float,
    quantity: float,
    fee: float,
    slippage_cost: float,
) -> tuple[float, float, float | None, float, float, float, float, float]:
    """Espejo de `Portfolio.apply_sell` (portfolio.py:63-104)."""
    if quantity <= 0.0 or position <= 0.0:
        return (
            cash,
            position,
            avg_entry,
            entry_fees,
            entry_slippage,
            realized_pnl,
            total_fees,
            total_slippage,
        )
    sold = min(quantity, position)
    fraction = sold / position
    allocated_entry_fees = entry_fees * fraction
    allocated_entry_slippage = entry_slippage * fraction
    scale = sold / quantity if quantity > 0.0 else 0.0
    exit_fee = fee * scale
    exit_slippage = slippage_cost * scale
    base_entry = avg_entry if avg_entry is not None else 0.0
    gross_pnl = (exec_price - base_entry) * sold
    fees = allocated_entry_fees + exit_fee
    net_pnl = gross_pnl - fees
    notional = quantity * exec_price
    # Orden del engine (portfolio.py:81): `cash += fill.notional*scale - exit_fee`
    # evalúa primero `(notional*scale) - exit_fee` y LUEGO suma a cash. IEEE-754 no
    # es asociativo: `cash + (notional*scale - exit_fee)` ≠ `(cash + notional*scale)
    # - exit_fee` (1 ulp en ~23% de cierres completos). El paréntesis replica el
    # grouping real del engine bit a bit.
    new_cash = cash + (notional * scale - exit_fee)
    new_position = position - sold
    new_entry_fees = entry_fees - allocated_entry_fees
    new_entry_slippage = entry_slippage - allocated_entry_slippage
    new_realized = realized_pnl + net_pnl
    new_total_fees = total_fees + exit_fee
    new_total_slippage = total_slippage + exit_slippage
    if new_position <= 1e-12:
        new_position = 0.0
        new_avg: float | None = None
    else:
        new_avg = avg_entry
    return (
        new_cash,
        new_position,
        new_avg,
        new_entry_fees,
        new_entry_slippage,
        new_realized,
        new_total_fees,
        new_total_slippage,
    )


def residual(book_equity: float, ledger: AccountingLedger) -> Decimal:
    """Diferencia Decimal entre la equity contable persistida y la reconstruida.

    `residual == 0` (exacto) ⇔ la reconstrucción es bit-idéntica al libro.
    """
    return Decimal(str(book_equity)) - ledger.reconstructed_equity


@dataclass(frozen=True, slots=True)
class BookState:
    """Checkpoint contable persistible (16c.6 + 8c F2): estado + cursor del espejo.

    `average_entry` es `None` cuando no hay posición abierta. `entry_fees` es el
    estado interno del mirror que `Portfolio` necesita para repartir costes de
    entrada en un SELL posterior (resume bit-exacto del incremental). La
    serialización viaja como `str(Decimal)` (bit-exacta respecto al valor float
    persistido del engine); `last_event_ms` (cursor) viaja como int ms o null.
    `from_dict` es tolerante: devuelve `None` si falta una clave esencial o un
    valor no parsea (snapshots ilegibles/legacy parciales) — señal de que el
    caller (productor) debe FAIL-closed si la clave estaba PRESENTE — y un
    `BookState` con `last_event_ms=None` si la serialización parsea pero no trae
    cursor usable (libro pre-8c ⇒ re-baseline documentado: nunca desplegado, sin
    migración real). Nunca lanza.
    """

    cash: Decimal
    position_qty: Decimal
    average_entry: Decimal | None
    realized_pnl: Decimal
    fees: Decimal
    equity: Decimal
    entry_fees: Decimal = Decimal("0")
    last_event_ms: int | None = None

    _ESSENTIAL = frozenset({"cash", "position_qty", "realized_pnl", "fees", "equity"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": str(self.cash),
            "position_qty": str(self.position_qty),
            "average_entry": "" if self.average_entry is None else str(self.average_entry),
            "realized_pnl": str(self.realized_pnl),
            "fees": str(self.fees),
            "equity": str(self.equity),
            "entry_fees": str(self.entry_fees),
            "last_event_ms": self.last_event_ms,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BookState | None:
        if not cls._ESSENTIAL.issubset(data.keys()):
            return None
        try:
            avg_raw = data.get("average_entry")
            average_entry = Decimal(str(avg_raw)) if avg_raw not in (None, "") else None
            entry_raw = data.get("entry_fees")
            entry_fees = Decimal(str(entry_raw)) if entry_raw not in (None, "") else Decimal("0")
            return cls(
                cash=Decimal(str(data["cash"])),
                position_qty=Decimal(str(data["position_qty"])),
                average_entry=average_entry,
                realized_pnl=Decimal(str(data["realized_pnl"])),
                fees=Decimal(str(data["fees"])),
                equity=Decimal(str(data["equity"])),
                entry_fees=entry_fees,
                last_event_ms=_cursor_from_value(data.get("last_event_ms")),
            )
        except (ValueError, TypeError, ArithmeticError):
            return None


def _cursor_from_value(value: object) -> int | None:
    """Cursor desde un valor serializado; no-int/no-parseable ⇒ None (sin cursor)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Resultado de `reconcile_with_book`: veredicto + libro actual + residuos."""

    status: str
    ledger: AccountingLedger
    book: BookState
    mismatches: tuple[str, ...]
    accounting_residual: Decimal


def _book_from_ledger(
    ledger: AccountingLedger,
    *,
    entry_fees: float,
    last_event_ms: int | None,
) -> BookState:
    """Checkpoint persistible: componentes del ledger + estado interno + cursor."""
    return BookState(
        cash=ledger.cash,
        position_qty=ledger.position_qty,
        average_entry=None if ledger.position_qty == 0 else ledger.average_entry,
        realized_pnl=ledger.realized_pnl,
        fees=ledger.fees,
        equity=ledger.reconstructed_equity,
        entry_fees=_d(entry_fees),
        last_event_ms=last_event_ms,
    )


def _compare(
    mismatches: list[str],
    deltas: list[Decimal],
    name: str,
    expected: Decimal,
    actual: Decimal,
) -> None:
    delta = abs(expected - actual)
    deltas.append(delta)
    if delta != 0:
        mismatches.append(name)


def reconcile_with_book(
    events: Sequence[PaperTradeEvent],
    *,
    initial_capital: float,
    mark_price: float | None,
    previous_book: Mapping[str, Any] | None,
    interval_ms: int,
) -> ReconciliationResult:
    """Reconciliación three-way con checkpoint (16c.6 / Task 8c F2).

    Verifica, componente a componente (cash / position_qty / average_entry con
    posición abierta / realized_pnl / fees / equity) y sin tolerancias:

        live (equity del último evento persistido)
            == full (espejo sobre TODOS los eventos)
            == incremental (checkpoint previo + events_since por cursor)

    - `previous_book is None` (primer ancla / sesión nueva) ⇒ **baseline PASS**:
      no hay referencia previa, se acepta la reconstrucción full como nuevo
      checkpoint con cursor = `timestamp_ms` del último evento (carveout 16c.6).
      `previous_book` presente pero sin cursor usable (`last_event_ms is None`,
      serialización pre-8c) ⇒ mismo baseline re-base. Un `previous_book`
      PRESENTE pero ILEGIBLE (`BookState.from_dict` → `None`) también devuelve
      aquí baseline como carveout del kernel, pero el CALLER (productor) valida
      presencia + parseabilidad del mapping crudo y hace FAIL-closed
      (`unparseable_accounting_book`) — nunca un baseline silencioso end-to-end.
    - Con checkpoint usable: `events_since` = eventos con `timestamp_ms > cursor`;
      el incremental reanuda el mirror desde el estado del checkpoint (floats
      lossless vía `str`) y avanza con `events_since` por la MISMA aritmética
      espejo. `full` re-juega todos los eventos; `live` = equity del último
      evento. La posición abierta se marca a mercado con el MISMO `mark_price`
      en los tres caminos.
    - `mismatches` cubre (a) full vs incremental por componente (detecta
      corrupción/borrado de eventos viejos) y (b) la equity reconstruida
      (full/incremental, iguales entre sí) vs `live` (detecta corrupción de
      eventos nuevos y borrado del último). `accounting_residual` = máximo delta
      entre todos los caminos aplicables; PASS ⇔ 0.
    """
    ordered = sorted(events, key=attrgetter("timestamp_ms"))
    last_event_ms = ordered[-1].timestamp_ms if ordered else None
    full_final = _advance(_mirror_start(initial_capital), ordered)
    full_ledger = _ledger_from_state(full_final, mark_price=mark_price)
    full_entry_fees = full_final[3]

    reference = BookState.from_dict(previous_book) if previous_book is not None else None
    if reference is None or reference.last_event_ms is None:
        return ReconciliationResult(
            status="PASS",
            ledger=full_ledger,
            book=_book_from_ledger(
                full_ledger, entry_fees=full_entry_fees, last_event_ms=last_event_ms
            ),
            mismatches=(),
            accounting_residual=Decimal("0"),
        )

    events_since = [event for event in ordered if event.timestamp_ms > reference.last_event_ms]
    incremental_start = (
        float(reference.cash),
        float(reference.position_qty),
        float(reference.average_entry) if reference.average_entry is not None else None,
        float(reference.entry_fees),
        0.0,
        float(reference.realized_pnl),
        float(reference.fees),
        0.0,
    )
    incremental_final = _advance(incremental_start, events_since)
    incremental_ledger = _ledger_from_state(incremental_final, mark_price=mark_price)

    mismatches: list[str] = []
    deltas: list[Decimal] = []

    _compare(mismatches, deltas, "cash", full_ledger.cash, incremental_ledger.cash)
    _compare(
        mismatches,
        deltas,
        "position_qty",
        full_ledger.position_qty,
        incremental_ledger.position_qty,
    )
    if full_ledger.position_qty > 0 and incremental_ledger.position_qty > 0:
        _compare(
            mismatches,
            deltas,
            "average_entry",
            full_ledger.average_entry,
            incremental_ledger.average_entry,
        )
    _compare(
        mismatches,
        deltas,
        "realized_pnl",
        full_ledger.realized_pnl,
        incremental_ledger.realized_pnl,
    )
    _compare(mismatches, deltas, "fees", full_ledger.fees, incremental_ledger.fees)
    _compare(
        mismatches,
        deltas,
        "equity",
        full_ledger.reconstructed_equity,
        incremental_ledger.reconstructed_equity,
    )
    if ordered:
        live_equity = Decimal(str(ordered[-1].equity))
        _compare(mismatches, deltas, "equity", full_ledger.reconstructed_equity, live_equity)

    book = _book_from_ledger(full_ledger, entry_fees=full_entry_fees, last_event_ms=last_event_ms)
    if mismatches:
        return ReconciliationResult(
            status="FAIL",
            ledger=full_ledger,
            book=book,
            mismatches=tuple(mismatches),
            accounting_residual=max(deltas),
        )
    return ReconciliationResult(
        status="PASS",
        ledger=full_ledger,
        book=book,
        mismatches=(),
        accounting_residual=Decimal("0"),
    )
