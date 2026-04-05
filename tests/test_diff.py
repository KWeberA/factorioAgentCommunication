import json
from pathlib import Path

from factorio_agent_bridge.adapters.common import standard_diff_runs


def test_diff_runs_reports_improvements_and_regressions(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    (left / "summary.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    (right / "summary.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    (left / "assertions.json").write_text(json.dumps([
        {"name": "expected-event-sequence", "passed": False},
        {"name": "support-mode", "passed": False},
    ]), encoding="utf-8")
    (right / "assertions.json").write_text(json.dumps([
        {"name": "expected-event-sequence", "passed": True},
        {"name": "support-mode", "passed": False},
    ]), encoding="utf-8")

    diff = standard_diff_runs(left, right)
    assert diff["improved"] == ["expected-event-sequence"]
    assert diff["unchanged_failures"] == ["support-mode"]
