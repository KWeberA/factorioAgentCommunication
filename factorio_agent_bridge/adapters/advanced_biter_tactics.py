from __future__ import annotations

from pathlib import Path
from typing import Any

from factorio_agent_bridge.adapters.common import (
    copy_harness_outputs,
    finalize_normalized_run,
    load_json,
    load_optional_jsonl,
    merge_events,
    standard_diff_runs,
)
from factorio_agent_bridge.protocol import list_frames, write_json


NATIVE_DIR = "advanced-biter-tactics"
STALL_TIMEOUT_TICKS = 360
EARLY_EVENT_REQUIREMENTS = {
    "wall-open": ["group_registered", "contact_found"],
    "wall-covered-flank": ["group_registered", "contact_found"],
    "breach-reuse": ["arena_wave_spawned", "group_registered"],
}


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
    "breach_pressure_updated": "entity_damaged",
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
    "coverage_violation": "decision_made",
    "state_stalled": "decision_made",
    "entry_progress_updated": "breach_opened",
}


def _normalize_native_event(event: dict[str, Any], scenario_name: str, source_event_index: int) -> dict[str, Any]:
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
            "entry_progress": event.get("entry_progress"),
            "coverage_sources": event.get("coverage_sources"),
            "covering_turret_count": event.get("covering_turret_count"),
            "in_turret_coverage": event.get("in_turret_coverage"),
            "in_flame_hazard": event.get("in_flame_hazard"),
            "hazard_score": event.get("hazard_score"),
            "last_meaningful_progress_tick": event.get("last_meaningful_progress_tick"),
        },
        "source": "mod-semantic",
        "source_event_index": source_event_index,
    }


