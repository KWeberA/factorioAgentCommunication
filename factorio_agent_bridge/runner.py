from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factorio_agent_bridge.adapters import advanced_biter_tactics, biter_aware_bot_pathing, biter_turret_defense, smart_combat_alarms
from factorio_agent_bridge.adapters.common import load_optional_json, standard_diff_runs
from factorio_agent_bridge.protocol import ensure_protocol_dirs, list_frames, write_json, write_jsonl
from factorio_agent_bridge.v2 import ACTION_REGISTRY, CAPABILITY_REGISTRY, DEFAULT_CAPABILITIES, RUN_CONFIG_FIELDS, build_bridge_description


REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_SOURCE = REPO_ROOT / "mods" / "agentBridgeHarness"
WORKSPACE_ROOT = REPO_ROOT / ".agent-bridge"
RUNS_ROOT = REPO_ROOT / "runs"

MOD_REGISTRY = {
    "abt": {
        "adapter": advanced_biter_tactics,
        "enabled_builtin_mods": ["base"],
        "semantic_namespace": "advanced_biter_tactics",
        "canonical_scenarios": ["wall-open", "wall-covered-flank", "breach-reuse"],
        "default_capabilities": DEFAULT_CAPABILITIES,
    },
    "babp": {
        "adapter": biter_aware_bot_pathing,
        "enabled_builtin_mods": ["base"],
        "semantic_namespace": "biter_aware_bot_pathing",
        "canonical_scenarios": ["smoke-lab", "test-map", "full-validation"],
        "default_capabilities": DEFAULT_CAPABILITIES,
    },
    "sca": {
        "adapter": smart_combat_alarms,
        "enabled_builtin_mods": ["base"],
        "semantic_namespace": "smart_combat_alarms",
        "canonical_scenarios": ["no-breach-on-single-destruction", "breach-confirmed", "dangerous-attack", "gui-state-export"],
        "default_capabilities": DEFAULT_CAPABILITIES,
    },
    "btd": {
        "adapter": biter_turret_defense,
        "enabled_builtin_mods": ["base"],
        "semantic_namespace": "biter_turret_defense",
        "canonical_scenarios": ["baseline-survival", "unlock-path", "forced-defeat", "late-wave-check"],
        "default_capabilities": DEFAULT_CAPABILITIES,
    },
}

