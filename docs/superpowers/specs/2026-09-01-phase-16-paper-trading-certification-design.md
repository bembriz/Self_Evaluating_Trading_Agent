# Phase 16 Paper Trading Certification Design

## Goal

Build the certification framework for Paper Trading Certification without faking time, trades, or market regimes.

## Scope

Phase 16 remains evidence-driven. The system may start and track a certification run now, but the phase gate can only pass after all PRD thresholds are satisfied by real paper-trading evidence:

- at least 30 calendar days;
- at least 200 real paper trades;
- at least 2 market regimes;
- periodic reports generated;
- strategy/config immutability enforced.

## Architecture

Certification lives outside trading execution. It reads paper-session evidence and metadata, computes a certification status, and writes auditable reports. It does not create trades, alter strategy decisions, enable LIVE, or bypass risk rules.

The certification checker is deterministic and file-based first, matching the existing harness pattern. Later phases can feed it from the database or live paper session logs without changing the acceptance semantics.

## Components

- `harness/scripts/new_phase.py --phase 16`: creates phase report, UAT checklist, and evidence directory.
- `docs/phases/16/certification-state.json`: append-only certification state snapshot for the current strategy version.
- `harness/scripts/paper_certification.py`: validates thresholds, generates periodic report snapshots, and returns PASS/PENDING reasons.
- `harness/state/progress.yaml`: marks only framework deliverables complete now; time/trade/regime deliverables stay pending until evidence exists.
- `docs/phases/16/evidence/*.log`: command evidence captured through `harness/scripts/evidence.sh`.

## Certification Rules

- Calendar days are computed from observed paper-session timestamps, not from wall-clock claims.
- Trades count only from paper execution records produced by the paper engine or accepted paper-session artifacts.
- Market regimes count distinct regimes observed in paper evidence; duplicate names do not inflate the count.
- If 30 days pass but fewer than 200 trades exist, certification remains pending and extends automatically.
- Artificial trades are invalid. Test fixtures may validate code paths but never satisfy certification.
- A strategy or risk-relevant config hash change invalidates the active certification and starts a new version.

## Error Handling

- Missing state file: certification reports `PENDING` with a clear reason.
- Malformed evidence: certification reports `PENDING` and cites the path.
- Strategy hash mismatch: certification reports `INVALIDATED` and requires a new certification version.
- No sufficient trades/regimes/days: certification reports `PENDING`, never `FAIL`, unless evidence is corrupt.

## Testing

- Unit tests cover threshold logic for days, trades, regimes, extension after 30 days, and invalidation on strategy hash change.
- Harness CLI tests verify deterministic report output and exit codes.
- Gate checks remain evidence-based through `progress.py` and `gate_check.py`.

## Human Gate

The user approves only after the checker reports all thresholds met and the UAT checklist is approved. Until then, Phase 16 can be in progress with no blockers if the certification framework is working and waiting for real elapsed evidence.
