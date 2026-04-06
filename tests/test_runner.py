from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from factorio_agent_bridge.runner import (
    MOD_REGISTRY,
    _build_benchmark_args,
    _build_create_args,
    _load_plan_file,
    _parse_json_option,
    _parse_json_list_option,
    _write_harness_config,
    describe_mod,
    run_mod_scenario,
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
        capabilities=["world", "entities", "events"],
        capability_options={
            "entities": {"limit": 12},
        },
        setup_options={
            "seed": "bridge-fixture",
            "action_plan": [
                {"tick": 120, "action": "purchase_unlock", "unlock_id": "pocket-1"},
                {"tick": 240, "action": "purchase_unlock", "unlock_id": "gate-1"},
            ],
        },
        action_plan=[
            {"tick": 60, "action": "emit_frame"},
            {"tick": 90, "action": "wait_until", "condition": {"kind": "event", "event": "wave_started"}},
        ],
        assertion_options={
            "expected_phase": "combat",
        },
        waits=[],
        event_filters={"categories": ["wave_resolved", "decision_made"]},
        frame_filters={"include_semantic_extensions": True},
    )

    content = config_path.read_text(encoding="utf-8")
    assert 'scenario_name = "unlock-path"' in content
    assert 'mod_name = "biter-turret-defense"' in content
    assert "action_plan" in content
    assert "purchase_unlock" in content
    assert "capabilities" in content
    assert "wait_until" in content
    assert 'expected_phase = "combat"' in content


def test_parse_json_option_requires_object_payload() -> None:
    assert _parse_json_option('{"sample": true}') == {"sample": True}

    with pytest.raises(ValueError):
        _parse_json_option('["not", "an", "object"]')


def test_parse_json_list_option_requires_array_payload() -> None:
    assert _parse_json_list_option('["world", "events"]') == ["world", "events"]

    with pytest.raises(ValueError):
        _parse_json_list_option('{"not": "an array"}')


def test_load_plan_file_requires_object_payload(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text('{"scenario_name":"bridge-world","capabilities":["world"]}', encoding="utf-8")

    assert _load_plan_file(plan_path)["scenario_name"] == "bridge-world"

    plan_path.write_text('["invalid"]', encoding="utf-8")
    with pytest.raises(ValueError):
        _load_plan_file(plan_path)


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


def test_describe_mod_reports_v2_capabilities() -> None:
    description = describe_mod(mod_key="sca")

    assert description["version"] == "2.0"
    assert "world" in description["capabilities"]
    assert "wait_until" in description["actions"]
    assert "config_fields" in description


def test_run_mod_scenario_writes_failure_package_for_create_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target_mod_root = tmp_path / "mod"
    target_mod_root.mkdir()
    (target_mod_root / "info.json").write_text('{"name":"fixture-mod","version":"1.0.0"}', encoding="utf-8")

    import factorio_agent_bridge.runner as runner_module

    monkeypatch.setattr(runner_module, "WORKSPACE_ROOT", tmp_path / ".agent-bridge")
    monkeypatch.setattr(runner_module, "RUNS_ROOT", tmp_path / "runs")

    def fake_run_factorio(*args, **kwargs):
        runtime_root = runner_module.WORKSPACE_ROOT / "workspaces"
        runtime_root.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(args=["factorio"], returncode=1, stdout="create failed", stderr="stack")

    monkeypatch.setattr(runner_module, "_run_factorio", fake_run_factorio)

    output_root = run_mod_scenario(
        mod_key="abt",
        factorio_exe=Path("factorio.exe"),
        target_mod_root=target_mod_root,
        scenario_name="wall-open",
        max_ticks=120,
        sample_interval=30,
        capture_radius=48,
        capabilities=["world"],
        capability_options={},
        setup_options={},
        action_plan=[],
        assertion_options={},
        waits=[],
        event_filters={},
        frame_filters={},
    )

    assert (output_root / "failure.json").exists()
    assert (output_root / "summary.json").exists()
    assert (output_root / "run-manifest.json").exists()
    assert (output_root / "events.jsonl").exists()
    assert (output_root / "assertions.json").exists()


def test_run_mod_scenario_rewrites_malformed_partial_artifacts_in_failure_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target_mod_root = tmp_path / "mod"
    target_mod_root.mkdir()
    (target_mod_root / "info.json").write_text('{"name":"fixture-mod","version":"1.0.0"}', encoding="utf-8")

    import factorio_agent_bridge.runner as runner_module

    monkeypatch.setattr(runner_module, "WORKSPACE_ROOT", tmp_path / ".agent-bridge")
    monkeypatch.setattr(runner_module, "RUNS_ROOT", tmp_path / "runs")

    def fake_run_factorio(*args, **kwargs):
        factorio_args = args[1]
        config_path = Path(factorio_args[factorio_args.index("--config") + 1])
        runtime_root = config_path.parent.parent
        harness_root = runtime_root / "script-output" / "agent-bridge"
        harness_root.mkdir(parents=True, exist_ok=True)
        (harness_root / "assertions.json").write_text('{"broken": ', encoding="utf-8")
        (harness_root / "events.jsonl").write_text('{"tick":1}\n{"tick":', encoding="utf-8")
        return subprocess.CompletedProcess(args=["factorio"], returncode=1, stdout="create failed", stderr="stack")

    monkeypatch.setattr(runner_module, "_run_factorio", fake_run_factorio)

    output_root = run_mod_scenario(
        mod_key="abt",
        factorio_exe=Path("factorio.exe"),
        target_mod_root=target_mod_root,
        scenario_name="wall-covered-flank",
        max_ticks=120,
        sample_interval=30,
        capture_radius=48,
        capabilities=["world"],
        capability_options={},
        setup_options={},
        action_plan=[],
        assertion_options={},
        waits=[],
        event_filters={},
        frame_filters={},
    )

    assertions_payload = (output_root / "assertions.json").read_text(encoding="utf-8")
    events_payload = (output_root / "events.jsonl").read_text(encoding="utf-8")

    assert assertions_payload.strip() == "[]"
    assert events_payload.strip() == '{"tick": 1}'
