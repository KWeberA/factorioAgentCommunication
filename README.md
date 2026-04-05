# Factorio Agent Bridge

Semantics-first local validation tooling for Factorio mod iteration with AI agents.

This repository provides:

- A shared run artifact protocol
- A local Windows runner for isolated Factorio validation runs
- A thin harness mod that drives the target mod through `remote.call("agent_bridge", ...)`
- Adapters for `advanced-biter-tactics`, `biterAwareBotPathing`, `smartCombatAlarms`, and `biterTurretDefense`
- Fixture-based tests for protocol parsing, assertion evaluation, and run diffing

## Current Status

- The bridge runner is registry-driven and supports `abt`, `babp`, `sca`, and `btd`.
- The target mod now exposes `remote.call("agent_bridge", ...)` with:
  - `list_scenarios()`
  - `setup_scenario(name, options)`
  - `capture_frame(options)`
  - `evaluate_assertions(name, options)`
  - `reset_scenario()`
- `advanced-biter-tactics` remains the reference integration with arena-backed scenarios.
- `biterAwareBotPathing` now wraps the existing smoke lab / test map / full validation flow behind the bridge.
- `smartCombatAlarms` now exports semantic alert, GUI, breach, and dangerous-attack state through the bridge.
- `biterTurretDefense` now exports wave, unlock, HUD, and defeat/victory state through the bridge.

## Layout

- `factorio_agent_bridge/`: Python runner, protocol helpers, adapters, and CLI
- `mods/agentBridgeHarness/`: thin Factorio harness mod used during automated runs
- `tools/run-agent-bridge.ps1`: PowerShell wrapper for local Windows runs
- `tests/`: unit tests and fixtures

## Example

```powershell
.\tools\run-agent-bridge.ps1 `
  -Mod "babp" `
  -FactorioExe "E:\SteamLibrary\steamapps\common\Factorio\bin\x64\factorio.exe" `
  -TargetModRoot "C:\Users\Alex\repo\biterAwareBotPathing" `
  -Scenario "full-validation"
```

The runner creates an isolated workspace under `.agent-bridge/`, executes the scenario, collects `script-output`, and writes a normalized run under `runs/<timestamp>-<scenario>/`.

The preferred iterative loop is:

1. Run one deterministic bridge scenario for the target mod.
2. Inspect `run-manifest.json`, `events.jsonl`, `frames/`, `assertions.json`, and `summary.json`.
3. Only fall back to manual Factorio observation if the bridge does not yet cover the changed behavior.
