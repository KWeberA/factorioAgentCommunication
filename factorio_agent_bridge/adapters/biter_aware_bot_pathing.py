from __future__ import annotations

from pathlib import Path
from typing import Any

from factorio_agent_bridge.adapters.common import (
    copy_harness_outputs,
    finalize_normalized_run,
    load_optional_json,
    load_optional_jsonl,
    standard_diff_runs,
    synthetic_boundary_events,
)


NATIVE_DIR = "biter-aware-bot-pathing"


def _normalize_native_event(event: dict[str, Any], scenario_name: str, mod_name: str) -> dict[str, Any]:
    return {
        "tick": event.get("tick"),
        "category": event.get("category", "decision_made"),
        "event": event.get("event"),
        "mod_name": mod_name,
        "scenario_name": scenario_name,
        "subject_ids": event.get("subject_ids", {}),
        "position": event.get("position"),
        "reason": event.get("reason"),
        "details": event.get("details", {}),
    }


def normalize_run(raw_script_output_root: Path, output_root: Path) -> dict[str, Any]:
    native_root = raw_script_output_root / NATIVE_DIR
    run_manifest, assertions, _ = copy_harness_outputs(raw_script_output_root, output_root)
    boundary_events = synthetic_boundary_events(run_manifest)

    native_events = load_optional_jsonl(native_root / "bridge-events.jsonl")
    validation_summary = load_optional_json(native_root / "validation-test-map.json")
    if validation_summary is not None:
        native_events.append(
            {
                "tick": run_manifest.get("end_tick"),
                "event": "validation_summary_loaded",
                "category": "decision_made",
                "reason": "validation-json",
                "position": None,
                "subject_ids": {},
                "details": {
                    "keys": sorted(validation_summary.keys()),
                },
            }
        )

    normalized_events = [boundary_events[0]]
    normalized_events.extend(
        _normalize_native_event(event, run_manifest["scenario_name"], run_manifest["mod_name"])
        for event in native_events
    )
    normalized_events.append(boundary_events[1])
    return finalize_normalized_run(
        output_root,
        run_manifest=run_manifest,
        assertions=assertions,
        normalized_events=normalized_events,
    )


def diff_runs(left_root: Path, right_root: Path) -> dict[str, Any]:
    return standard_diff_runs(left_root, right_root)
