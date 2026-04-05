from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from factorio_agent_bridge.protocol import (
    build_summary,
    ensure_protocol_dirs,
    list_frames,
    load_json,
    load_jsonl,
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
        },
    ]


def copy_harness_outputs(raw_script_output_root: Path, output_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    artifacts = ensure_protocol_dirs(output_root)
    harness_root = raw_script_output_root / HARNESS_DIR
    run_manifest = load_json(harness_root / "run-manifest.json")
    assertions = load_json(harness_root / "assertions.json")

    write_json(artifacts.run_manifest, run_manifest)
    write_json(artifacts.assertions, assertions)

    raw_frames_dir = harness_root / "frames"
    for frame_path in list_frames(raw_frames_dir):
        write_json(artifacts.frames / frame_path.name, load_json(frame_path))

    return run_manifest, assertions, len(list_frames(artifacts.frames))


def finalize_normalized_run(
    output_root: Path,
    *,
    run_manifest: dict[str, Any],
    assertions: list[dict[str, Any]],
    normalized_events: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    artifacts = ensure_protocol_dirs(output_root)
    events = list(normalized_events)
    write_json(artifacts.run_manifest, run_manifest)
    write_json(artifacts.assertions, assertions)
    write_jsonl(artifacts.events, events)

    summary = build_summary(
        run_manifest=run_manifest,
        assertions=assertions,
        frame_count=len(list_frames(artifacts.frames)),
        event_count=len(events),
        failure_reasons=[assertion["name"] for assertion in assertions if not assertion.get("passed")],
    )
    write_json(artifacts.summary, summary)
    return summary


def standard_diff_runs(left_root: Path, right_root: Path) -> dict[str, Any]:
    left_summary = load_json(left_root / "summary.json")
    right_summary = load_json(right_root / "summary.json")
    left_assertions = load_json(left_root / "assertions.json")
    right_assertions = load_json(right_root / "assertions.json")

    left_failed = {assertion["name"] for assertion in left_assertions if not assertion.get("passed")}
    right_failed = {assertion["name"] for assertion in right_assertions if not assertion.get("passed")}

    return {
        "left_status": left_summary["status"],
        "right_status": right_summary["status"],
        "improved": sorted(left_failed - right_failed),
        "regressed": sorted(right_failed - left_failed),
        "unchanged_failures": sorted(left_failed & right_failed),
    }


def load_optional_json(path: Path) -> Any:
    if not path.exists():
        return None
    return load_json(path)


def load_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_jsonl(path)
