from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factorio_agent_bridge.adapters import advanced_biter_tactics, biter_aware_bot_pathing, biter_turret_defense, smart_combat_alarms
from factorio_agent_bridge.adapters.common import standard_diff_runs


REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_SOURCE = REPO_ROOT / "mods" / "agentBridgeHarness"
WORKSPACE_ROOT = REPO_ROOT / ".agent-bridge"
RUNS_ROOT = REPO_ROOT / "runs"

MOD_REGISTRY = {
    "abt": {
        "adapter": advanced_biter_tactics,
        "enabled_builtin_mods": ["base"],
    },
    "babp": {
        "adapter": biter_aware_bot_pathing,
        "enabled_builtin_mods": ["base"],
    },
    "sca": {
        "adapter": smart_combat_alarms,
        "enabled_builtin_mods": ["base"],
    },
    "btd": {
        "adapter": biter_turret_defense,
        "enabled_builtin_mods": ["base"],
    },
}


def _read_info_json(mod_root: Path) -> dict[str, Any]:
    return json.loads((mod_root / "info.json").read_text(encoding="utf-8"))


def _write_config_ini(path: Path, write_data_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join([
        "; version=13",
        "[path]",
        "read-data=__PATH__system-read-data__",
        f"write-data={write_data_root.as_posix()}",
        "",
        "[general]",
        "locale=en",
        "",
        "[other]",
        "verbose-logging=true",
        "",
    ])
    path.write_text(content, encoding="ascii")


def _copy_tree(source: Path, target: Path, *, excluded_names: set[str] | None = None) -> None:
    excluded_names = excluded_names or set()
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name in excluded_names:
            continue
        destination = target / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def _write_mod_list(path: Path, target_mod_name: str, harness_mod_name: str, enabled_builtin_mods: list[str]) -> None:
    write_payload = {
        "mods": [
            *({"name": mod_name, "enabled": True} for mod_name in enabled_builtin_mods),
            {"name": harness_mod_name, "enabled": True},
            {"name": target_mod_name, "enabled": True},
        ]
    }
    path.write_text(json.dumps(write_payload, indent=2), encoding="utf-8")


def _to_lua(value: Any) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "{ " + ", ".join(_to_lua(item) for item in value) + " }"
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            items.append(f"{key} = {_to_lua(item)}")
        return "{ " + ", ".join(items) + " }"
    raise TypeError(f"Unsupported Lua conversion value: {value!r}")


def _write_harness_config(
    path: Path,
    *,
    mod_name: str,
    scenario_name: str,
    max_ticks: int,
    sample_interval: int,
    capture_radius: int,
    setup_options: dict[str, Any],
    assertion_options: dict[str, Any],
) -> None:
    payload = {
        "mod_name": mod_name,
        "scenario_name": scenario_name,
        "max_ticks": max_ticks,
        "sample_interval": sample_interval,
        "capture_options": {
            "radius": capture_radius,
        },
        "setup_options": setup_options,
        "assertion_options": assertion_options,
    }
    lines = [
        "return {",
        f"  mod_name = {_to_lua(payload['mod_name'])},",
        f"  scenario_name = {_to_lua(payload['scenario_name'])},",
        f"  max_ticks = {payload['max_ticks']},",
        f"  sample_interval = {payload['sample_interval']},",
        f"  setup_options = {_to_lua(payload['setup_options'])},",
        f"  assertion_options = {_to_lua(payload['assertion_options'])},",
        f"  capture_options = {_to_lua(payload['capture_options'])}",
        "}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_create_args(config_path: Path, mods_root: Path, save_path: Path) -> list[str]:
    return [
        "--config",
        str(config_path),
        "--mod-directory",
        str(mods_root),
        "--disable-audio",
        "--map-gen-seed",
        "424242",
        "--create",
        str(save_path),
    ]


def _build_benchmark_args(config_path: Path, mods_root: Path, save_path: Path, max_ticks: int) -> list[str]:
    return [
        "--config",
        str(config_path),
        "--mod-directory",
        str(mods_root),
        "--disable-audio",
        "--benchmark",
        str(save_path),
        "--benchmark-ticks",
        str(max_ticks + 1),
        "--benchmark-runs",
        "1",
        "--benchmark-ignore-paused",
    ]


def _run_factorio(factorio_exe: Path, args: list[str], *, cwd: Path | None = None) -> None:
    completed = subprocess.run([str(factorio_exe), *args], check=False, cwd=cwd)
    if completed.returncode != 0:
        raise RuntimeError(f"Factorio failed with exit code {completed.returncode}: {' '.join(args)}")


def run_mod_scenario(
    *,
    mod_key: str,
    factorio_exe: Path,
    target_mod_root: Path,
    scenario_name: str,
    max_ticks: int,
    sample_interval: int,
    capture_radius: int,
    setup_options: dict[str, Any],
    assertion_options: dict[str, Any],
) -> Path:
    if mod_key not in MOD_REGISTRY:
        raise KeyError(f"Unknown mod key: {mod_key}")

    mod_entry = MOD_REGISTRY[mod_key]
    adapter = mod_entry["adapter"]
    info = _read_info_json(target_mod_root)
    target_mod_name = info["name"]
    target_mod_version = info["version"]
    harness_info = _read_info_json(HARNESS_SOURCE)
    harness_mod_name = harness_info["name"]
    harness_mod_version = harness_info["version"]

    runtime_root = WORKSPACE_ROOT / "workspaces" / mod_key
    mods_root = runtime_root / "mods"
    config_root = runtime_root / "config"
    saves_root = runtime_root / "saves"
    raw_script_output_root = runtime_root / "script-output"
    config_path = config_root / "config.ini"
    save_path = saves_root / "agent-bridge.zip"

    for directory in (mods_root, config_root, saves_root, raw_script_output_root):
        directory.mkdir(parents=True, exist_ok=True)

    _write_config_ini(config_path, runtime_root)

    target_mod_dir = mods_root / f"{target_mod_name}_{target_mod_version}"
    _copy_tree(
        target_mod_root,
        target_mod_dir,
        excluded_names={".git", ".vscode", ".factorio-test", ".factorio-validation"},
    )

    harness_mod_dir = mods_root / f"{harness_mod_name}_{harness_mod_version}"
    _copy_tree(HARNESS_SOURCE, harness_mod_dir)
    _write_harness_config(
        harness_mod_dir / "config.lua",
        mod_name=target_mod_name,
        scenario_name=scenario_name,
        max_ticks=max_ticks,
        sample_interval=sample_interval,
        capture_radius=capture_radius,
        setup_options=setup_options,
        assertion_options=assertion_options,
    )
    _write_mod_list(
        mods_root / "mod-list.json",
        target_mod_name,
        harness_mod_name,
        enabled_builtin_mods=mod_entry["enabled_builtin_mods"],
    )

    if save_path.exists():
        save_path.unlink()
    if raw_script_output_root.exists():
        shutil.rmtree(raw_script_output_root)
        raw_script_output_root.mkdir(parents=True, exist_ok=True)

    _run_factorio(
        factorio_exe,
        _build_create_args(config_path, mods_root, save_path),
        cwd=REPO_ROOT,
    )
    _run_factorio(
        factorio_exe,
        _build_benchmark_args(config_path, mods_root, save_path, max_ticks),
        cwd=REPO_ROOT,
    )

    raw_manifest = raw_script_output_root / "agent-bridge" / "run-manifest.json"
    if not raw_manifest.exists():
        raise FileNotFoundError(f"Harness output missing: {raw_manifest}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = RUNS_ROOT / f"{run_id}-{scenario_name}"
    adapter.normalize_run(raw_script_output_root, output_root)
    return output_root


def _parse_json_option(raw_value: str) -> dict[str, Any]:
    payload = json.loads(raw_value)
    if not isinstance(payload, dict):
        raise ValueError("JSON option payloads must decode to objects")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factorio-agent-bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a bridge-integrated mod scenario")
    run_parser.add_argument("--mod", required=True, choices=sorted(MOD_REGISTRY.keys()))
    run_parser.add_argument("--factorio-exe", required=True, type=Path)
    run_parser.add_argument("--target-mod-root", required=True, type=Path)
    run_parser.add_argument("--scenario", required=True)
    run_parser.add_argument("--max-ticks", type=int, default=720)
    run_parser.add_argument("--sample-interval", type=int, default=30)
    run_parser.add_argument("--capture-radius", type=int, default=48)
    run_parser.add_argument("--setup-options-json", default="{}")
    run_parser.add_argument("--assertion-options-json", default="{}")

    legacy_run_parser = subparsers.add_parser("run-abt", help="Backward compatible ABT bridge command")
    legacy_run_parser.add_argument("--factorio-exe", required=True, type=Path)
    legacy_run_parser.add_argument("--target-mod-root", required=True, type=Path)
    legacy_run_parser.add_argument("--scenario", required=True)
    legacy_run_parser.add_argument("--max-ticks", type=int, default=720)
    legacy_run_parser.add_argument("--sample-interval", type=int, default=30)
    legacy_run_parser.add_argument("--capture-radius", type=int, default=48)

    diff_parser = subparsers.add_parser("diff", help="Diff two normalized runs")
    diff_parser.add_argument("--left", required=True, type=Path)
    diff_parser.add_argument("--right", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "run":
        output_root = run_mod_scenario(
            mod_key=args.mod,
            factorio_exe=args.factorio_exe,
            target_mod_root=args.target_mod_root,
            scenario_name=args.scenario,
            max_ticks=args.max_ticks,
            sample_interval=args.sample_interval,
            capture_radius=args.capture_radius,
            setup_options=_parse_json_option(args.setup_options_json),
            assertion_options=_parse_json_option(args.assertion_options_json),
        )
        print(output_root)
        return 0

    if args.command == "run-abt":
        output_root = run_mod_scenario(
            mod_key="abt",
            factorio_exe=args.factorio_exe,
            target_mod_root=args.target_mod_root,
            scenario_name=args.scenario,
            max_ticks=args.max_ticks,
            sample_interval=args.sample_interval,
            capture_radius=args.capture_radius,
            setup_options={},
            assertion_options={},
        )
        print(output_root)
        return 0

    if args.command == "diff":
        print(json.dumps(standard_diff_runs(args.left, args.right), indent=2))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
