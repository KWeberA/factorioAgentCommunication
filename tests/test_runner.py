from __future__ import annotations

from pathlib import Path

import pytest

from factorio_agent_bridge.runner import (
    MOD_REGISTRY,
    _build_benchmark_args,
    _build_create_args,
    _parse_json_option,
    _write_harness_config,
)


def test_mod_registry_includes_all_supported_targets() -> None:
    assert set(MOD_REGISTRY.keys()) == {"abt", "babp", "sca", "btd"}


def test_write_harness_config_persists_setup_and_action_plan(tmp_path: Path) -> None:
    config_path = tmp_path / "config.lua"
    _write_harness_config(
        config_path,
        mod_name="biter-turret-defense",
        scenario_name="unlock-path",
        max_ticks=900,
        sample_interval=45,
        capture_radius=32,
        setup_options={
            "seed": "bridge-fixture",
            "action_plan": [
                {"tick": 120, "action": "purchase_unlock", "unlock_id": "pocket-1"},
                {"tick": 240, "action": "purchase_unlock", "unlock_id": "gate-1"},
            ],
        },
        assertion_options={
            "expected_phase": "combat",
        },
    )

    content = config_path.read_text(encoding="utf-8")
    assert 'scenario_name = "unlock-path"' in content
    assert 'mod_name = "biter-turret-defense"' in content
    assert "action_plan" in content
    assert "purchase_unlock" in content
    assert 'expected_phase = "combat"' in content


def test_parse_json_option_requires_object_payload() -> None:
    assert _parse_json_option('{"sample": true}') == {"sample": True}

    with pytest.raises(ValueError):
        _parse_json_option('["not", "an", "object"]')


def test_build_create_args_sets_seed_and_create_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "config.ini"
    mods_root = tmp_path / "mods"
    save_path = tmp_path / "save.zip"

    args = _build_create_args(config_path, mods_root, save_path)

    assert "--map-gen-seed" in args
    assert "424242" in args
    assert args[-2] == "--create"
    assert args[-1] == str(save_path)


def test_build_benchmark_args_runs_one_tick_past_target_and_ignores_paused(tmp_path: Path) -> None:
    config_path = tmp_path / "config.ini"
    mods_root = tmp_path / "mods"
    save_path = tmp_path / "save.zip"

    args = _build_benchmark_args(config_path, mods_root, save_path, 720)

    tick_index = args.index("--benchmark-ticks")
    assert args[tick_index + 1] == "721"
    assert "--benchmark-ignore-paused" in args
    assert "--benchmark-sanitize" not in args
