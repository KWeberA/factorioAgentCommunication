from __future__ import annotations

from pathlib import Path
from typing import Any

from factorio_agent_bridge.adapters.common import (
    copy_harness_outputs,
    finalize_normalized_run,
    load_optional_jsonl,
    standard_diff_runs,
    synthetic_boundary_events,
)


NATIVE_DIR = "advanced-biter-tactics"


EVENT_CATEGORY_MAP = {
    "arena_wave_spawned": "wave_resolved",
    "group_registered": "scenario_started",
    "contact_found": "decision_made",
    "wall_network_scanned": "decision_made",
    "candidates_scored": "decision_made",
    "attack_selected": "target_selected",
    "flank_waypoint_set": "decision_made",
    "siege_site_selected": "decision_made",
    "support_mode_selected": "decision_made",
    "support_group_created": "decision_made",
    "support_position_rejected": "decision_made",
    "standoff_position_selected": "decision_made",
    "breach_pressure_detected": "entity_damaged",
    "breach_progress_updated": "breach_opened",
    "breach_assault_planned": "decision_made",
    "turret_priority_selected": "target_selected",
    "melee_split_created": "decision_made",
    "reserve_group_created": "decision_made",
    "ranged_cone_group_created": "decision_made",
    "ranged_cone_lane_set": "decision_made",
    "support_followup_started": "decision_made",
    "flame_lane_set": "decision_made",
    "fire_hazard_avoided": "decision_made",
    "open_entry_taken": "breach_opened",
    "interior_target_selected": "target_selected",
    "breach_reused": "breach_opened",
    "fallback_issued": "decision_made",
    "group_cleanup": "scenario_finished",
}


def _normalize_native_event(event: dict[str, Any], scenario_name: str) -> dict[str, Any]:
    category = EVENT_CATEGORY_MAP.get(event.get("event"), "decision_made")
    return {
        "tick": event.get("tick"),
        "category": category,
        "event": event.get("event"),
        "mod_name": "advanced-biter-tactics",
        "scenario_name": scenario_name,
        "subject_ids": {
            "group_id": event.get("group_id"),
            "siege_site_id": event.get("siege_site_id"),
            "support_group_id": event.get("support_group_id"),
        },
        "position": event.get("target_position") or event.get("group_position") or event.get("contact_position"),
        "reason": event.get("reason"),
        "details": {
            "state": event.get("state"),
            "support_mode": event.get("support_mode"),
            "selected_candidate_index": event.get("selected_candidate_index"),
            "wave_index": event.get("wave_index"),
            "entry_open": event.get("entry_open"),
        },
    }


def normalize_run(raw_script_output_root: Path, output_root: Path) -> dict[str, Any]:
    native_root = raw_script_output_root / NATIVE_DIR

    run_manifest, assertions, _ = copy_harness_outputs(raw_script_output_root, output_root)

    native_events = load_optional_jsonl(native_root / "events.jsonl")
    boundary_events = synthetic_boundary_events(run_manifest)
    normalized_events = [boundary_events[0]]
    normalized_events.extend(
        _normalize_native_event(event, run_manifest["scenario_name"])
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
