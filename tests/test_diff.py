import json
from pathlib import Path

from factorio_agent_bridge.adapters import advanced_biter_tactics
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

    (left / "events.jsonl").write_text(json.dumps({
        "source": "mod-semantic",
        "category": "decision_made",
        "event": "contact_found",
        "reason": "nearest-wall",
        "subject_ids": {"group_id": 1},
    }) + "\n", encoding="utf-8")
    (right / "events.jsonl").write_text(
        json.dumps({
            "source": "mod-semantic",
            "category": "decision_made",
            "event": "contact_found",
            "reason": "nearest-wall",
            "subject_ids": {"group_id": 1},
        }) + "\n" +
        json.dumps({
            "source": "mod-semantic",
            "category": "decision_made",
            "event": "coverage_violation",
            "reason": "covered-path",
            "subject_ids": {"group_id": 1},
        }) + "\n",
        encoding="utf-8",
    )
    (left / "failure.json").write_text(json.dumps({"phase": "benchmark"}), encoding="utf-8")
    (left / "frames").mkdir()
    (right / "frames").mkdir()
    (left / "frames" / "frame-30.json").write_text(json.dumps({"tick": 30, "scenario_name": "a", "mod_name": "m"}), encoding="utf-8")
    (right / "frames" / "frame-30.json").write_text(json.dumps({"tick": 30, "scenario_name": "a", "mod_name": "m"}), encoding="utf-8")
    (right / "frames" / "frame-60.json").write_text(json.dumps({"tick": 60, "scenario_name": "a", "mod_name": "m"}), encoding="utf-8")

    diff = standard_diff_runs(left, right)
    assert diff["assertion_diff"]["improved"] == ["expected-event-sequence"]
    assert diff["assertion_diff"]["unchanged_failures"] == ["support-mode"]
    assert diff["event_diff"]["new"][0]["count"] == 1
    assert diff["failure_diff"]["left_failure"]["phase"] == "benchmark"


def test_abt_diff_reports_semantic_group_deltas(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    for root in (left, right):
        (root / "frames").mkdir(parents=True)
        (root / "summary.json").write_text(json.dumps({"status": "passed", "phase": "complete"}), encoding="utf-8")
        (root / "assertions.json").write_text("[]", encoding="utf-8")
        (root / "events.jsonl").write_text("", encoding="utf-8")

    (left / "frames" / "frame-10.json").write_text(json.dumps({
        "tick": 10,
        "scenario_name": "wall-open",
        "mod_name": "advanced-biter-tactics",
        "observations": {"combat": {"groups": [{"group_id": 1, "in_turret_coverage": False, "support_mode": "none"}]}},
        "semantic_extensions": {"advanced_biter_tactics": {"group_diagnostics": [{"group_id": 1, "progress_stalled": False}]}}
    }), encoding="utf-8")
    (right / "frames" / "frame-10.json").write_text(json.dumps({
        "tick": 10,
        "scenario_name": "wall-open",
        "mod_name": "advanced-biter-tactics",
        "observations": {"combat": {"groups": [{"group_id": 1, "in_turret_coverage": True, "support_mode": "cone-siege"}]}},
        "semantic_extensions": {"advanced_biter_tactics": {"group_diagnostics": [{"group_id": 1, "progress_stalled": True}]}}
    }), encoding="utf-8")

    diff = advanced_biter_tactics.diff_runs(left, right)
    assert diff["semantic_diff"]["abt"]["groups_newly_entering_turret_coverage"] == [1]
    assert diff["semantic_diff"]["abt"]["groups_newly_stalled"] == [1]
    assert diff["semantic_diff"]["abt"]["support_mode_changes"]["right"] == {"1": "cone-siege"}
