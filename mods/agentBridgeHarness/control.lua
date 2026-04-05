local CONFIG = require("config")

local OUTPUT_ROOT = "agent-bridge"
local FRAMES_ROOT = OUTPUT_ROOT .. "/frames"

local function json_write(path, payload)
  helpers.write_file(path, helpers.table_to_json(payload), false)
end

local function now_factorio_version()
  return script.active_mods and script.active_mods.base or nil
end

local function capture_frame(reason)
  local frame = remote.call("agent_bridge", "capture_frame", {
    reason = reason,
    radius = CONFIG.capture_options.radius
  })
  if frame and frame.tick then
    json_write(string.format("%s/frame-%d.json", FRAMES_ROOT, frame.tick), frame)
  end
end

local function write_run_manifest(status, setup_result)
  local payload = {
    mod_name = CONFIG.mod_name,
    scenario_name = CONFIG.scenario_name,
    factorio_version = now_factorio_version(),
    start_tick = storage.bridge.start_tick,
    end_tick = game.tick,
    status = status,
    sample_interval = CONFIG.sample_interval,
    max_ticks = CONFIG.max_ticks,
    setup = setup_result
  }
  json_write(OUTPUT_ROOT .. "/run-manifest.json", payload)
  return payload
end

local function ensure_state()
  storage.bridge = storage.bridge or {}
  storage.bridge.bootstrap_complete = storage.bridge.bootstrap_complete or false
  storage.bridge.completed = storage.bridge.completed or false
  storage.bridge.start_tick = storage.bridge.start_tick or nil
  storage.bridge.setup_result = storage.bridge.setup_result or nil
  storage.bridge.next_sample_tick = storage.bridge.next_sample_tick or nil
end

local function bootstrap_run(reason)
  ensure_state()

  if storage.bridge.bootstrap_complete then
    return
  end

  remote.call("agent_bridge", "reset_scenario")
  storage.bridge.setup_result = remote.call("agent_bridge", "setup_scenario", CONFIG.scenario_name, CONFIG.setup_options)
  storage.bridge.start_tick = game.tick
  storage.bridge.next_sample_tick = game.tick + CONFIG.sample_interval
  storage.bridge.bootstrap_complete = true
  capture_frame(reason or "start")
end

local function finalize_run(reason)
  if storage.bridge.completed then
    return
  end

  capture_frame(reason or "final")
  local assertions = remote.call("agent_bridge", "evaluate_assertions", CONFIG.scenario_name, CONFIG.assertion_options)
  local failed = 0
  for index = 1, #assertions do
    if not assertions[index].passed then
      failed = failed + 1
    end
  end

  json_write(OUTPUT_ROOT .. "/assertions.json", assertions)
  local summary = {
    status = failed == 0 and "passed" or "failed",
    assertion_counts = {
      passed = #assertions - failed,
      failed = failed,
      total = #assertions
    }
  }
  json_write(OUTPUT_ROOT .. "/summary.json", summary)
  write_run_manifest(summary.status, storage.bridge.setup_result)
  remote.call("agent_bridge", "reset_scenario")
  storage.bridge.completed = true
end

script.on_init(function()
  ensure_state()
  bootstrap_run("runner-init")
end)

script.on_configuration_changed(function()
  ensure_state()
  bootstrap_run("runner-config-changed")
end)

script.on_event(defines.events.on_tick, function(event)
  ensure_state()

  if storage.bridge.completed then
    return
  end

  if not storage.bridge.bootstrap_complete then
    bootstrap_run("runner-tick-bootstrap")
    return
  end

  if event.tick >= storage.bridge.next_sample_tick then
    capture_frame("interval")
    storage.bridge.next_sample_tick = event.tick + CONFIG.sample_interval
  end

  if event.tick - storage.bridge.start_tick >= CONFIG.max_ticks then
    finalize_run("benchmark-complete")
  end
end)
