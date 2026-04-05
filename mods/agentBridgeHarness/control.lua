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

script.on_init(function()
  storage.bridge = {
    stage = "setup",
    start_tick = nil,
    setup_result = nil,
    next_sample_tick = nil
  }
end)

script.on_nth_tick(1, function()
  if storage.bridge.stage == "completed" then
    script.on_nth_tick(1, nil)
    return
  end

  if storage.bridge.stage == "setup" then
    remote.call("agent_bridge", "reset_scenario")
    storage.bridge.setup_result = remote.call("agent_bridge", "setup_scenario", CONFIG.scenario_name, CONFIG.setup_options)
    storage.bridge.start_tick = game.tick
    storage.bridge.next_sample_tick = game.tick + CONFIG.sample_interval
    storage.bridge.stage = "running"
    capture_frame("start")
    return
  end

  if storage.bridge.stage ~= "running" then
    return
  end

  if game.tick >= storage.bridge.next_sample_tick then
    capture_frame("interval")
    storage.bridge.next_sample_tick = game.tick + CONFIG.sample_interval
  end

  if game.tick - storage.bridge.start_tick + 1 >= CONFIG.max_ticks then
    capture_frame("final")
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
    storage.bridge.stage = "completed"
    script.on_nth_tick(1, nil)
  end
end)
