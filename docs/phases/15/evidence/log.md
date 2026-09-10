- `2026-08-24T09:00:30-06:00` **release-check** → `python3 harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check.log
- `2026-08-24T09:00:33-06:00` **pip-audit** → `uv run pip-audit --desc off` · exit=`0` · artifact: docs/phases/15/evidence/pip-audit.log
- `2026-08-24T09:03:02-06:00` **lint** → `uv run ruff check .` · exit=`0` · artifact: docs/phases/15/evidence/lint.log
- `2026-08-24T09:03:02-06:00` **format-check** → `uv run ruff format --check .` · exit=`0` · artifact: docs/phases/15/evidence/format-check.log
- `2026-08-24T09:03:03-06:00` **mypy** → `uv run mypy src tests` · exit=`0` · artifact: docs/phases/15/evidence/mypy.log
- `2026-08-26T00:02:35-06:00` **dataset-verify** → `uv run python -m main verify` · exit=`0` · artifact: docs/phases/15/evidence/dataset-verify.log
- `2026-08-26T00:02:48-06:00` **backtest-official-run1** → `uv run python -m main backtest --output docs/phases/15/evidence/backtest_run1.json` · exit=`0` · artifact: docs/phases/15/evidence/backtest-official-run1.log
- `2026-08-26T00:02:59-06:00` **backtest-official-run2** → `uv run python -m main backtest --output docs/phases/15/evidence/backtest_run2.json` · exit=`0` · artifact: docs/phases/15/evidence/backtest-official-run2.log
- `2026-08-26T00:02:59-06:00` **backtest-determinism-diff** → `bash -c diff docs/phases/15/evidence/backtest_run1.json docs/phases/15/evidence/backtest_run2.json && echo DETERMINISTIC_OK` · exit=`0` · artifact: docs/phases/15/evidence/backtest-determinism-diff.log
- `2026-08-26T00:05:21-06:00` **release-check** → `uv run python harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check.log
- `2026-08-26T00:17:09-06:00` **replay-official-run1** → `uv run python -m main replay --output docs/phases/15/evidence/replay_run1.jsonl` · exit=`0` · artifact: docs/phases/15/evidence/replay-official-run1.log
- `2026-08-26T00:17:17-06:00` **replay-official-run2** → `uv run python -m main replay --output docs/phases/15/evidence/replay_run2.jsonl` · exit=`0` · artifact: docs/phases/15/evidence/replay-official-run2.log
- `2026-08-26T00:17:17-06:00` **replay-determinism-diff** → `bash -c diff docs/phases/15/evidence/replay_run1.jsonl docs/phases/15/evidence/replay_run2.jsonl && echo DETERMINISTIC_OK` · exit=`0` · artifact: docs/phases/15/evidence/replay-determinism-diff.log
- `2026-08-26T00:19:51-06:00` **release-check** → `uv run python harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check.log
- `2026-08-26T00:24:20-06:00` **release-check** → `uv run python harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check.log
- `2026-08-26T00:27:38-06:00` **release-check** → `uv run python harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check.log
- `2026-08-26T00:40:32-06:00` **paper-session-run1** → `uv run python -m main paper-session --output docs/phases/15/evidence/paper_session_run1.json` · exit=`0` · artifact: docs/phases/15/evidence/paper-session-run1.log
- `2026-08-26T00:40:41-06:00` **paper-session-run2** → `uv run python -m main paper-session --output docs/phases/15/evidence/paper_session_run2.json` · exit=`0` · artifact: docs/phases/15/evidence/paper-session-run2.log
- `2026-08-26T00:40:41-06:00` **paper-session-determinism-diff** → `bash -c diff docs/phases/15/evidence/paper_session_run1.json docs/phases/15/evidence/paper_session_run2.json && echo DETERMINISTIC_OK` · exit=`0` · artifact: docs/phases/15/evidence/paper-session-determinism-diff.log
- `2026-08-26T00:43:02-06:00` **release-check** → `uv run python harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check.log
- `2026-08-31T23:15:13-06:00` **bybit-testnet-lifecycle** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os
import time

from domain.trading.order import OrderRequest
from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import BybitTradeClient

