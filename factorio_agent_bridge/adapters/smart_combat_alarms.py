from __future__ import annotations

from pathlib import Path

from factorio_agent_bridge.adapters.common import (
    copy_harness_outputs,
    finalize_normalized_run,
    load_optional_jsonl,
    standard_diff_runs,
    synthetic_boundary_events,
)


NATIVE_DIR = "smart-combat-alarms"


def normalize_run(raw_script_output_root: Path, output_root: Path) -> dict:
    native_root = raw_script_output_root / NATIVE_DIR
    run_manifest, assertions, _ = copy_harness_outputs(raw_script_output_root, output_root)
    boundary_events = synthetic_boundary_events(run_manifest)
    native_events = load_optional_jsonl(native_root / "bridge-events.jsonl")

    normalized_events = [boundary_events[0]]
    for event in native_events:
        normalized_events.append(
            {
                "tick": event.get("tick"),
                "category": event.get("category", "alert_triggered"),
                "event": event.get("event"),
                "mod_name": run_manifest["mod_name"],
                "scenario_name": run_manifest["scenario_name"],
                "subject_ids": event.get("subject_ids", {}),
                "position": event.get("position"),
                "reason": event.get("reason"),
                "details": event.get("details", {}),
            }
        )
    normalized_events.append(boundary_events[1])

    return finalize_normalized_run(
        output_root,
        run_manifest=run_manifest,
        assertions=assertions,
        normalized_events=normalized_events,
    )


def diff_runs(left_root: Path, right_root: Path) -> dict:
    return standard_diff_runs(left_root, right_root)
