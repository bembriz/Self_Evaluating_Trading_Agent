from pathlib import Path

import release_check


def test_check_testnet_requires_successful_lifecycle_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(release_check, "REPO", tmp_path)
    log = tmp_path / "docs/phases/15/evidence/bybit-testnet-lifecycle-pass-final.log"
    log.parent.mkdir(parents=True)

    assert release_check.check_testnet()[0] == "PENDING"

    log.write_text("TESTNET_LIFECYCLE=PASS\nexit=1\n", encoding="utf-8")
    assert release_check.check_testnet()[0] == "PENDING"

    log.write_text("TESTNET_LIFECYCLE=PASS\nexit=0\n", encoding="utf-8")
    status, detail = release_check.check_testnet()

    assert status == "PASS"
    assert str(Path("docs/phases/15/evidence/bybit-testnet-lifecycle-pass-final.log")) in detail
