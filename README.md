# Factorio Agent Bridge

Semantics-first local validation tooling for Factorio mod iteration with AI agents.

This repository provides:

- A shared run artifact protocol
- A local Windows runner for isolated Factorio validation runs
- A thin harness mod that drives the target mod through `remote.call("agent_bridge", ...)`
- A reference adapter for `advanced-biter-tactics`
- Fixture-based tests for protocol parsing, assertion evaluation, and run diffing

## Current Status

- `advanced-biter-tactics` is integrated as the first reference mod.
- The target mod now exposes `remote.call("agent_bridge", ...)` with:
  - `list_scenarios()`
  - `setup_scenario(name, options)`
  - `capture_frame(options)`
  - `evaluate_assertions(name, options)`
  - `reset_scenario()`
- Local bridge runs have been validated against:
  - `wall-open` as a passing reference
  - `wall-covered-flank` as a failing reference that demonstrates negative reporting

## Layout

- `factorio_agent_bridge/`: Python runner, protocol helpers, adapters, and CLI
- `mods/agentBridgeHarness/`: thin Factorio harness mod used during automated runs
- `tools/run-agent-bridge.ps1`: PowerShell wrapper for local Windows runs
- `tests/`: unit tests and fixtures

## Example

```powershell
.\tools\run-agent-bridge.ps1 `
  -FactorioExe "E:\SteamLibrary\steamapps\common\Factorio\bin\x64\factorio.exe" `
  -TargetModRoot "C:\Users\Alex\repo\advancedBiterTactics" `
  -Scenario "wall-covered-flank"
```

The runner creates an isolated workspace under `.agent-bridge/`, executes the scenario, collects `script-output`, and writes a normalized run under `runs/<timestamp>-<scenario>/`.
