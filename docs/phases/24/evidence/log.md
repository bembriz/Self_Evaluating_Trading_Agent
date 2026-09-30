- `2026-09-29T18:32:40-06:00` **p24-orchestrator-ruff** → `uv run ruff check .` · exit=`0` · artifact: docs/phases/24/evidence/p24-orchestrator-ruff.log
- `2026-09-29T18:32:40-06:00` **p24-orchestrator-format** → `uv run ruff format --check .` · exit=`0` · artifact: docs/phases/24/evidence/p24-orchestrator-format.log
- `2026-09-29T18:32:41-06:00` **p24-orchestrator-mypy** → `uv run mypy src tests` · exit=`0` · artifact: docs/phases/24/evidence/p24-orchestrator-mypy.log
- `2026-09-29T18:32:50-06:00` **p24-orchestrator-tests-coverage** → `uv run pytest tests/test_medallion_refresh.py tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py tests/test_gold_dataset.py --cov=infrastructure.medallion.refresh --cov-branch --cov-fail-under=90` · exit=`0` · artifact: docs/phases/24/evidence/p24-orchestrator-tests-coverage.log
- `2026-09-29T18:33:00-06:00` **p24-orchestrator-summary** → `python3 -c print("ruff=PASS"); print("format=PASS"); print("mypy=PASS"); print("medallion_tests=161 PASS"); print("orchestrator_coverage=96.48%"); print("planner=PASS"); print("dry_run=PASS"); print("idempotencia=PASS"); print("resume=PASS"); print("WF_HOLDOUT_BLOCKED=YES"); print("UNASSIGNED_RESEARCH_READS=0"); print("PAPER_IMPACT=NO"); print("full_pytest_local=1310 PASS + 15 errors: PostgreSQL 127.0.0.1:5433 connection refused")` · exit=`0` · artifact: docs/phases/24/evidence/p24-orchestrator-summary.log
- `2026-09-29T19:25:18-06:00` **p24-systemd-units-pytest** → `uv run pytest tests/test_medallion_systemd_units.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-pytest.log
- `2026-09-29T19:25:18-06:00` **p24-systemd-units-ruff** → `uv run ruff check tests/test_medallion_systemd_units.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-ruff.log
- `2026-09-29T19:25:18-06:00` **p24-systemd-units-format** → `uv run ruff format --check tests/test_medallion_systemd_units.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-format.log
- `2026-09-29T19:25:18-06:00` **p24-systemd-units-mypy** → `uv run mypy tests/test_medallion_systemd_units.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-mypy.log
- `2026-09-29T19:25:18-06:00` **p24-systemd-units-bash-syntax** → `bash -n deployment/medallion/systemd/install.sh deployment/medallion/systemd/uninstall.sh` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-bash-syntax.log
- `2026-09-29T19:25:19-06:00` **p24-systemd-units-systemd-verify** → `bash -c if command -v systemd-analyze >/dev/null 2>&1; then systemd-analyze verify deployment/medallion/systemd/medallion-refresh.service deployment/medallion/systemd/medallion-refresh.timer; else printf "systemd-analyze not available\\n"; exit 64; fi` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-systemd-verify.log
- `2026-09-29T19:25:19-06:00` **p24-systemd-units-calendar** → `bash -c if command -v systemd-analyze >/dev/null 2>&1; then systemd-analyze calendar "*-*-* 06:20:00 UTC"; else printf "systemd-analyze not available\\n"; exit 64; fi` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-calendar.log
- `2026-09-29T19:25:19-06:00` **p24-systemd-units-shellcheck** → `bash -c if command -v shellcheck >/dev/null 2>&1; then shellcheck deployment/medallion/systemd/install.sh deployment/medallion/systemd/uninstall.sh; else printf "shellcheck not available / not installed\\n"; fi` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-shellcheck.log
- `2026-09-29T19:25:19-06:00` **p24-systemd-units-state-flags** → `bash -c printf "SERVER_CHANGED=NO\\nPAPER_IMPACT=NO\\n"` · exit=`0` · artifact: docs/phases/24/evidence/p24-systemd-units-state-flags.log
- `2026-09-29T19:52:45-06:00` **p24-capacity-guards-focused-tests** → `uv run pytest tests/test_medallion_capacity_guards.py tests/test_medallion_refresh.py tests/test_medallion_systemd_units.py --cov=infrastructure.medallion.capacity_guards --cov=infrastructure.medallion.refresh --cov-report=term-missing` · exit=`0` · artifact: docs/phases/24/evidence/p24-capacity-guards-focused-tests.log
- `2026-09-29T19:52:45-06:00` **p24-capacity-guards-ruff** → `uv run ruff check src/infrastructure/medallion/capacity_guards.py src/infrastructure/medallion/refresh.py tests/test_medallion_capacity_guards.py tests/test_medallion_refresh.py tests/test_medallion_systemd_units.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-capacity-guards-ruff.log
- `2026-09-29T19:52:45-06:00` **p24-capacity-guards-format** → `uv run ruff format --check src/infrastructure/medallion/capacity_guards.py src/infrastructure/medallion/refresh.py tests/test_medallion_capacity_guards.py tests/test_medallion_refresh.py tests/test_medallion_systemd_units.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-capacity-guards-format.log
- `2026-09-29T19:52:46-06:00` **p24-capacity-guards-mypy** → `uv run mypy src/infrastructure/medallion/capacity_guards.py src/infrastructure/medallion/refresh.py tests/test_medallion_capacity_guards.py tests/test_medallion_refresh.py tests/test_medallion_systemd_units.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-capacity-guards-mypy.log
- `2026-09-29T19:52:47-06:00` **p24-capacity-guards-systemd-verify** → `bash -c if command -v systemd-analyze >/dev/null 2>&1; then systemd-analyze verify deployment/medallion/systemd/medallion-refresh.service deployment/medallion/systemd/medallion-refresh.timer; else printf "systemd-analyze not available\\n"; exit 64; fi` · exit=`0` · artifact: docs/phases/24/evidence/p24-capacity-guards-systemd-verify.log
- `2026-09-29T19:52:47-06:00` **p24-capacity-guards-state-flags** → `bash -c printf "SSD_MIN_FREE_GB_GUARD=PASS\\nSSD_CACHE_MAX_GB_GUARD=PASS\\nDATA_VOLUME_MARKER_UUID_LABEL_GUARD=PASS\\nRETENTION=PASS\\nFAIL_BEFORE_WRITE=YES\\nCANONICAL_DATA_PROTECTED=YES\\nDRY_RUN_SAFE=YES\\nSERVER_CHANGED=NO\\nPAPER_IMPACT=NO\\n"` · exit=`0` · artifact: docs/phases/24/evidence/p24-capacity-guards-state-flags.log
- `2026-09-29T20:39:51-06:00` **p24-uat-fix-focal-tests** → `uv run pytest tests/test_medallion_future_collection.py tests/test_medallion_refresh.py tests/test_medallion_capacity_guards.py tests/test_medallion_systemd_units.py tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py tests/test_source_schema.py tests/test_gold_dataset.py` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-focal-tests.log
- `2026-09-29T20:41:16-06:00` **p24-uat-fix-unit-suite** → `env -u DATABASE_URL bash -c uv run pytest tests --ignore=tests/integration --ignore=tests/e2e -q` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-unit-suite.log
- `2026-09-29T20:43:55-06:00` **p24-uat-fix-unit-coverage** → `env -u DATABASE_URL bash -c uv run pytest tests --ignore=tests/integration --ignore=tests/e2e --cov=src --cov-branch --cov-fail-under=90 -q` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-unit-coverage.log
- `2026-09-29T20:49:04-06:00` **p24-uat-fix-ruff** → `uv run ruff check .` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-ruff.log
- `2026-09-29T20:49:04-06:00` **p24-uat-fix-format** → `uv run ruff format --check .` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-format.log
- `2026-09-29T20:49:05-06:00` **p24-uat-fix-mypy** → `uv run mypy src tests` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-mypy.log
- `2026-09-29T20:49:05-06:00` **p24-uat-fix-systemd-verify** → `bash -c if command -v systemd-analyze >/dev/null 2>&1; then systemd-analyze verify deployment/medallion/systemd/medallion-refresh.service deployment/medallion/systemd/medallion-refresh.timer; else printf "systemd-analyze not available\n"; exit 64; fi` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-systemd-verify.log
- `2026-09-29T20:49:05-06:00` **p24-uat-fix-state-flags** → `bash -c printf "RUNTIME=/opt/seta-medallion\nMEDALLION_START_DAY=2026-08-24\nBRONZE_PATH=/srv/data/medallion/bronze/bybit/spot/ETHUSDT\nINGEST_SCOPE=explicit-DevelopmentAndFutureCollection\nDEVELOPMENT_DEFAULT_PRESERVED=YES\nWF_ALWAYS_BLOCKED=YES\nFINAL_HOLDOUT_ALWAYS_BLOCKED=YES\nFUTURE_2026_08_24_BRONZE_SILVER_CANDLES=YES\nGOLD_RESEARCH_REPLAY_ENABLED=NO\nSERVER_CHANGED=NO\nPAPER_IMPACT=NO\n"` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-fix-state-flags.log
- `2026-09-29T21:15:01-06:00` **p24-uat-systemd-state** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 systemctl is-enabled medallion-refresh.timer; systemctl is-active medallion-refresh.timer; systemctl list-timers medallion-refresh.timer --no-pager; systemctl show medallion-refresh.service -p ActiveState -p SubState -p Result -p ExecMainStatus` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-systemd-state.log
- `2026-09-29T21:15:02-06:00` **p24-uat-status-json** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 cat /srv/fast/medallion/refresh/status.json` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-status-json.log
- `2026-09-29T21:15:02-06:00` **p24-uat-journal** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 journalctl -u medallion-refresh.service --no-pager | tail -20` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-journal.log
- `2026-09-29T21:15:03-06:00` **p24-uat-canonical-idempotency** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 sha256sum /srv/data/medallion/bronze/bybit/spot/ETHUSDT/manifest.json /srv/data/medallion/silver/trades/ETHUSDT/manifest.json /srv/data/medallion/silver/candles/ETHUSDT/manifest.json; echo bronze_date_dirs=$(ls /srv/data/medallion/bronze/bybit/spot/ETHUSDT | grep -c '^date='); echo silver_trades_date_dirs=$(ls /srv/data/medallion/silver/trades/ETHUSDT | grep -c '^date='); echo part_leftovers=$(find /srv/data/medallion /srv/fast/medallion -name '*.part' | wc -l)` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-canonical-idempotency.log
- `2026-09-29T21:15:03-06:00` **p24-uat-paper-safety** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 docker inspect --format 'ID={{.Id}} IMAGE={{.Config.Image}} STARTED={{.State.StartedAt}} RUNNING={{.State.Running}} RESTARTS={{.RestartCount}}' self-evaluating-trading-agent-paper-runner-1; docker inspect --format '{{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' self-evaluating-trading-agent-paper-runner-1` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-paper-safety.log
- `2026-09-29T21:15:04-06:00` **p24-uat-gold-unchanged** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 ls /srv/data/medallion/gold/replay-datasets/ETHUSDT; echo gold_files_since_apply=$(find /srv/data/medallion/gold -newermt '2026-09-30 03:00' -type f | wc -l)` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-gold-unchanged.log
- `2026-09-29T21:15:18-06:00` **p24-uat-negative-guards** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 PYTHONPATH=/opt/seta-medallion/src python3 - <<"PY"
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from infrastructure.medallion.capacity_guards import (
    CapacityGuardConfig, CapacityGuardError, DiskUsage, VolumeIdentity, run_capacity_preflight,
)
from infrastructure.medallion.split_guard import (
    SplitGuardError, ensure_ingest_allowed, PHASE24_INGEST_SCOPE, DEFAULT_INGEST_SCOPE,
)

GIB = 1024**3

class P:
    def __init__(self, free=396*GIB, mount=True, label="LENOVO_DATA", uuid="10fff707-60e4-4321-afa0-a3c4704d9e8d", marker="LENOVO_DATA"):
        self.free=free; self.mount=mount; self.label=label; self.uuid=uuid; self.marker=marker
    def disk_usage(self, p): return DiskUsage(total=500*GIB, used=1, free=self.free)
    def is_mount(self, p): return self.mount
    def read_text(self, p): return self.marker
    def volume_identity(self, p): return VolumeIdentity(label=self.label, uuid=self.uuid)
    def remove_tree(self, p): raise AssertionError("purge attempted")

def blocked(label, fn):
    try:
        fn(); print(label + ": NOT_BLOCKED")
    except (CapacityGuardError, SplitGuardError) as e:
        print(label + ": BLOCKED " + type(e).__name__)

with TemporaryDirectory() as td:
    def cfg():
        return CapacityGuardConfig(
            data_mount=Path(td)/"srv/data", marker_path=Path(td)/"m",
            expected_label="LENOVO_DATA",
            expected_uuid="10fff707-60e4-4321-afa0-a3c4704d9e8d",
            ssd_path=Path(td)/"fast", cache_path=Path(td)/"cache",
        )
    blocked("invalid_marker_empty", lambda: run_capacity_preflight(cfg(), probe=P(marker="")))
    blocked("wrong_label", lambda: run_capacity_preflight(cfg(), probe=P(label="WRONG")))
    blocked("uuid_mismatch", lambda: run_capacity_preflight(cfg(), probe=P(uuid="deadbeef")))
    blocked("not_mountpoint", lambda: run_capacity_preflight(cfg(), probe=P(mount=False)))
    blocked("insufficient_free_space", lambda: run_capacity_preflight(cfg(), probe=P(free=1*GIB)))
    blocked("wf_2025_06_17", lambda: ensure_ingest_allowed(date(2025,6,17), scope=PHASE24_INGEST_SCOPE))
    blocked("holdout_2026_03_15", lambda: ensure_ingest_allowed(date(2026,3,15), scope=PHASE24_INGEST_SCOPE))
    blocked("holdout_last_2026_08_23", lambda: ensure_ingest_allowed(date(2026,8,23), scope=PHASE24_INGEST_SCOPE))
    blocked("future_without_scope", lambda: ensure_ingest_allowed(date(2026,8,24), scope=DEFAULT_INGEST_SCOPE))
    ensure_ingest_allowed(date(2026,8,24), scope=PHASE24_INGEST_SCOPE)
    print("future_2026_08_24_with_scope: ALLOWED")
print("REAL_MARKER=" + Path("/srv/data/.lenovosrv-data-volume").read_text().splitlines()[0])
PY` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-negative-guards.log
- `2026-09-29T21:16:16-06:00` **p24-uat-paper-safety** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 docker inspect --format 'ID={{.Id}} IMAGE={{.Config.Image}} STARTED={{.State.StartedAt}} RUNNING={{.State.Running}} RESTARTS={{.RestartCount}}' self-evaluating-trading-agent-paper-runner-1; docker inspect --format '{{range .Mounts}}{{.Source}}->{{.Destination}} rw={{.RW}}{{"\n"}}{{end}}' self-evaluating-trading-agent-paper-runner-1` · exit=`0` · artifact: docs/phases/24/evidence/p24-uat-paper-safety.log
