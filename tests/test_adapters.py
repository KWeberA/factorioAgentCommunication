from __future__ import annotations

import json
from pathlib import Path

from factorio_agent_bridge.adapters import advanced_biter_tactics, biter_aware_bot_pathing, biter_turret_defense, smart_combat_alarms
from factorio_agent_bridge.adapters.common import finalize_normalized_run
from factorio_agent_bridge.protocol import ensure_protocol_dirs


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _seed_harness_output(raw_root: Path, *, mod_name: str, scenario_name: str) -> None:
    harness_root = raw_root / "agent-bridge"
    _write_json(
        harness_root / "run-manifest.json",
        {
            "mod_name": mod_name,
            "scenario_name": scenario_name,
            "start_tick": 1,
            "end_tick": 240,
            "status": "passed",
        },
    )
    _write_json(
        harness_root / "assertions.json",
        [
            {"name": "bridge-smoke", "type": "invariant", "passed": True, "expected": True, "actual": True, "evidence": {}},
        ],
    )
    _write_json(
        harness_root / "frames" / "frame-30.json",
        {
            "tick": 30,
            "scenario_name": scenario_name,
        },
    )


def test_babp_adapter_normalizes_native_events_and_validation_summary(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    output_root = tmp_path / "out"
    _seed_harness_output(raw_root, mod_name="biter-aware-bot-pathing", scenario_name="full-validation")
    _write_jsonl(
        raw_root / "biter-aware-bot-pathing" / "bridge-events.jsonl",
        [
            {
                "tick": 45,
                "event": "deferred_task_detected",
                "category": "decision_made",
                "reason": "ghost-recheck",
                "subject_ids": {"surface": "nauvis"},
                "position": {"x": 2, "y": 5},
                "details": {"task_count": 3},
            }
        ],
    )
    _write_json(
        raw_root / "biter-aware-bot-pathing" / "validation-test-map.json",
        {
            "runs": 2,
            "failures": 0,
        },
    )

    summary = biter_aware_bot_pathing.normalize_run(raw_root, output_root)
    events = (output_root / "events.jsonl").read_text(encoding="utf-8").splitlines()

    assert summary["status"] == "passed"
    assert len(events) == 4
    assert any("validation_summary_loaded" in line for line in events)


def test_sca_adapter_preserves_alert_and_gui_categories(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    output_root = tmp_path / "out"
    _seed_harness_output(raw_root, mod_name="smart-combat-alarms", scenario_name="breach-confirmed")
    _write_jsonl(
        raw_root / "smart-combat-alarms" / "bridge-events.jsonl",
        [
            {
                "tick": 60,
                "event": "breach_confirmed",
                "category": "alert_triggered",
                "reason": "room-open",
                "details": {"room_id": 4},
            },
            {
                "tick": 61,
                "event": "prototype_mode_changed",
                "category": "gui_changed",
                "reason": "bridge-fixture",
                "details": {"prototype_name": "stone-wall", "mode": "breach"},
            },
        ],
    )

    smart_combat_alarms.normalize_run(raw_root, output_root)
    content = (output_root / "events.jsonl").read_text(encoding="utf-8")

    assert '"category": "alert_triggered"' in content
    assert '"category": "gui_changed"' in content


def test_btd_adapter_normalizes_wave_and_unlock_events(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    output_root = tmp_path / "out"
    _seed_harness_output(raw_root, mod_name="biter-turret-defense", scenario_name="unlock-path")
    _write_jsonl(
        raw_root / "biter-turret-defense" / "bridge-events.jsonl",
        [
            {
                "tick": 90,
                "event": "wave_started",
                "category": "wave_resolved",
                "reason": "scheduled-wave",
                "details": {"wave_number": 1},
            },
            {
                "tick": 140,
                "event": "unlock_purchased",
                "category": "decision_made",
                "reason": "action-plan",
                "details": {"unlock_id": "pocket-1", "coins_remaining": 20},
            },
        ],
    )

    biter_turret_defense.normalize_run(raw_root, output_root)
    content = (output_root / "events.jsonl").read_text(encoding="utf-8")

    assert '"event": "wave_started"' in content
    assert '"event": "unlock_purchased"' in content


def test_abt_adapter_promotes_legacy_groups_into_generic_combat_groups(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    output_root = tmp_path / "out"
    _seed_harness_output(raw_root, mod_name="advanced-biter-tactics", scenario_name="wall-covered-flank")
    _write_json(
        raw_root / "agent-bridge" / "assertions.json",
        [
            {
                "name": "no-coverage-before-breach",
                "type": "outcome",
                "passed": False,
                "expected": True,
                "actual": False,
                "evidence": {
                    "coverage_violation": {
                        "tick": 80,
                        "group_id": 7,
                    }
                },
            }
        ],
    )
    _write_json(
        raw_root / "agent-bridge" / "frames" / "frame-120.json",
        {
            "tick": 120,
            "scenario_name": "wall-covered-flank",
            "semantic_extensions": {
                "advanced_biter_tactics": {
                    "legacy_frame": {
                        "groups": [
                            {
                                "id": 7,
                                "role": "main",
                                "state": "tracking",
                                "group_position": {"x": -10, "y": 0},
                                "member_count": 12,
                                "state_since_tick": 0,
                                "state_duration_ticks": 30,
                                "last_meaningful_progress_tick": 0,
                                "in_turret_coverage": True,
                                "covering_turret_count": 2,
                                "coverage_sources": [{"name": "gun-turret"}],
                                "in_flame_hazard": False,
                                "hazard_score": 0,
                                "entry_progress": 0,
                                "breach_pressure_active": False,
                                "support_mode": "none",
                                "scenario": "wall-covered-flank",
                            }
                        ]
                    }
                }
            },
        },
    )
    _write_jsonl(
        raw_root / "advanced-biter-tactics" / "events.jsonl",
        [
            {
                "tick": 0,
                "event": "group_registered",
                "group_id": 7,
                "group_position": {"x": -10, "y": 0},
                "reason": "register",
                "state": "tracking",
            },
            {
                "tick": 5,
                "event": "contact_found",
                "group_id": 7,
                "contact_position": {"x": 0, "y": 0},
                "reason": "nearest-wall",
                "state": "tracking",
            },
            {
                "tick": 80,
                "event": "coverage_violation",
                "group_id": 7,
                "reason": "covered-path",
                "in_turret_coverage": True,
                "covering_turret_count": 2,
                "coverage_sources": [{"name": "gun-turret"}],
            },
            {
                "tick": 90,
                "event": "interior_target_selected",
                "group_id": 7,
                "reason": "interior-focus",
            },
        ],
    )

    advanced_biter_tactics.normalize_run(raw_root, output_root)
    frame = json.loads((output_root / "frames" / "frame-120.json").read_text(encoding="utf-8"))
    assertions = json.loads((output_root / "assertions.json").read_text(encoding="utf-8"))

    assert frame["observations"]["combat"]["groups"][0]["group_id"] == 7
    assert frame["observations"]["combat"]["groups"][0]["in_turret_coverage"] is True
    assert frame["semantic_extensions"]["advanced_biter_tactics"]["group_diagnostics"][0]["unsafe_before_breach"] is True
    assert frame["semantic_extensions"]["advanced_biter_tactics"]["group_diagnostics"][0]["interior_target_before_entry"] is True
    assert assertions[0]["related_group_ids"] == [7]
    assert 80 in assertions[0]["related_event_ticks"]


def test_finalize_normalized_run_marks_scenario_isolation_violations(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    artifacts = ensure_protocol_dirs(output_root)
    _write_json(
        artifacts.frames / "frame-10.json",
        {
            "tick": 10,
            "scenario_name": "wrong-scenario",
            "mod_name": "advanced-biter-tactics",
        },
    )

    summary = finalize_normalized_run(
        output_root,
        run_manifest={
            "mod_name": "advanced-biter-tactics",
            "scenario_name": "wall-open",
            "status": "passed",
            "phase": "complete",
        },
        assertions=[
            {
                "name": "bridge-smoke",
                "type": "invariant",
                "passed": True,
                "expected": True,
                "actual": True,
                "evidence": {},
            }
        ],
        normalized_events=[
            {
                "tick": 1,
                "category": "scenario_started",
                "event": "scenario_started",
                "mod_name": "advanced-biter-tactics",
                "scenario_name": "wall-open",
                "subject_ids": {},
                "position": None,
                "reason": "test",
                "details": {},
                "source": "harness",
            }
        ],
    )

    assert summary["status"] == "failed"
    assert "scenario-isolation-violation" in summary["failure_reasons"]


def test_abt_adapter_uses_legacy_frame_event_history_when_native_log_is_missing(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    output_root = tmp_path / "out"
    _seed_harness_output(raw_root, mod_name="advanced-biter-tactics", scenario_name="wall-open")
    _write_json(
        raw_root / "agent-bridge" / "frames" / "frame-120.json",
        {
            "tick": 120,
            "scenario_name": "wall-open",
            "semantic_extensions": {
                "advanced_biter_tactics": {
                    "legacy_frame": {
                        "groups": [],
                        "recent_events": [
                            {"tick": 0, "event": "group_registered", "group_id": 1, "reason": "register"},
                            {"tick": 5, "event": "contact_found", "group_id": 1, "reason": "nearest-wall"},
                        ],
                    }
                }
            },
        },
    )

    advanced_biter_tactics.normalize_run(raw_root, output_root)
    assertions = json.loads((output_root / "assertions.json").read_text(encoding="utf-8"))
    history_assertion = next(row for row in assertions if row["name"] == "semantic-history-retains-early-events")

    assert history_assertion["passed"] is True