SYMBOL = "ETHUSDT"
ORDER_LINK_ID = f"seta-lrc15-{int(time.time())}"

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    client = BybitTradeClient(
        signer=BybitSigner(api_key=api_key, api_secret=api_secret),
        base_url="https://api-testnet.bybit.com",
        timeout=10.0,
    )
    placed = False
    try:
        before = await client.open_orders(SYMBOL)
        print(f"testnet_open_orders_before={len(before)}")
        req = OrderRequest(
            symbol=SYMBOL,
            side="Buy",
            quantity=5.0,
            order_type="Limit",
            price=1.0,
            order_link_id=ORDER_LINK_ID,
        )
        order = await client.place_order(req)
        placed = True
        print("testnet_place_order=PASS")
        print(f"order_link_id={order.order_link_id}")
        print(f"exchange_order_id_present={bool(order.exchange_order_id)}")

        open_orders = await client.open_orders(SYMBOL)
        matched = [o for o in open_orders if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_reconcile_open_order={bool(matched)}")
        if not matched:
            raise SystemExit("placed order was not visible in open orders")

        cancelled = await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
        print(f"testnet_cancel_order={cancelled}")
        if not cancelled:
            raise SystemExit("cancel_order returned false for newly placed order")

        after = await client.open_orders(SYMBOL)
        still_open = [o for o in after if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_order_still_open_after_cancel={bool(still_open)}")
        if still_open:
            raise SystemExit("order remained open after cancel")
        print("TESTNET_LIFECYCLE=PASS")
    finally:
        if placed:
            try:
                await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
            except Exception as exc:  # best-effort cleanup, do not expose internals/secrets
                print(f"cleanup_cancel_result=ignored:{exc.__class__.__name__}")
        await client.close()

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-lifecycle.log
- `2026-08-31T23:16:57-06:00` **bybit-testnet-lifecycle-fixed** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os
import time

from domain.trading.order import OrderRequest
from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import BybitTradeClient

SYMBOL = "ETHUSDT"
ORDER_LINK_ID = f"seta-lrc15-{int(time.time())}"

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    client = BybitTradeClient(
        signer=BybitSigner(api_key=api_key, api_secret=api_secret),
        base_url="https://api-testnet.bybit.com",
        timeout=10.0,
    )
    placed = False
    try:
        before = await client.open_orders(SYMBOL)
        print(f"testnet_open_orders_before={len(before)}")
        req = OrderRequest(
            symbol=SYMBOL,
            side="Buy",
            quantity=5.0,
            order_type="Limit",
            price=1.0,
            order_link_id=ORDER_LINK_ID,
        )
        order = await client.place_order(req)
        placed = True
        print("testnet_place_order=PASS")
        print(f"order_link_id={order.order_link_id}")
        print(f"exchange_order_id_present={bool(order.exchange_order_id)}")

        open_orders = await client.open_orders(SYMBOL)
        matched = [o for o in open_orders if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_reconcile_open_order={bool(matched)}")
        if not matched:
            raise SystemExit("placed order was not visible in open orders")

        cancelled = await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
        print(f"testnet_cancel_order={cancelled}")
        if not cancelled:
            raise SystemExit("cancel_order returned false for newly placed order")

        after = await client.open_orders(SYMBOL)
        still_open = [o for o in after if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_order_still_open_after_cancel={bool(still_open)}")
        if still_open:
            raise SystemExit("order remained open after cancel")
        print("TESTNET_LIFECYCLE=PASS")
    finally:
        if placed:
            try:
                await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
            except Exception as exc:
                print(f"cleanup_cancel_result=ignored:{exc.__class__.__name__}")
        await client.close()

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-lifecycle-fixed.log
- `2026-08-31T23:17:26-06:00` **bybit-testnet-lifecycle-price25** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os
import time

from domain.trading.order import OrderRequest
from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import BybitTradeClient

SYMBOL = "ETHUSDT"
ORDER_LINK_ID = f"seta-lrc15-{int(time.time())}"

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    client = BybitTradeClient(
        signer=BybitSigner(api_key=api_key, api_secret=api_secret),
        base_url="https://api-testnet.bybit.com",
        timeout=10.0,
    )
    placed = False
    try:
        before = await client.open_orders(SYMBOL)
        print(f"testnet_open_orders_before={len(before)}")
        req = OrderRequest(
            symbol=SYMBOL,
            side="Buy",
            quantity=0.2,
            order_type="Limit",
            price=25.0,
            order_link_id=ORDER_LINK_ID,
        )
        order = await client.place_order(req)
        placed = True
        print("testnet_place_order=PASS")
        print(f"order_link_id={order.order_link_id}")
        print(f"exchange_order_id_present={bool(order.exchange_order_id)}")

        open_orders = await client.open_orders(SYMBOL)
        matched = [o for o in open_orders if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_reconcile_open_order={bool(matched)}")
        if not matched:
            raise SystemExit("placed order was not visible in open orders")

        cancelled = await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
        print(f"testnet_cancel_order={cancelled}")
        if not cancelled:
            raise SystemExit("cancel_order returned false for newly placed order")

        after = await client.open_orders(SYMBOL)
        still_open = [o for o in after if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_order_still_open_after_cancel={bool(still_open)}")
        if still_open:
            raise SystemExit("order remained open after cancel")
        print("TESTNET_LIFECYCLE=PASS")
    finally:
        if placed:
            try:
                await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
            except Exception as exc:
                print(f"cleanup_cancel_result=ignored:{exc.__class__.__name__}")
        await client.close()

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-lifecycle-price25.log
- `2026-08-31T23:17:54-06:00` **bybit-testnet-balance-check** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os

import httpx

from infrastructure.bybit.auth import BybitSigner

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    signer = BybitSigner(api_key=api_key, api_secret=api_secret)
    params = {"accountType": "UNIFIED", "coin": "USDT,ETH"}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    headers = signer.sign("/v5/account/wallet-balance", payload=query)
    async with httpx.AsyncClient(base_url="https://api-testnet.bybit.com", timeout=10.0) as client:
        response = await client.get("/v5/account/wallet-balance", params=params, headers=headers)
    raw = response.json()
    print(f"wallet_http_status={response.status_code}")
    print(f"wallet_ret_code={raw.get(retCode)}")
    print(f"wallet_ret_msg={raw.get(retMsg)}")
    if raw.get("retCode") != 0:
        raise SystemExit("wallet balance check failed")
    coins = []
    for account in raw.get("result", {}).get("list", []):
        if isinstance(account, dict):
            coins.extend(account.get("coin", []))
    seen = {str(c.get("coin")): c for c in coins if isinstance(c, dict)}
    for coin in ("USDT", "ETH"):
        item = seen.get(coin, {})
        try:
            balance = float(item.get("walletBalance", "0") or 0)
        except (TypeError, ValueError):
            balance = 0.0
        print(f"{coin}_wallet_balance_positive={balance > 0}")

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-balance-check.log
- `2026-08-31T23:18:19-06:00` **bybit-testnet-balance-check-fixed** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os

import httpx

from infrastructure.bybit.auth import BybitSigner

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    signer = BybitSigner(api_key=api_key, api_secret=api_secret)
    params = {"accountType": "UNIFIED", "coin": "USDT,ETH"}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    headers = signer.sign("/v5/account/wallet-balance", payload=query)
    async with httpx.AsyncClient(base_url="https://api-testnet.bybit.com", timeout=10.0) as client:
        response = await client.get("/v5/account/wallet-balance", params=params, headers=headers)
    raw = response.json()
    ret_code = raw.get("retCode")
    ret_msg = raw.get("retMsg")
    print(f"wallet_http_status={response.status_code}")
    print(f"wallet_ret_code={ret_code}")
    print(f"wallet_ret_msg={ret_msg}")
    if ret_code != 0:
        raise SystemExit("wallet balance check failed")
    coins = []
    for account in raw.get("result", {}).get("list", []):
        if isinstance(account, dict):
            coins.extend(account.get("coin", []))
    seen = {str(c.get("coin")): c for c in coins if isinstance(c, dict)}
    for coin in ("USDT", "ETH"):
        item = seen.get(coin, {})
        try:
            balance = float(item.get("walletBalance", "0") or 0)
        except (TypeError, ValueError):
            balance = 0.0
        print(f"{coin}_wallet_balance_positive={balance > 0}")

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-balance-check-fixed.log
- `2026-08-31T23:18:40-06:00` **bybit-testnet-balance-check-encoded** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os

import httpx

from infrastructure.bybit.auth import BybitSigner

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    signer = BybitSigner(api_key=api_key, api_secret=api_secret)
    params = {"accountType": "UNIFIED", "coin": "USDT,ETH"}
    query = str(httpx.QueryParams(params))
    headers = signer.sign("/v5/account/wallet-balance", payload=query)
    async with httpx.AsyncClient(base_url="https://api-testnet.bybit.com", timeout=10.0) as client:
        response = await client.get("/v5/account/wallet-balance", params=params, headers=headers)
    raw = response.json()
    ret_code = raw.get("retCode")
    ret_msg = raw.get("retMsg")
    print(f"wallet_http_status={response.status_code}")
    print(f"wallet_ret_code={ret_code}")
    print(f"wallet_ret_msg={ret_msg}")
    if ret_code != 0:
        raise SystemExit("wallet balance check failed")
    coins = []
    for account in raw.get("result", {}).get("list", []):
        if isinstance(account, dict):
            coins.extend(account.get("coin", []))
    seen = {str(c.get("coin")): c for c in coins if isinstance(c, dict)}
    for coin in ("USDT", "ETH"):
        item = seen.get(coin, {})
        try:
            balance = float(item.get("walletBalance", "0") or 0)
        except (TypeError, ValueError):
            balance = 0.0
        print(f"{coin}_wallet_balance_positive={balance > 0}")

asyncio.run(main())
PY` · exit=`0` · artifact: docs/phases/15/evidence/bybit-testnet-balance-check-encoded.log
- `2026-08-31T23:19:16-06:00` **bybit-signature-unit-tests** → `uv run pytest tests/test_bybit_trade_auth.py tests/test_bybit_trade_client.py -q` · exit=`0` · artifact: docs/phases/15/evidence/bybit-signature-unit-tests.log
- `2026-08-31T23:19:40-06:00` **bybit-signature-ruff** → `uv run ruff check src/infrastructure/bybit/auth.py tests/test_bybit_trade_auth.py` · exit=`1` · artifact: docs/phases/15/evidence/bybit-signature-ruff.log
- `2026-08-31T23:20:10-06:00` **bybit-signature-ruff-fixed** → `uv run ruff check src/infrastructure/bybit/auth.py tests/test_bybit_trade_auth.py` · exit=`0` · artifact: docs/phases/15/evidence/bybit-signature-ruff-fixed.log
- `2026-08-31T23:20:20-06:00` **bybit-signature-unit-tests-fixed** → `uv run pytest tests/test_bybit_trade_auth.py tests/test_bybit_trade_client.py -q` · exit=`0` · artifact: docs/phases/15/evidence/bybit-signature-unit-tests-fixed.log
- `2026-08-31T23:30:20-06:00` **bybit-testnet-lifecycle-funded** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os
import time

from domain.trading.order import OrderRequest
from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import BybitTradeClient

SYMBOL = "ETHUSDT"
ORDER_LINK_ID = f"seta-lrc15-{int(time.time())}"

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    client = BybitTradeClient(
        signer=BybitSigner(api_key=api_key, api_secret=api_secret),
        base_url="https://api-testnet.bybit.com",
        timeout=10.0,
    )
    placed = False
    try:
        before = await client.open_orders(SYMBOL)
        print(f"testnet_open_orders_before={len(before)}")
        req = OrderRequest(
            symbol=SYMBOL,
            side="Buy",
            quantity=0.2,
            order_type="Limit",
            price=25.0,
            order_link_id=ORDER_LINK_ID,
        )
        order = await client.place_order(req)
        placed = True
        print("testnet_place_order=PASS")
        print(f"order_link_id={order.order_link_id}")
        print(f"exchange_order_id_present={bool(order.exchange_order_id)}")

        open_orders = await client.open_orders(SYMBOL)
        matched = [o for o in open_orders if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_reconcile_open_order={bool(matched)}")
        if not matched:
            raise SystemExit("placed order was not visible in open orders")

        cancelled = await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
        print(f"testnet_cancel_order={cancelled}")
        if not cancelled:
            raise SystemExit("cancel_order returned false for newly placed order")

        after = await client.open_orders(SYMBOL)
        still_open = [o for o in after if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_order_still_open_after_cancel={bool(still_open)}")
        if still_open:
            raise SystemExit("order remained open after cancel")
        print("TESTNET_LIFECYCLE=PASS")
    finally:
        if placed:
            try:
                await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
            except Exception as exc:
                print(f"cleanup_cancel_result=ignored:{exc.__class__.__name__}")
        await client.close()

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-lifecycle-funded.log
- `2026-08-31T23:30:47-06:00` **bybit-testnet-account-balances** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os

import httpx

from infrastructure.bybit.auth import BybitSigner

ACCOUNT_TYPES = ("UNIFIED", "FUND", "SPOT")
COINS = ("USDT", "ETH")

async def signed_get(client: httpx.AsyncClient, signer: BybitSigner, path: str, params: dict[str, str]) -> dict[str, object]:
    query = str(httpx.QueryParams(params))
    headers = signer.sign(path, payload=query)
    response = await client.get(path, params=params, headers=headers)
    raw = response.json()
    print(f"{params.get(accountType)}_http_status={response.status_code}")
    print(f"{params.get(accountType)}_ret_code={raw.get(retCode)}")
    print(f"{params.get(accountType)}_ret_msg={raw.get(retMsg)}")
    return raw

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")
    signer = BybitSigner(api_key=api_key, api_secret=api_secret)
    async with httpx.AsyncClient(base_url="https://api-testnet.bybit.com", timeout=10.0) as client:
        for account_type in ACCOUNT_TYPES:
            raw = await signed_get(
                client,
                signer,
                "/v5/account/wallet-balance",
                {"accountType": account_type, "coin": ",".join(COINS)},
            )
            if raw.get("retCode") != 0:
                continue
            coins = []
            for account in raw.get("result", {}).get("list", []):
                if isinstance(account, dict):
                    coins.extend(account.get("coin", []))
            seen = {str(c.get("coin")): c for c in coins if isinstance(c, dict)}
            for coin in COINS:
                item = seen.get(coin, {})
                try:
                    balance = float(item.get("walletBalance", "0") or 0)
                except (TypeError, ValueError):
                    balance = 0.0
                print(f"{account_type}_{coin}_wallet_balance_positive={balance > 0}")

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-account-balances.log
- `2026-08-31T23:31:13-06:00` **bybit-testnet-account-balances-fixed** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os

import httpx

from infrastructure.bybit.auth import BybitSigner

ACCOUNT_TYPES = ("UNIFIED", "FUND", "SPOT")
COINS = ("USDT", "ETH")

async def signed_get(client: httpx.AsyncClient, signer: BybitSigner, path: str, params: dict[str, str]) -> dict[str, object]:
    account_type = params["accountType"]
    query = str(httpx.QueryParams(params))
    headers = signer.sign(path, payload=query)
    response = await client.get(path, params=params, headers=headers)
    raw = response.json()
    print(f"{account_type}_http_status={response.status_code}")
    print(f"{account_type}_ret_code={raw.get("retCode")}")
    print(f"{account_type}_ret_msg={raw.get("retMsg")}")
    return raw

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")
    signer = BybitSigner(api_key=api_key, api_secret=api_secret)
    async with httpx.AsyncClient(base_url="https://api-testnet.bybit.com", timeout=10.0) as client:
        for account_type in ACCOUNT_TYPES:
            raw = await signed_get(
                client,
                signer,
                "/v5/account/wallet-balance",
                {"accountType": account_type, "coin": ",".join(COINS)},
            )
            if raw.get("retCode") != 0:
                continue
            coins = []
            for account in raw.get("result", {}).get("list", []):
                if isinstance(account, dict):
                    coins.extend(account.get("coin", []))
            seen = {str(c.get("coin")): c for c in coins if isinstance(c, dict)}
            for coin in COINS:
                item = seen.get(coin, {})
                try:
                    balance = float(item.get("walletBalance", "0") or 0)
                except (TypeError, ValueError):
                    balance = 0.0
                print(f"{account_type}_{coin}_wallet_balance_positive={balance > 0}")

asyncio.run(main())
PY` · exit=`0` · artifact: docs/phases/15/evidence/bybit-testnet-account-balances-fixed.log
- `2026-08-31T23:33:05-06:00` **bybit-testnet-balance-recheck** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os

import httpx

from infrastructure.bybit.auth import BybitSigner

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")
    signer = BybitSigner(api_key=api_key, api_secret=api_secret)
    params = {"accountType": "UNIFIED", "coin": "USDT,ETH"}
    query = str(httpx.QueryParams(params))
    headers = signer.sign("/v5/account/wallet-balance", payload=query)
    async with httpx.AsyncClient(base_url="https://api-testnet.bybit.com", timeout=10.0) as client:
        response = await client.get("/v5/account/wallet-balance", params=params, headers=headers)
    raw = response.json()
    print(f"wallet_http_status={response.status_code}")
    print(f"wallet_ret_code={raw.get("retCode")}")
    print(f"wallet_ret_msg={raw.get("retMsg")}")
    if raw.get("retCode") != 0:
        raise SystemExit("wallet balance check failed")
    coins = []
    for account in raw.get("result", {}).get("list", []):
        if isinstance(account, dict):
            coins.extend(account.get("coin", []))
    seen = {str(c.get("coin")): c for c in coins if isinstance(c, dict)}
    has_positive = False
    for coin in ("USDT", "ETH"):
        item = seen.get(coin, {})
        try:
            balance = float(item.get("walletBalance", "0") or 0)
        except (TypeError, ValueError):
            balance = 0.0
        positive = balance > 0
        has_positive = has_positive or positive
        print(f"UNIFIED_{coin}_wallet_balance_positive={positive}")
    if not has_positive:
        raise SystemExit("UNIFIED wallet still has no positive USDT/ETH balance")

asyncio.run(main())
PY` · exit=`0` · artifact: docs/phases/15/evidence/bybit-testnet-balance-recheck.log
- `2026-08-31T23:33:26-06:00` **bybit-testnet-lifecycle-pass** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os
import time

from domain.trading.order import OrderRequest
from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import BybitTradeClient

SYMBOL = "ETHUSDT"
ORDER_LINK_ID = f"seta-lrc15-{int(time.time())}"

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    client = BybitTradeClient(
        signer=BybitSigner(api_key=api_key, api_secret=api_secret),
        base_url="https://api-testnet.bybit.com",
        timeout=10.0,
    )
    placed = False
    try:
        before = await client.open_orders(SYMBOL)
        print(f"testnet_open_orders_before={len(before)}")
        req = OrderRequest(
            symbol=SYMBOL,
            side="Buy",
            quantity=0.2,
            order_type="Limit",
            price=25.0,
            order_link_id=ORDER_LINK_ID,
        )
        order = await client.place_order(req)
        placed = True
        print("testnet_place_order=PASS")
        print(f"order_link_id={order.order_link_id}")
        print(f"exchange_order_id_present={bool(order.exchange_order_id)}")

        open_orders = await client.open_orders(SYMBOL)
        matched = [o for o in open_orders if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_reconcile_open_order={bool(matched)}")
        if not matched:
            raise SystemExit("placed order was not visible in open orders")

        cancelled = await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
        placed = False
        print(f"testnet_cancel_order={cancelled}")
        if not cancelled:
            raise SystemExit("cancel_order returned false for newly placed order")

        after = await client.open_orders(SYMBOL)
        still_open = [o for o in after if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_order_still_open_after_cancel={bool(still_open)}")
        if still_open:
            raise SystemExit("order remained open after cancel")
        print("TESTNET_LIFECYCLE=PASS")
    finally:
        if placed:
            try:
                await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
            except Exception as exc:
                print(f"cleanup_cancel_result=ignored:{exc.__class__.__name__}")
        await client.close()

asyncio.run(main())
PY` · exit=`1` · artifact: docs/phases/15/evidence/bybit-testnet-lifecycle-pass.log
- `2026-08-31T23:34:22-06:00` **bybit-testnet-cleanup-open-orders** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os

from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import BybitTradeClient

SYMBOL = "ETHUSDT"
PREFIX = "seta-lrc15-"

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")
    client = BybitTradeClient(signer=BybitSigner(api_key=api_key, api_secret=api_secret))
    try:
        orders = await client.open_orders(SYMBOL)
        ours = [o for o in orders if o.order_link_id.startswith(PREFIX)]
        print(f"testnet_open_orders_total={len(orders)}")
        print(f"testnet_lrc15_open_orders={len(ours)}")
        for order in ours:
            cancelled = await client.cancel_order(symbol=SYMBOL, order_link_id=order.order_link_id)
            print(f"cleanup_cancelled={order.order_link_id}:{cancelled}")
    finally:
        await client.close()

asyncio.run(main())
PY` · exit=`0` · artifact: docs/phases/15/evidence/bybit-testnet-cleanup-open-orders.log
- `2026-08-31T23:34:53-06:00` **bybit-testnet-lifecycle-pass-final** → `bash -lc set -a; . ./.envrc >/dev/null 2>&1; set +a; uv run python - <<'PY'
from __future__ import annotations

import asyncio
import os
import time

from domain.trading.order import OrderRequest
from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import BybitTradeClient

SYMBOL = "ETHUSDT"
ORDER_LINK_ID = f"seta-lrc15-{int(time.time())}"

async def main() -> None:
    api_key = os.environ.get("BYBIT_API_KEY", "")
    api_secret = os.environ.get("BYBIT_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit("missing BYBIT_API_KEY/BYBIT_API_SECRET in environment")

    client = BybitTradeClient(
        signer=BybitSigner(api_key=api_key, api_secret=api_secret),
        base_url="https://api-testnet.bybit.com",
        timeout=10.0,
    )
    placed = False
    try:
        before = await client.open_orders(SYMBOL)
        print(f"testnet_open_orders_before={len(before)}")
        req = OrderRequest(
            symbol=SYMBOL,
            side="Buy",
            quantity=0.2,
            order_type="Limit",
            price=25.0,
            order_link_id=ORDER_LINK_ID,
        )
        order = await client.place_order(req)
        placed = True
        print("testnet_place_order=PASS")
        print(f"order_link_id={order.order_link_id}")
        print(f"exchange_order_id_present={bool(order.exchange_order_id)}")

        open_orders = await client.open_orders(SYMBOL)
        matched = [o for o in open_orders if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_reconcile_open_order={bool(matched)}")
        if not matched:
            raise SystemExit("placed order was not visible in open orders")

        cancelled = await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
        placed = False
        print(f"testnet_cancel_order={cancelled}")
        if not cancelled:
            raise SystemExit("cancel_order returned false for newly placed order")

        after = await client.open_orders(SYMBOL)
        still_open = [o for o in after if o.order_link_id == ORDER_LINK_ID]
        print(f"testnet_order_still_open_after_cancel={bool(still_open)}")
        if still_open:
            raise SystemExit("order remained open after cancel")
        print("TESTNET_LIFECYCLE=PASS")
    finally:
        if placed:
            try:
                await client.cancel_order(symbol=SYMBOL, order_link_id=ORDER_LINK_ID)
            except Exception as exc:
                print(f"cleanup_cancel_result=ignored:{exc.__class__.__name__}")
        await client.close()

asyncio.run(main())
PY` · exit=`0` · artifact: docs/phases/15/evidence/bybit-testnet-lifecycle-pass-final.log
- `2026-08-31T23:36:11-06:00` **bybit-release-gate-tests** → `uv run pytest harness/tests/test_release_check.py tests/test_bybit_trade_client.py tests/test_bybit_trade_auth.py -q` · exit=`0` · artifact: docs/phases/15/evidence/bybit-release-gate-tests.log
- `2026-08-31T23:37:37-06:00` **release-check-after-testnet** → `python3 harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check-after-testnet.log
- `2026-08-31T23:48:08-06:00` **release-check-after-uat** → `python3 harness/scripts/release_check.py` · exit=`0` · artifact: docs/phases/15/evidence/release-check-after-uat.log