def _build_group_event_flags(events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    flags: dict[int, dict[str, Any]] = {}
    for event in events:
        group_id = event.get("group_id")
        if not isinstance(group_id, int):
            continue
        row = flags.setdefault(
            group_id,
            {
                "first_inside_entry_tick": None,
                "first_interior_target_tick": None,
            },
        )
        if event.get("event") == "entry_progress_updated" and event.get("reason") == "inside" and row["first_inside_entry_tick"] is None:
            row["first_inside_entry_tick"] = event.get("tick")
        if event.get("event") == "interior_target_selected" and row["first_interior_target_tick"] is None:
            row["first_interior_target_tick"] = event.get("tick")
    return flags


def _load_semantic_events(native_root: Path, output_root: Path) -> list[dict[str, Any]]:
    native_events = load_optional_jsonl(native_root / "events.jsonl")
    if native_events:
        return native_events

    latest_tick = -1
    latest_events: list[dict[str, Any]] = []
    for frame_path in list_frames(output_root / "frames"):
        frame = load_json(frame_path)
        legacy_frame = (
            frame.get("semantic_extensions", {})
            .get("advanced_biter_tactics", {})
            .get("legacy_frame")
        ) or {}
        recent_events = legacy_frame.get("recent_events") or []
        tick = frame.get("tick") or -1
        if recent_events and tick >= latest_tick:
            latest_tick = tick
            latest_events = recent_events
    return latest_events


def _normalize_group(group: dict[str, Any], frame_tick: int, group_event_flags: dict[int, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    state_since_tick = group.get("state_since_tick")
    state_duration_ticks = group.get("state_duration_ticks")
    if state_duration_ticks is None and state_since_tick is not None:
        state_duration_ticks = max(frame_tick - state_since_tick, 0)
    last_meaningful_progress_tick = group.get("last_meaningful_progress_tick")
    progress_stalled = False
    if last_meaningful_progress_tick is not None:
        progress_stalled = (frame_tick - last_meaningful_progress_tick) >= STALL_TIMEOUT_TICKS

    entry_progress = group.get("entry_progress")
    unsafe_before_breach = bool(group.get("in_turret_coverage")) and (entry_progress is None or entry_progress <= 0)
    inside_cone_violation = group.get("support_mode") == "cone-siege" and bool(group.get("in_turret_coverage"))
    group_flags = group_event_flags.get(group.get("id"), {})
    first_inside_entry_tick = group_flags.get("first_inside_entry_tick")
    first_interior_target_tick = group_flags.get("first_interior_target_tick")
    interior_target_before_entry = (
        first_interior_target_tick is not None
        and (first_inside_entry_tick is None or first_interior_target_tick < first_inside_entry_tick)
        and first_interior_target_tick <= frame_tick
    )

    normalized = {
        "group_id": group.get("id"),
        "role": group.get("role"),
        "state": group.get("state"),
        "position": group.get("group_position"),
        "member_count": group.get("member_count"),
        "state_since_tick": state_since_tick,
        "state_duration_ticks": state_duration_ticks,
        "last_meaningful_progress_tick": last_meaningful_progress_tick,
        "in_turret_coverage": group.get("in_turret_coverage"),
        "covering_turret_count": group.get("covering_turret_count"),
        "coverage_sources": group.get("coverage_sources") or [],
        "in_flame_hazard": group.get("in_flame_hazard"),
        "hazard_score": group.get("hazard_score"),
        "entry_progress": entry_progress,
        "breach_pressure_active": group.get("breach_pressure_active"),
        "support_mode": group.get("support_mode"),
        "scenario": group.get("scenario"),
    }
    diagnostics = {
        "group_id": group.get("id"),
        "progress_stalled": progress_stalled,
        "unsafe_before_breach": unsafe_before_breach,
        "inside_cone_violation": inside_cone_violation,
        "interior_target_before_entry": interior_target_before_entry,
    }
    return normalized, diagnostics


def _promote_abt_frames(output_root: Path, scenario_name: str, native_events: list[dict[str, Any]]) -> dict[str, Any]:
    aggregated = {
        "groups_with_coverage": set(),
        "groups_stalled": set(),
        "support_modes": {},
    }
    group_event_flags = _build_group_event_flags(native_events)
    for frame_path in list_frames(output_root / "frames"):
        frame = load_json(frame_path)
        legacy_frame = (
            frame.get("semantic_extensions", {})
            .get("advanced_biter_tactics", {})
            .get("legacy_frame")
        )
        if not legacy_frame:
            continue
        groups = legacy_frame.get("groups") or []
        generic_groups = []
        diagnostics = []
        for group in groups:
            normalized_group, group_diagnostics = _normalize_group(group, frame.get("tick") or 0, group_event_flags)
            generic_groups.append(normalized_group)
            diagnostics.append(group_diagnostics)
            if normalized_group.get("in_turret_coverage"):
                aggregated["groups_with_coverage"].add(normalized_group["group_id"])
            if group_diagnostics.get("progress_stalled"):
                aggregated["groups_stalled"].add(normalized_group["group_id"])
            if normalized_group.get("support_mode") is not None:
                aggregated["support_modes"][normalized_group["group_id"]] = normalized_group.get("support_mode")

        frame.setdefault("observations", {})
        frame["observations"].setdefault("combat", {})
        frame["observations"]["combat"]["groups"] = generic_groups
        frame.setdefault("semantic_extensions", {}).setdefault("advanced_biter_tactics", {})
        frame["semantic_extensions"]["advanced_biter_tactics"]["group_diagnostics"] = diagnostics
        frame["scenario_name"] = scenario_name
        write_json(frame_path, frame)
    return aggregated


def _first_event(events: list[dict[str, Any]], event_name: str, *, reason: str | None = None, support_mode: str | None = None) -> dict[str, Any] | None:
    for event in events:
        if event.get("event") != event_name:
            continue
        if reason is not None and event.get("reason") != reason:
            continue
        details = event.get("details") or {}
        if support_mode is not None and details.get("support_mode") != support_mode:
            continue
        return event
    return None


def _find_first_group_tick(frames_dir: Path, predicate) -> int | None:
    for frame_path in list_frames(frames_dir):
        frame = load_json(frame_path)
        for group in frame.get("observations", {}).get("combat", {}).get("groups", []):
            if predicate(group):
                return frame.get("tick")
    return None


def _collect_group_ids(value: Any) -> set[int]:
    group_ids: set[int] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"group_id", "support_group_id"} and isinstance(item, int):
                group_ids.add(item)
            else:
                group_ids.update(_collect_group_ids(item))
    elif isinstance(value, list):
        for item in value:
            group_ids.update(_collect_group_ids(item))
    return group_ids


def _collect_event_ticks(value: Any) -> set[int]:
    ticks: set[int] = set()
    if isinstance(value, dict):
        if "tick" in value and isinstance(value["tick"], int):
            ticks.add(value["tick"])
        for item in value.values():
            ticks.update(_collect_event_ticks(item))
    elif isinstance(value, list):
        for item in value:
            ticks.update(_collect_event_ticks(item))
    return ticks


def _ensure_event_history_assertions(
    run_manifest: dict[str, Any],
    native_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    event_names = [event.get("event") for event in native_events]
    required_events = EARLY_EVENT_REQUIREMENTS.get(run_manifest["scenario_name"], ["group_registered"])
    missing = [event_name for event_name in required_events if event_name not in event_names]
    return [
        {
            "name": "semantic-history-retains-early-events",
            "type": "outcome",
            "passed": len(missing) == 0,
            "expected": required_events,
            "actual": event_names[: max(len(required_events), 4)],
            "evidence": {
                "missing": missing,
                "first_native_event": native_events[0] if native_events else None,
            },
            "mod_name": run_manifest["mod_name"],
            "scenario_name": run_manifest["scenario_name"],
            "related_group_ids": [],
            "related_event_ticks": [native_events[0]["tick"]] if native_events else [],
        }
    ]


def _enrich_assertions(
    assertions: list[dict[str, Any]],
    *,
    events: list[dict[str, Any]],
    frames_dir: Path,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    first_coverage_violation = _first_event(events, "coverage_violation")
    first_support_stall = _first_event(events, "state_stalled")
    first_inside_entry = _first_event(events, "entry_progress_updated", reason="inside")
    first_interior_target = _first_event(events, "interior_target_selected")
    first_cone_coverage_violation = _first_event(events, "coverage_violation", support_mode="cone-siege")

    for assertion in assertions:
        row = dict(assertion)
        evidence = dict(row.get("evidence") or {})
        related_group_ids = set(row.get("related_group_ids") or [])
        related_group_ids.update(_collect_group_ids(evidence))
        related_event_ticks = set(row.get("related_event_ticks") or [])
        related_event_ticks.update(_collect_event_ticks(evidence))

        if row["name"] == "no-coverage-before-breach":
            violating_tick = _find_first_group_tick(frames_dir, lambda group: bool(group.get("in_turret_coverage")) and (group.get("entry_progress") is None or group.get("entry_progress", 0) <= 0))
            evidence["first_violating_event"] = first_coverage_violation
            evidence["first_violating_group_snapshot_tick"] = violating_tick
        elif row["name"] == "support-progress-within-threshold":
            stalled_tick = _find_first_group_tick(frames_dir, lambda group: bool(group.get("support_mode")) and group.get("state_duration_ticks") is not None and group.get("state_duration_ticks") >= STALL_TIMEOUT_TICKS)
            evidence["first_violating_event"] = first_support_stall
            evidence["first_violating_group_snapshot_tick"] = stalled_tick
        elif row["name"] == "reuse-entered-before-interior-target":
            violating_tick = _find_first_group_tick(frames_dir, lambda group: group.get("entry_progress") is None or group.get("entry_progress", 0) <= 0)
            evidence["first_violating_event"] = first_interior_target if (first_interior_target and not first_inside_entry) else None
            evidence["first_violating_group_snapshot_tick"] = violating_tick
        elif row["name"] == "cone-outside-flame-range":
            violating_tick = _find_first_group_tick(frames_dir, lambda group: group.get("support_mode") == "cone-siege" and bool(group.get("in_turret_coverage")))
            evidence["first_violating_event"] = first_cone_coverage_violation
            evidence["first_violating_group_snapshot_tick"] = violating_tick

        row["evidence"] = evidence
        row["related_group_ids"] = sorted(related_group_ids)
        row["related_event_ticks"] = sorted(related_event_ticks)
        enriched.append(row)
    return enriched


def _event_history_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    group_coverage = set()
    stalled_groups = set()
    support_modes = {}
    breach_pressure_tick = None
    entry_inside_tick = None
    interior_target_tick = None

    for event in events:
        details = event.get("details") or {}
        subject_ids = event.get("subject_ids") or {}
        group_id = subject_ids.get("group_id")
        if details.get("in_turret_coverage"):
            group_coverage.add(group_id)
        if event.get("event") == "state_stalled":
            stalled_groups.add(group_id)
        if details.get("support_mode") is not None:
            support_modes[group_id] = details.get("support_mode")
        if event.get("event") == "breach_pressure_detected" and breach_pressure_tick is None:
            breach_pressure_tick = event.get("tick")
        if event.get("event") == "entry_progress_updated" and event.get("reason") == "inside" and entry_inside_tick is None:
            entry_inside_tick = event.get("tick")
        if event.get("event") == "interior_target_selected" and interior_target_tick is None:
            interior_target_tick = event.get("tick")

    return {
        "groups_with_coverage": sorted(group_id for group_id in group_coverage if group_id is not None),
        "groups_stalled": sorted(group_id for group_id in stalled_groups if group_id is not None),
        "support_modes": {str(group_id): mode for group_id, mode in support_modes.items() if group_id is not None},
        "first_breach_pressure_tick": breach_pressure_tick,
        "entry_progress_order": {
            "inside_entry_tick": entry_inside_tick,
            "interior_target_tick": interior_target_tick,
        },
    }


def _frame_semantic_summary(root: Path) -> dict[str, Any]:
    groups_with_coverage = set()
    groups_stalled = set()
    support_modes: dict[str, Any] = {}
    for frame_path in list_frames(root / "frames"):
        frame = load_json(frame_path)
        combat_groups = frame.get("observations", {}).get("combat", {}).get("groups", [])
        diagnostics = {
            row.get("group_id"): row
            for row in frame.get("semantic_extensions", {}).get("advanced_biter_tactics", {}).get("group_diagnostics", [])
            if row.get("group_id") is not None
        }
        for group in combat_groups:
            group_id = group.get("group_id")
            if group_id is None:
                continue
            if group.get("in_turret_coverage"):
                groups_with_coverage.add(group_id)
            if diagnostics.get(group_id, {}).get("progress_stalled"):
                groups_stalled.add(group_id)
            if group.get("support_mode") is not None:
                support_modes[str(group_id)] = group.get("support_mode")
    return {
        "groups_with_coverage": sorted(groups_with_coverage),
        "groups_stalled": sorted(groups_stalled),
        "support_modes": support_modes,
    }


def normalize_run(raw_script_output_root: Path, output_root: Path) -> dict[str, Any]:
    native_root = raw_script_output_root / NATIVE_DIR

    run_manifest, assertions, _, harness_events = copy_harness_outputs(raw_script_output_root, output_root)

    native_events = _load_semantic_events(native_root, output_root)
    normalized_native_events = [
        _normalize_native_event(event, run_manifest["scenario_name"], source_event_index=index)
        for index, event in enumerate(native_events)
    ]
    normalized_events = merge_events(harness_events, normalized_native_events)
    promoted = _promote_abt_frames(output_root, run_manifest["scenario_name"], native_events)
    assertions = assertions + _ensure_event_history_assertions(run_manifest, native_events)
    assertions = _enrich_assertions(assertions, events=normalized_events, frames_dir=output_root / "frames")
    summary = finalize_normalized_run(
        output_root,
        run_manifest=run_manifest,
        assertions=assertions,
        normalized_events=normalized_events,
    )

    metrics_path = output_root / "metrics.json"
    metrics = load_json(metrics_path)
    metrics["semantic"] = {
        "abt": {
            "groups_with_coverage": sorted(promoted["groups_with_coverage"]),
            "groups_stalled": sorted(promoted["groups_stalled"]),
            "support_modes": {str(key): value for key, value in promoted["support_modes"].items()},
        }
    }
    write_json(metrics_path, metrics)
    return summary


def diff_runs(left_root: Path, right_root: Path) -> dict[str, Any]:
    diff = standard_diff_runs(left_root, right_root)
    left_events = load_optional_jsonl(left_root / "events.jsonl")
    right_events = load_optional_jsonl(right_root / "events.jsonl")
    left_frames = _frame_semantic_summary(left_root)
    right_frames = _frame_semantic_summary(right_root)
    left_summary = _event_history_summary(left_events)
    right_summary = _event_history_summary(right_events)

    diff["semantic_diff"]["abt"] = {
        "groups_newly_entering_turret_coverage": sorted(set(right_frames["groups_with_coverage"]) - set(left_frames["groups_with_coverage"])),
        "groups_no_longer_entering_turret_coverage": sorted(set(left_frames["groups_with_coverage"]) - set(right_frames["groups_with_coverage"])),
        "groups_newly_stalled": sorted(set(right_frames["groups_stalled"]) - set(left_frames["groups_stalled"])),
        "groups_no_longer_stalled": sorted(set(left_frames["groups_stalled"]) - set(right_frames["groups_stalled"])),
        "support_mode_changes": {
            "left": left_frames["support_modes"] or left_summary["support_modes"],
            "right": right_frames["support_modes"] or right_summary["support_modes"],
        },
        "breach_pressure_timing_changes": {
            "left_first_breach_pressure_tick": left_summary["first_breach_pressure_tick"],
            "right_first_breach_pressure_tick": right_summary["first_breach_pressure_tick"],
        },
        "entry_progress_ordering_changes": {
            "left": left_summary["entry_progress_order"],
            "right": right_summary["entry_progress_order"],
        },
    }
    return diff
