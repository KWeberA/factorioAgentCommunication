from __future__ import annotations

import json
from pathlib import Path

from factorio_agent_bridge.adapters import biter_aware_bot_pathing, biter_turret_defense, smart_combat_alarms


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
    assert "validation_summary_loaded" in events[2]


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
