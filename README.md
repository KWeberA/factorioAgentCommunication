# Factorio Agent Bridge

Capability-based local test platform for Factorio mod iteration with AI agents.

This repository provides:

- A shared run artifact protocol and frame envelope
- A local Windows runner for isolated Factorio validation runs
- A thin harness mod with a V2 compatibility layer for existing `agent_bridge` mods
- Generic capability capture for world, entities, players, forces, combat, logistics, power, fluids, circuit, trains, GUI, rendering, events, and map state
- A generic action-plan engine for deterministic test steps and waits
- Adapters for `advanced-biter-tactics`, `biterAwareBotPathing`, `smartCombatAlarms`, and `biterTurretDefense`
- Fixture-based tests for protocol parsing, assertion evaluation, run diffing, and runner config generation

## Current Status

- The bridge runner is registry-driven and supports `abt`, `babp`, `sca`, and `btd`.
- The V2 harness is capability-based and supports:
  - generic snapshot envelopes with `observations` and `semantic_extensions`
  - action-plan driven scenario steps
  - event logging and wait conditions
  - compatibility fallback from legacy `capture_frame()` to V2 snapshots
- Existing target mods still expose `remote.call("agent_bridge", ...)` with:
  - `list_scenarios()`
  - `setup_scenario(name, options)`
  - `capture_frame(options)`
  - `evaluate_assertions(name, options)`
  - `reset_scenario()`
- The V2 runner now also supports:
  - `describe --mod <key>`
  - `run-plan --mod <key> --plan-json <file>`
  - `run --mod <key> --capabilities-json ... --action-plan-json ...`

## Agent Summary

This bridge is meant to let an agent evaluate Factorio mod changes from machine-readable run artifacts instead of manual screen-watching.

For an agent, the bridge now provides four main things:

- Isolated deterministic runs:
  - every run gets a fresh workspace under `.agent-bridge/workspaces/<run-id>-<mod>-<scenario>/`
  - the normalized result is written to `runs/<timestamp>-<scenario>/`
  - `scenario_name` is carried through manifests, events, frames, assertions, and summaries
- Capability-based observation:
  - agents can request only the data they need instead of dumping everything
  - generic snapshot data is written under `observations.<capability>`
  - mod-specific meaning is written under `semantic_extensions.<mod>`
- Action-driven test control:
  - runs can include deterministic `action_plan` steps like `emit_frame`, `advance_ticks`, `wait_until`, `spawn_entity`, `destroy_entity`, `set_tiles`, `teleport_player`, `insert_items`, `set_research`, and `set_force_state`
- Structured evaluation and failure handling:
  - assertions, metrics, summaries, diffs, and early-failure packages are always normalized into stable JSON artifacts

### Capability Catalog

The generic V2 capability layer currently supports:

- `world`: active surface, known surfaces, daytime, freeze state, pollution sample
- `entities`: filtered entities with type, force, position, health, energy, status, progress, inventories
- `players`: player position, opened entity, selected entity, vehicle, cursor stack, controller type
- `forces`: research state, evolution factor, kill statistics, current research
- `combat`: hostile counts, nearby combat entities, recent damage and destroy counters
- `logistics`: ghosts, robots, roboports
- `power`: electric entities and aggregate energy sample
- `fluids`: fluid-capable entities and sampled fluidbox contents
- `circuit`: circuit-capable entities and sampled network ids
- `trains`: train state, station, schedule size, front position
- `gui`: semantic GUI tree snapshots for players
- `rendering`: rendering ids, types, targets, time-to-live
- `events`: recent harness event stream
- `map`: sampled tiles, resources, cliffs

### What Agents Should Read

The primary artifacts for agent iteration are:

- `run-manifest.json`: run identity, phase, workspace roots, scenario, status
- `events.jsonl`: normalized full event stream with `source`, `event_index`, and `source_event_index`
- `frames/frame-<tick>.json`: capability snapshots plus mod semantic extensions
- `assertions.json`: pass/fail checks with evidence and related ticks/groups
- `summary.json`: compact verdict and next focus hints
- `metrics.json`: counts and semantic aggregates
- `failure.json`: present on early failure phases like `create`, `load`, `benchmark`, `assertions`, or `normalize`

### ABT-Specific Semantic Support

`advanced-biter-tactics` now exposes more than legacy event sequences.

For ABT runs, the bridge promotes group safety data into generic V2 `observations.combat.groups[]`, including:

- `state_since_tick`
- `state_duration_ticks`
- `last_meaningful_progress_tick`
- `in_turret_coverage`
- `covering_turret_count`
- `coverage_sources`
- `in_flame_hazard`
- `hazard_score`
- `entry_progress`
- `breach_pressure_active`

ABT also keeps its richer mod-specific meaning under `semantic_extensions.advanced_biter_tactics`, including group diagnostics such as:

- `progress_stalled`
- `unsafe_before_breach`
- `inside_cone_violation`
- `interior_target_before_entry`

### Failure And Diff Behavior

Agents should not treat a missing run artifact as “no result”.

If Factorio fails early, the runner still writes a normalized failure package with:

- `run-manifest.json`
- `summary.json`
- `metrics.json`
- `failure.json`
- copied `factorio-current.log`
- valid fallback `assertions.json`
- valid fallback `events.jsonl`
- `scenario.json`
- `action-plan.json`

Diffs are machine-first JSON and include:

- `assertion_diff`
- `event_diff`
- `frame_diff`
- `failure_diff`
- `semantic_diff`

For ABT, `semantic_diff.abt` also reports coverage, stall, support-mode, breach-pressure, and entry-ordering changes.

### Recommended Agent Loop

The intended loop for agents is:

1. Choose one deterministic scenario.
2. Run the bridge with only the needed capabilities.
3. Read `summary.json`, `assertions.json`, and `events.jsonl` first.
4. Open specific frames only when the summary or assertions point to ambiguity.
5. Use `diff` between runs to decide whether behavior improved, regressed, or stayed unclear.
6. Fall back to manual Factorio observation only if the behavior is not yet represented in bridge artifacts.

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

## Describe Command

```powershell
python -m factorio_agent_bridge describe --mod sca
```

This prints the V2 capability catalog, supported actions, canonical scenarios, and runner-level config fields for the selected mod key.

## Action Plan Example

```json
{
  "scenario_name": "breach-confirmed",
  "max_ticks": 720,
  "capabilities": ["world", "entities", "combat", "events", "gui"],
  "action_plan": [
    {"tick": 60, "action": "emit_frame"},
    {
      "tick": 120,
      "action": "wait_until",
      "condition": {
        "kind": "event",
        "event": "breach_confirmed"
      },
      "timeout_ticks": 240
    }
  ],
  "assertion_options": {}
}
```

Run it with:

```powershell
.\tools\run-agent-bridge.ps1 `
  -Mod "sca" `
  -FactorioExe "E:\SteamLibrary\steamapps\common\Factorio\bin\x64\factorio.exe" `
  -TargetModRoot "C:\Users\Alex\repo\smartCombatAlarms" `
  -Scenario "breach-confirmed" `
  -PlanJson "C:\path\to\bridge-plan.json"
```

The preferred iterative loop is:

1. Run one deterministic bridge scenario for the target mod.
2. Inspect `run-manifest.json`, `events.jsonl`, `frames/`, `assertions.json`, `summary.json`, and when present `scenario.json`, `action-plan.json`, and `metrics.json`.
3. Only fall back to manual Factorio observation if the bridge does not yet cover the changed behavior.
