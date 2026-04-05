from pathlib import Path

from factorio_agent_bridge.protocol import build_summary, load_json, load_jsonl


FIXTURES = Path(__file__).parent / "fixtures" / "protocol"


def test_load_json_and_jsonl() -> None:
    manifest = load_json(FIXTURES / "sample-run-manifest.json")
    events = load_jsonl(FIXTURES / "sample-events.jsonl")
    assert manifest["scenario_name"] == "wall-covered-flank"
    assert len(events) == 3
    assert events[1]["event"] == "flank_waypoint_set"


def test_build_summary() -> None:
    manifest = load_json(FIXTURES / "sample-run-manifest.json")
    assertions = load_json(FIXTURES / "sample-assertions.json")
    summary = build_summary(manifest, assertions, frame_count=4, event_count=3)
    assert summary["status"] == "passed"
    assert summary["assertion_counts"]["total"] == 2
    assert summary["frame_count"] == 4
