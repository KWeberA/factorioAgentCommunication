from pathlib import Path

from factorio_agent_bridge.protocol import build_metrics, build_summary, ensure_protocol_dirs, load_json, load_jsonl


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


def test_protocol_dirs_include_v2_optional_artifacts(tmp_path: Path) -> None:
    artifacts = ensure_protocol_dirs(tmp_path)
    assert artifacts.scenario.name == "scenario.json"
    assert artifacts.action_plan.name == "action-plan.json"
    assert artifacts.metrics.name == "metrics.json"
    assert artifacts.failure.name == "failure.json"
    assert artifacts.factorio_log.name == "factorio-current.log"


def test_build_metrics() -> None:
    manifest = load_json(FIXTURES / "sample-run-manifest.json")
    assertions = load_json(FIXTURES / "sample-assertions.json")
    metrics = build_metrics(manifest, assertions, frame_count=4, event_count=3)

    assert metrics["assertion_counts"]["total"] == 2
    assert metrics["frame_count"] == 4
    assert metrics["event_count"] == 3


def test_load_json_sanitizes_factorio_non_finite_tokens(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"stop_tick": inf, "negative": -inf, "other": nan}', encoding="utf-8")

    payload = load_json(payload_path)

    assert payload["stop_tick"] is None
    assert payload["negative"] is None
    assert payload["other"] is None
