from __future__ import annotations

from pathlib import Path
from typing import Any

from factorio_agent_bridge.protocol import (
    build_summary,
    ensure_protocol_dirs,
    list_frames,
    load_json,
    load_jsonl,
    write_json,
    write_jsonl,
)


NATIVE_DIR = "advanced-biter-tactics"
HARNESS_DIR = "agent-bridge"


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
    artifacts = ensure_protocol_dirs(output_root)
    harness_root = raw_script_output_root / HARNESS_DIR
    native_root = raw_script_output_root / NATIVE_DIR

    run_manifest = load_json(harness_root / "run-manifest.json")
    assertions = load_json(harness_root / "assertions.json")

    native_events = load_jsonl(native_root / "events.jsonl")
    normalized_events = [
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
        }
    ]
    normalized_events.extend(
        _normalize_native_event(event, run_manifest["scenario_name"])
        for event in native_events
    )
    normalized_events.append(
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
        }
    )

    write_json(artifacts.run_manifest, run_manifest)
    write_json(artifacts.assertions, assertions)
    write_jsonl(artifacts.events, normalized_events)

    raw_frames_dir = harness_root / "frames"
    for frame_path in list_frames(raw_frames_dir):
        write_json(artifacts.frames / frame_path.name, load_json(frame_path))

    summary = build_summary(
        run_manifest=run_manifest,
        assertions=assertions,
        frame_count=len(list_frames(artifacts.frames)),
        event_count=len(normalized_events),
        failure_reasons=[assertion["name"] for assertion in assertions if not assertion.get("passed")],
    )
    write_json(artifacts.summary, summary)
    return summary


def diff_runs(left_root: Path, right_root: Path) -> dict[str, Any]:
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