MOD_NAME_TO_KEY = {
    "advanced-biter-tactics": "abt",
    "biter-aware-bot-pathing": "babp",
    "smart-combat-alarms": "sca",
    "biter-turret-defense": "btd",
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
    capabilities: list[str],
    capability_options: dict[str, Any],
    setup_options: dict[str, Any],
    action_plan: list[dict[str, Any]],
    assertion_options: dict[str, Any],
    waits: list[dict[str, Any]],
    event_filters: dict[str, Any],
    frame_filters: dict[str, Any],
) -> None:
    payload = {
        "mod_name": mod_name,
        "scenario_name": scenario_name,
        "max_ticks": max_ticks,
        "sample_interval": sample_interval,
        "capabilities": capabilities,
        "capability_options": capability_options,
        "capture_options": {
            "radius": capture_radius,
        },
        "setup_options": setup_options,
        "action_plan": action_plan,
        "assertion_options": assertion_options,
        "waits": waits,
        "event_filters": event_filters,
        "frame_filters": frame_filters,
    }
    lines = [
        "return {",
        f"  mod_name = {_to_lua(payload['mod_name'])},",
        f"  scenario_name = {_to_lua(payload['scenario_name'])},",
        f"  max_ticks = {payload['max_ticks']},",
        f"  sample_interval = {payload['sample_interval']},",
        f"  capabilities = {_to_lua(payload['capabilities'])},",
        f"  capability_options = {_to_lua(payload['capability_options'])},",
        f"  setup_options = {_to_lua(payload['setup_options'])},",
        f"  action_plan = {_to_lua(payload['action_plan'])},",
        f"  assertion_options = {_to_lua(payload['assertion_options'])},",
        f"  waits = {_to_lua(payload['waits'])},",
        f"  event_filters = {_to_lua(payload['event_filters'])},",
        f"  frame_filters = {_to_lua(payload['frame_filters'])},",
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


def _run_factorio(factorio_exe: Path, args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run([str(factorio_exe), *args], check=False, cwd=cwd, text=True, capture_output=True)
    return completed


def _parse_json_option(raw_value: str) -> dict[str, Any]:
    payload = json.loads(raw_value)
    if not isinstance(payload, dict):
        raise ValueError("JSON option payloads must decode to objects")
    return payload


def _parse_json_list_option(raw_value: str) -> list[Any]:
    payload = json.loads(raw_value)
    if not isinstance(payload, list):
        raise ValueError("JSON list payloads must decode to arrays")
    return payload


def _load_plan_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Plan payloads must decode to objects")
    return payload


def _safe_slug(text: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in text).strip("-") or "scenario"


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _copy_factorio_log(runtime_root: Path, output_root: Path) -> tuple[str | None, str | None]:
    source = runtime_root / "factorio-current.log"
    if not source.exists():
        return None, None
    target = output_root / "factorio-current.log"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return str(source), str(target)


def _load_json_for_failure(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _load_jsonl_for_failure(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_failure_artifacts(
    *,
    output_root: Path,
    runtime_root: Path,
    raw_script_output_root: Path,
    mod_name: str,
    scenario_name: str,
    phase: str,
    exit_code: int | None,
    error_message: str,
    setup_options: dict[str, Any],
    action_plan: list[dict[str, Any]],
    assertion_options: dict[str, Any],
    capabilities: list[str],
    capability_options: dict[str, Any],
) -> None:
    artifacts = ensure_protocol_dirs(output_root)
    factorio_log_path, factorio_log_copied_to = _copy_factorio_log(runtime_root, output_root)
    existing_events = _load_jsonl_for_failure(artifacts.events)
    existing_assertions = _load_json_for_failure(artifacts.assertions, [])
    frame_count = len(list_frames(artifacts.frames))

    run_manifest = {
        "mod_name": mod_name,
        "scenario_name": scenario_name,
        "start_tick": None,
        "end_tick": None,
        "status": "failed",
        "phase": phase,
        "workspace_root": str(runtime_root),
        "raw_script_output_root": str(raw_script_output_root),
        "failure_artifact_present": True,
    }
    failure = {
        "phase": phase,
        "exit_code": exit_code,
        "error_message": error_message,
        "factorio_log_path": factorio_log_path,
        "factorio_log_copied_to": factorio_log_copied_to,
        "mod_name": mod_name,
        "scenario_name": scenario_name,
    }
    summary = {
        "status": "failed",
        "mod_name": mod_name,
        "scenario_name": scenario_name,
        "phase": phase,
        "event_count": len(existing_events),
        "frame_count": frame_count,
        "assertion_counts": {"passed": 0, "failed": len(existing_assertions), "total": len(existing_assertions)},
        "failure_reasons": [phase, error_message],
        "next_focus_hints": [phase],
    }
    metrics = {
        "mod_name": mod_name,
        "scenario_name": scenario_name,
        "phase": phase,
        "tick_span": 0,
        "frame_count": frame_count,
        "event_count": len(existing_events),
        "assertion_counts": {"passed": 0, "failed": len(existing_assertions), "total": len(existing_assertions)},
    }

    write_json(artifacts.run_manifest, run_manifest)
    write_json(artifacts.failure, failure)
    write_json(artifacts.summary, summary)
    write_json(artifacts.metrics, metrics)
    write_json(artifacts.assertions, existing_assertions)
    write_jsonl(artifacts.events, existing_events)
    write_json(
        artifacts.scenario,
        {
            "name": scenario_name,
            "description": "Runner failure package.",
            "default_capabilities": capabilities,
            "default_capability_options": capability_options,
            "setup": setup_options,
            "action_plan": {"steps": action_plan},
            "assertions": assertion_options,
        },
    )
    write_json(artifacts.action_plan, {"steps": action_plan})


def _copy_partial_harness_artifacts(raw_script_output_root: Path, output_root: Path) -> None:
    harness_root = raw_script_output_root / "agent-bridge"
    if not harness_root.exists():
        return
    artifacts = ensure_protocol_dirs(output_root)
    for source_name, target in (
        ("events.jsonl", artifacts.events),
        ("assertions.json", artifacts.assertions),
        ("run-manifest.json", artifacts.run_manifest),
        ("summary.json", artifacts.summary),
        ("metrics.json", artifacts.metrics),
        ("scenario.json", artifacts.scenario),
        ("action-plan.json", artifacts.action_plan),
    ):
        source = harness_root / source_name
        if source.exists():
            if source.suffix == ".jsonl":
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    frames_root = harness_root / "frames"
    if frames_root.exists():
        for frame_path in list_frames(frames_root):
            (artifacts.frames / frame_path.name).write_text(frame_path.read_text(encoding="utf-8"), encoding="utf-8")


def _finalize_success_manifest(output_root: Path, runtime_root: Path, raw_script_output_root: Path) -> None:
    manifest_path = output_root / "run-manifest.json"
    summary_path = output_root / "summary.json"
    metrics_path = output_root / "metrics.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["phase"] = "complete"
    manifest["workspace_root"] = str(runtime_root)
    manifest["raw_script_output_root"] = str(raw_script_output_root)
    manifest["failure_artifact_present"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    for path in (summary_path, metrics_path):
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["phase"] = "complete"
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_mod_scenario(
    *,
    mod_key: str,
    factorio_exe: Path,
    target_mod_root: Path,
    scenario_name: str,
    max_ticks: int,
    sample_interval: int,
    capture_radius: int,
    capabilities: list[str],
    capability_options: dict[str, Any],
    setup_options: dict[str, Any],
    action_plan: list[dict[str, Any]],
    assertion_options: dict[str, Any],
    waits: list[dict[str, Any]],
    event_filters: dict[str, Any],
    frame_filters: dict[str, Any],
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

    run_id = _run_id()
    scenario_slug = _safe_slug(scenario_name)
    runtime_root = WORKSPACE_ROOT / "workspaces" / f"{run_id}-{mod_key}-{scenario_slug}"
    output_root = RUNS_ROOT / f"{run_id}-{scenario_slug}"
    mods_root = runtime_root / "mods"
    config_root = runtime_root / "config"
    saves_root = runtime_root / "saves"
    raw_script_output_root = runtime_root / "script-output"
    config_path = config_root / "config.ini"
    save_path = saves_root / "agent-bridge.zip"

    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    ensure_protocol_dirs(output_root)

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
        capabilities=capabilities,
        capability_options=capability_options,
        setup_options=setup_options,
        action_plan=action_plan,
        assertion_options=assertion_options,
        waits=waits,
        event_filters=event_filters,
        frame_filters=frame_filters,
    )
    _write_mod_list(
        mods_root / "mod-list.json",
        target_mod_name,
        harness_mod_name,
        enabled_builtin_mods=mod_entry["enabled_builtin_mods"],
    )

    create_result = _run_factorio(
        factorio_exe,
        _build_create_args(config_path, mods_root, save_path),
        cwd=REPO_ROOT,
    )
    if create_result.returncode != 0 or not save_path.exists():
        _copy_partial_harness_artifacts(raw_script_output_root, output_root)
        _write_failure_artifacts(
            output_root=output_root,
            runtime_root=runtime_root,
            raw_script_output_root=raw_script_output_root,
            mod_name=target_mod_name,
            scenario_name=scenario_name,
            phase="create",
            exit_code=create_result.returncode,
            error_message=(create_result.stdout or "") + (create_result.stderr or ""),
            setup_options=setup_options,
            action_plan=action_plan,
            assertion_options=assertion_options,
            capabilities=capabilities,
            capability_options=capability_options,
        )
        return output_root

    benchmark_result = _run_factorio(
        factorio_exe,
        _build_benchmark_args(config_path, mods_root, save_path, max_ticks),
        cwd=REPO_ROOT,
    )
    if benchmark_result.returncode != 0:
        _copy_partial_harness_artifacts(raw_script_output_root, output_root)
        _write_failure_artifacts(
            output_root=output_root,
            runtime_root=runtime_root,
            raw_script_output_root=raw_script_output_root,
            mod_name=target_mod_name,
            scenario_name=scenario_name,
            phase="benchmark",
            exit_code=benchmark_result.returncode,
            error_message=(benchmark_result.stdout or "") + (benchmark_result.stderr or ""),
            setup_options=setup_options,
            action_plan=action_plan,
            assertion_options=assertion_options,
            capabilities=capabilities,
            capability_options=capability_options,
        )
        return output_root

    harness_root = raw_script_output_root / "agent-bridge"
    raw_manifest = harness_root / "run-manifest.json"
    raw_assertions = harness_root / "assertions.json"
    if not raw_manifest.exists():
        _copy_partial_harness_artifacts(raw_script_output_root, output_root)
        _write_failure_artifacts(
            output_root=output_root,
            runtime_root=runtime_root,
            raw_script_output_root=raw_script_output_root,
            mod_name=target_mod_name,
            scenario_name=scenario_name,
            phase="load",
            exit_code=benchmark_result.returncode,
            error_message="Harness output missing run-manifest.json",
            setup_options=setup_options,
            action_plan=action_plan,
            assertion_options=assertion_options,
            capabilities=capabilities,
            capability_options=capability_options,
        )
        return output_root
    if not raw_assertions.exists():
        _copy_partial_harness_artifacts(raw_script_output_root, output_root)
        _write_failure_artifacts(
            output_root=output_root,
            runtime_root=runtime_root,
            raw_script_output_root=raw_script_output_root,
            mod_name=target_mod_name,
            scenario_name=scenario_name,
            phase="assertions",
            exit_code=benchmark_result.returncode,
            error_message="Harness output missing assertions.json",
            setup_options=setup_options,
            action_plan=action_plan,
            assertion_options=assertion_options,
            capabilities=capabilities,
            capability_options=capability_options,
        )
        return output_root

    try:
        adapter.normalize_run(raw_script_output_root, output_root)
        _finalize_success_manifest(output_root, runtime_root, raw_script_output_root)
        return output_root
    except Exception as exc:
        _copy_partial_harness_artifacts(raw_script_output_root, output_root)
        _write_failure_artifacts(
            output_root=output_root,
            runtime_root=runtime_root,
            raw_script_output_root=raw_script_output_root,
            mod_name=target_mod_name,
            scenario_name=scenario_name,
            phase="normalize",
            exit_code=None,
            error_message=str(exc),
            setup_options=setup_options,
            action_plan=action_plan,
            assertion_options=assertion_options,
            capabilities=capabilities,
            capability_options=capability_options,
        )
        return output_root


def describe_mod(*, mod_key: str, target_mod_root: Path | None = None) -> dict[str, Any]:
    if mod_key not in MOD_REGISTRY:
        raise KeyError(f"Unknown mod key: {mod_key}")

    registry_entry = MOD_REGISTRY[mod_key]
    target_mod_name = None
    if target_mod_root is not None and (target_mod_root / "info.json").exists():
        target_mod_name = _read_info_json(target_mod_root)["name"]

    description = build_bridge_description(
        mod_key=mod_key,
        registry_entry=registry_entry,
        target_mod_name=target_mod_name,
    )
    description["runner_commands"] = ["run", "run-plan", "describe", "diff", "run-abt"]
    description["config_schema"] = {
        "fields": RUN_CONFIG_FIELDS,
        "capability_names": sorted(CAPABILITY_REGISTRY.keys()),
        "action_names": sorted(ACTION_REGISTRY.keys()),
    }
    return description


def _diff_runs(left: Path, right: Path) -> dict[str, Any]:
    manifest = load_optional_json(left / "run-manifest.json") or load_optional_json(right / "run-manifest.json") or {}
    mod_key = MOD_NAME_TO_KEY.get(manifest.get("mod_name"))
    if mod_key:
        adapter = MOD_REGISTRY[mod_key]["adapter"]
        return adapter.diff_runs(left, right)
    return standard_diff_runs(left, right)


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
    run_parser.add_argument("--capabilities-json", default=json.dumps(DEFAULT_CAPABILITIES))
    run_parser.add_argument("--capability-options-json", default="{}")
    run_parser.add_argument("--setup-options-json", default="{}")
    run_parser.add_argument("--action-plan-json", default="[]")
    run_parser.add_argument("--assertion-options-json", default="{}")
    run_parser.add_argument("--waits-json", default="[]")
    run_parser.add_argument("--event-filters-json", default="{}")
    run_parser.add_argument("--frame-filters-json", default="{}")

    run_plan_parser = subparsers.add_parser("run-plan", help="Run a capability/action-plan-driven bridge scenario")
    run_plan_parser.add_argument("--mod", required=True, choices=sorted(MOD_REGISTRY.keys()))
    run_plan_parser.add_argument("--factorio-exe", required=True, type=Path)
    run_plan_parser.add_argument("--target-mod-root", required=True, type=Path)
    run_plan_parser.add_argument("--plan-json", required=True, type=Path)

    describe_parser = subparsers.add_parser("describe", help="Describe the V2 bridge capabilities for a mod key")
    describe_parser.add_argument("--mod", required=True, choices=sorted(MOD_REGISTRY.keys()))
    describe_parser.add_argument("--target-mod-root", type=Path)

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
            capabilities=_parse_json_list_option(args.capabilities_json),
            capability_options=_parse_json_option(args.capability_options_json),
            setup_options=_parse_json_option(args.setup_options_json),
            action_plan=_parse_json_list_option(args.action_plan_json),
            assertion_options=_parse_json_option(args.assertion_options_json),
            waits=_parse_json_list_option(args.waits_json),
            event_filters=_parse_json_option(args.event_filters_json),
            frame_filters=_parse_json_option(args.frame_filters_json),
        )
        print(output_root)
        return 0

    if args.command == "run-plan":
        plan = _load_plan_file(args.plan_json)
        scenario_name = plan.get("scenario_name") or plan.get("scenario")
        if not scenario_name:
            raise ValueError("Plan files must include 'scenario_name' or 'scenario'")
        output_root = run_mod_scenario(
            mod_key=args.mod,
            factorio_exe=args.factorio_exe,
            target_mod_root=args.target_mod_root,
            scenario_name=scenario_name,
            max_ticks=int(plan.get("max_ticks", 720)),
            sample_interval=int(plan.get("sample_interval", 30)),
            capture_radius=int(plan.get("capture_radius", 48)),
            capabilities=list(plan.get("capabilities", MOD_REGISTRY[args.mod].get("default_capabilities", DEFAULT_CAPABILITIES))),
            capability_options=dict(plan.get("capability_options", {})),
            setup_options=dict(plan.get("setup_options", {})),
            action_plan=list(plan.get("action_plan", [])),
            assertion_options=dict(plan.get("assertion_options", {})),
            waits=list(plan.get("waits", [])),
            event_filters=dict(plan.get("event_filters", {})),
            frame_filters=dict(plan.get("frame_filters", {})),
        )
        print(output_root)
        return 0

    if args.command == "describe":
        print(json.dumps(describe_mod(mod_key=args.mod, target_mod_root=args.target_mod_root), indent=2))
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
            capabilities=MOD_REGISTRY["abt"].get("default_capabilities", DEFAULT_CAPABILITIES),
            capability_options={},
            setup_options={},
            action_plan=[],
            assertion_options={},
            waits=[],
            event_filters={},
            frame_filters={},
        )
        print(output_root)
        return 0

    if args.command == "diff":
        print(json.dumps(_diff_runs(args.left, args.right), indent=2))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
