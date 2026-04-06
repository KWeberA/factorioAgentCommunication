from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from factorio_agent_bridge.protocol import (
    ACTION_PLAN,
    build_metrics,
    build_summary,
    ensure_protocol_dirs,
    FACTORIO_LOG,
    list_frames,
    load_json,
    load_jsonl,
    METRICS,
    SCENARIO,
    write_json,
    write_jsonl,
)


HARNESS_DIR = "agent-bridge"


def synthetic_boundary_events(run_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "tick": run_manifest.get("start_tick"),
            "category": "scenario_started",
            "event": "scenario_started",
            "mod_name": run_manifest.get("mod_name"),
            "scenario_name": run_manifest.get("scenario_name"),
            "subject_ids": {},
            "position": None,
            "reason": "harness-start",
            "details": {},
            "source": "harness",
        },
        {
            "tick": run_manifest.get("end_tick"),
            "category": "scenario_finished",
            "event": "scenario_finished",
            "mod_name": run_manifest.get("mod_name"),
            "scenario_name": run_manifest.get("scenario_name"),
            "subject_ids": {},
            "position": None,
            "reason": run_manifest.get("status"),
            "details": {},
            "source": "harness",
        },
    ]


def _annotate_assertions(run_manifest: dict[str, Any], assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for index, assertion in enumerate(assertions):
        row = dict(assertion)
        row.setdefault("mod_name", run_manifest.get("mod_name"))
        row.setdefault("scenario_name", run_manifest.get("scenario_name"))
        row.setdefault("assertion_index", index)
        row.setdefault("related_group_ids", [])
        row.setdefault("related_event_ticks", [])
        annotated.append(row)
    return annotated


def _annotate_frame_context(run_manifest: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    frame = dict(frame)
    frame["scenario_name"] = run_manifest.get("scenario_name")
    frame["mod_name"] = run_manifest.get("mod_name")
    frame.setdefault("meta", {})
    frame["meta"]["scenario_name"] = run_manifest.get("scenario_name")
    frame["meta"]["target_mod_name"] = run_manifest.get("mod_name")
    return frame


def _annotate_event_records(events: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        row = dict(event)
        row.setdefault("source", source)
        row["source_event_index"] = index
        annotated.append(row)
    return annotated


def copy_harness_outputs(raw_script_output_root: Path, output_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], int, list[dict[str, Any]]]:
    artifacts = ensure_protocol_dirs(output_root)
    harness_root = raw_script_output_root / HARNESS_DIR
    run_manifest = load_json(harness_root / "run-manifest.json")
    assertions = _annotate_assertions(run_manifest, load_json(harness_root / "assertions.json"))
    harness_events = _annotate_event_records(load_optional_jsonl(harness_root / "events.jsonl"), source="harness")

    write_json(artifacts.run_manifest, run_manifest)
    write_json(artifacts.assertions, assertions)

    raw_frames_dir = harness_root / "frames"
    for frame_path in list_frames(raw_frames_dir):
        write_json(artifacts.frames / frame_path.name, _annotate_frame_context(run_manifest, load_json(frame_path)))

    for name, target in (
        (SCENARIO, artifacts.scenario),
        (ACTION_PLAN, artifacts.action_plan),
        (METRICS, artifacts.metrics),
    ):
        source = harness_root / name
        if source.exists():
            write_json(target, load_json(source))

    if (harness_root / FACTORIO_LOG).exists():
        artifacts.factorio_log.write_text((harness_root / FACTORIO_LOG).read_text(encoding="utf-8"), encoding="utf-8")

    return run_manifest, assertions, len(list_frames(artifacts.frames)), harness_events


def _validate_assertion_context(assertions: list[dict[str, Any]], expected_scenario_name: str, expected_mod_name: str) -> list[str]:
    reasons: list[str] = []
    for assertion in assertions:
        if assertion.get("scenario_name") not in {None, expected_scenario_name}:
            reasons.append("scenario-isolation-violation")
            break
        if assertion.get("mod_name") not in {None, expected_mod_name}:
            reasons.append("scenario-isolation-violation")
            break
    return reasons


def _validate_frame_context(frames_dir: Path, expected_scenario_name: str, expected_mod_name: str) -> list[str]:
    reasons: list[str] = []
    for frame_path in list_frames(frames_dir):
        frame = load_json(frame_path)
        frame_scenario = frame.get("scenario_name") or frame.get("meta", {}).get("scenario_name")
        frame_mod = frame.get("mod_name") or frame.get("meta", {}).get("target_mod_name")
        if frame_scenario != expected_scenario_name or frame_mod != expected_mod_name:
            reasons.append("scenario-isolation-violation")
            break
    return reasons


def _validate_event_context(events: list[dict[str, Any]], expected_scenario_name: str, expected_mod_name: str) -> list[str]:
    reasons: list[str] = []
    for event in events:
        if event.get("scenario_name") != expected_scenario_name or event.get("mod_name") != expected_mod_name:
            reasons.append("scenario-isolation-violation")
            break
    return reasons


def finalize_normalized_run(
    output_root: Path,
    *,
    run_manifest: dict[str, Any],
    assertions: list[dict[str, Any]],
    normalized_events: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    artifacts = ensure_protocol_dirs(output_root)
    assertions = _annotate_assertions(run_manifest, assertions)
    events = index_events(list(normalized_events))
    write_json(artifacts.run_manifest, run_manifest)
    write_json(artifacts.assertions, assertions)
    write_jsonl(artifacts.events, events)

    failure_reasons = [assertion["name"] for assertion in assertions if not assertion.get("passed")]
    failure_reasons.extend(_validate_assertion_context(assertions, run_manifest["scenario_name"], run_manifest["mod_name"]))
    failure_reasons.extend(_validate_event_context(events, run_manifest["scenario_name"], run_manifest["mod_name"]))
    failure_reasons.extend(_validate_frame_context(artifacts.frames, run_manifest["scenario_name"], run_manifest["mod_name"]))
    failure_reasons = sorted(set(failure_reasons))

    summary = build_summary(
        run_manifest=run_manifest,
        assertions=assertions,
        frame_count=len(list_frames(artifacts.frames)),
        event_count=len(events),
        failure_reasons=failure_reasons,
    )
    if "scenario-isolation-violation" in failure_reasons:
        summary["status"] = "failed"
    write_json(artifacts.summary, summary)
    write_json(
        artifacts.metrics,
        build_metrics(
            run_manifest=run_manifest,
            assertions=assertions,
            frame_count=len(list_frames(artifacts.frames)),
            event_count=len(events),
        ),
    )
    return summary


def index_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        row = dict(event)
        row["event_index"] = index
        indexed.append(row)
    return indexed


def merge_events(*event_lists: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for order, event_list in enumerate(event_lists):
        for index, event in enumerate(event_list):
            row = dict(event)
            row["_merge_order"] = order
            row["_merge_index"] = index
            merged.append(row)

    merged.sort(key=lambda event: (
        event.get("tick") if event.get("tick") is not None else -1,
        event["_merge_order"],
        event["_merge_index"],
    ))

    normalized: list[dict[str, Any]] = []
    for event in merged:
        event.pop("_merge_order", None)
        event.pop("_merge_index", None)
        normalized.append(event)
    return index_events(normalized)


def _event_signature(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event.get("source"),
        event.get("category"),
        event.get("event"),
        event.get("reason"),
        tuple(sorted((event.get("subject_ids") or {}).items())),
    )


def _assertion_signature(assertion: dict[str, Any]) -> tuple[str, bool]:
    return assertion.get("name"), bool(assertion.get("passed"))


def _frame_signature(frame: dict[str, Any]) -> tuple[Any, ...]:
    return (
        frame.get("tick"),
        frame.get("scenario_name"),
        frame.get("mod_name"),
    )


def standard_diff_runs(left_root: Path, right_root: Path) -> dict[str, Any]:
    left_summary = load_json(left_root / "summary.json")
    right_summary = load_json(right_root / "summary.json")
    left_assertions = load_json(left_root / "assertions.json")
    right_assertions = load_json(right_root / "assertions.json")
    left_events = load_optional_jsonl(left_root / "events.jsonl")
    right_events = load_optional_jsonl(right_root / "events.jsonl")
    left_failure = load_optional_json(left_root / "failure.json")
    right_failure = load_optional_json(right_root / "failure.json")
    left_frames = [load_json(frame_path) for frame_path in list_frames(left_root / "frames")]
    right_frames = [load_json(frame_path) for frame_path in list_frames(right_root / "frames")]

    left_failed = {assertion["name"] for assertion in left_assertions if not assertion.get("passed")}
    right_failed = {assertion["name"] for assertion in right_assertions if not assertion.get("passed")}

    left_event_counts = Counter(_event_signature(event) for event in left_events)
    right_event_counts = Counter(_event_signature(event) for event in right_events)
    left_frame_counts = Counter(_frame_signature(frame) for frame in left_frames)
    right_frame_counts = Counter(_frame_signature(frame) for frame in right_frames)

    return {
        "left_status": left_summary["status"],
        "right_status": right_summary["status"],
        "assertion_diff": {
            "improved": sorted(left_failed - right_failed),
            "regressed": sorted(right_failed - left_failed),
            "unchanged_failures": sorted(left_failed & right_failed),
        },
        "event_diff": {
            "missing": summarize_counter_delta(left_event_counts - right_event_counts),
            "new": summarize_counter_delta(right_event_counts - left_event_counts),
        },
        "frame_diff": {
            "missing": summarize_counter_delta(left_frame_counts - right_frame_counts),
            "new": summarize_counter_delta(right_frame_counts - left_frame_counts),
            "left_frame_count": len(left_frames),
            "right_frame_count": len(right_frames),
        },
        "failure_diff": {
            "left_failure": left_failure,
            "right_failure": right_failure,
            "phase_changed": (left_summary.get("phase") != right_summary.get("phase")),
        },
        "semantic_diff": {},
    }


def summarize_counter_delta(counter: Counter[tuple[Any, ...]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, count in sorted(counter.items(), key=lambda item: item[0]):
        rows.append({
            "signature": list(key),
            "count": count,
        })
    return rows


def load_optional_json(path: Path) -> Any:
    if not path.exists():
        return None
    return load_json(path)


def load_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_jsonl(path)
