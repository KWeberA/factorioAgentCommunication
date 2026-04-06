local CONFIG = require("config")
local bridge_actions = require("bridge_actions")
local bridge_capabilities = require("bridge_capabilities")
local bridge_compat = require("bridge_compat")

local OUTPUT_ROOT = "agent-bridge"
local FRAMES_ROOT = OUTPUT_ROOT .. "/frames"

local function json_write(path, payload)
  helpers.write_file(path, helpers.table_to_json(payload), false)
end

local function jsonl_append(path, payload)
  helpers.write_file(path, helpers.table_to_json(payload) .. "\n", true)
end

local function now_factorio_version()
  return script.active_mods and script.active_mods.base or nil
end

local function semantic_namespace()
  return string.gsub(CONFIG.mod_name or "mod", "[^%w]+", "_")
end

local function has_capability(name)
  local capabilities = CONFIG.capabilities or {}
  for index = 1, #capabilities do
    if capabilities[index] == name then
      return true
    end
  end
  return false
end

local function event_allowed(category, event_name)
  local filters = CONFIG.event_filters or {}
  if filters.categories and #filters.categories > 0 then
    local matched = false
    for index = 1, #filters.categories do
      if filters.categories[index] == category then
        matched = true
        break
      end
    end
    if not matched then
      return false
    end
  end

  if filters.events and #filters.events > 0 then
    local matched = false
    for index = 1, #filters.events do
      if filters.events[index] == event_name then
        matched = true
        break
      end
    end
    if not matched then
      return false
    end
  end

  return true
end

local function now_counts()
  return storage.bridge.frame_count or 0, storage.bridge.event_count or 0
end

local function ensure_state()
  storage.bridge = storage.bridge or {}
  storage.bridge.bootstrap_complete = storage.bridge.bootstrap_complete or false
  storage.bridge.completed = storage.bridge.completed or false
  storage.bridge.start_tick = storage.bridge.start_tick or nil
  storage.bridge.setup_result = storage.bridge.setup_result or nil
  storage.bridge.next_sample_tick = storage.bridge.next_sample_tick or nil
  storage.bridge.frame_count = storage.bridge.frame_count or 0
  storage.bridge.event_count = storage.bridge.event_count or 0
  storage.bridge.recent_events = storage.bridge.recent_events or {}
  storage.bridge.recent_event_counts = storage.bridge.recent_event_counts or {
    damaged = 0,
    destroyed = 0
  }
  storage.bridge.latest_snapshot = storage.bridge.latest_snapshot or nil
  storage.bridge.bridge_description = storage.bridge.bridge_description or nil
  storage.bridge.action_plan = storage.bridge.action_plan or {}
  storage.bridge.action_index = storage.bridge.action_index or 1
  storage.bridge.active_wait = storage.bridge.active_wait or nil
  storage.bridge.advance_until_tick = storage.bridge.advance_until_tick or nil
  storage.bridge.source_event_index = storage.bridge.source_event_index or 0
end

local function record_runtime_event(category, event_name, position, subject_ids, reason, details)
  ensure_state()

  if not event_allowed(category, event_name) then
    return nil
  end

  local payload = {
    tick = game.tick,
    category = category,
    event = event_name,
    mod_name = CONFIG.mod_name,
    scenario_name = CONFIG.scenario_name,
    surface = game.surfaces[1] and game.surfaces[1].name or nil,
    position = position,
    subject_ids = subject_ids or {},
    force = details and details.force_name or nil,
    player_index = details and details.player_index or nil,
    reason = reason,
    details = details or {},
    source = "harness",
    source_event_index = storage.bridge.source_event_index
  }

  storage.bridge.source_event_index = storage.bridge.source_event_index + 1
  storage.bridge.event_count = storage.bridge.event_count + 1
  storage.bridge.recent_events[#storage.bridge.recent_events + 1] = payload
  if #storage.bridge.recent_events > 128 then
    table.remove(storage.bridge.recent_events, 1)
  end
  jsonl_append(OUTPUT_ROOT .. "/events.jsonl", payload)
  return payload
end

local function merge_tables(base, extra)
  if type(extra) ~= "table" then
    return base
  end
  for key, value in pairs(extra) do
    base[key] = value
  end
  return base
end

local function capture_snapshot(reason, extra_options)
  ensure_state()
  local options = {
    reason = reason,
    radius = CONFIG.capture_options.radius
  }
  if type(extra_options) == "table" then
    for key, value in pairs(extra_options) do
      options[key] = value
    end
  end

  local generic = bridge_capabilities.capture(CONFIG, storage.bridge, options)
  local semantic = bridge_compat.capture_semantic_snapshot(CONFIG, options)

  local frame = {
    tick = generic.tick,
    scenario_name = CONFIG.scenario_name,
    mod_name = CONFIG.mod_name,
    surface = generic.surface,
    bounds = generic.bounds,
    capabilities = generic.capabilities,
    meta = {
      reason = reason,
      scenario_name = CONFIG.scenario_name,
      target_mod_name = CONFIG.mod_name,
      semantic_namespace = semantic_namespace(),
      compatibility_mode = semantic.compatibility_mode or "v2"
    },
    observations = generic.observations or {},
    semantic_extensions = {}
  }

  if semantic.observations then
    merge_tables(frame.observations, semantic.observations)
  end
  if semantic.semantic_extensions then
    merge_tables(frame.semantic_extensions, semantic.semantic_extensions)
  end

  storage.bridge.latest_snapshot = frame
  storage.bridge.frame_count = storage.bridge.frame_count + 1
  json_write(string.format("%s/frame-%d.json", FRAMES_ROOT, frame.tick), frame)
  record_runtime_event("command_executed", "frame_captured", nil, {}, reason, {
    frame_tick = frame.tick
  })
  return frame
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
    setup = setup_result,
    capabilities = CONFIG.capabilities,
    semantic_namespace = semantic_namespace()
  }
  json_write(OUTPUT_ROOT .. "/run-manifest.json", payload)
  return payload
end

local function write_scenario_and_plan()
  json_write(OUTPUT_ROOT .. "/scenario.json", {
    name = CONFIG.scenario_name,
    description = "Generated bridge scenario envelope.",
    default_capabilities = CONFIG.capabilities,
    default_capability_options = CONFIG.capability_options,
    setup = CONFIG.setup_options,
    action_plan = {
      steps = CONFIG.action_plan or {}
    },
    assertions = CONFIG.assertion_options
  })
  json_write(OUTPUT_ROOT .. "/action-plan.json", {
    steps = CONFIG.action_plan or {}
  })
end

local function write_metrics(status)
  local frame_count, event_count = now_counts()
  json_write(OUTPUT_ROOT .. "/metrics.json", {
    status = status,
    frame_count = frame_count,
    event_count = event_count,
    capabilities = CONFIG.capabilities,
    start_tick = storage.bridge.start_tick,
    end_tick = game.tick
  })
end

local function finalize_run(reason)
  if storage.bridge.completed then
    return
  end

  capture_snapshot(reason or "final")
  local assertions = bridge_compat.evaluate_assertions(CONFIG.scenario_name, CONFIG.assertion_options)
  local failed = 0
  for index = 1, #assertions do
    if not assertions[index].passed then
      failed = failed + 1
    end
  end

  local summary = {
    status = failed == 0 and "passed" or "failed",
    assertion_counts = {
      passed = #assertions - failed,
      failed = failed,
      total = #assertions
    }
  }

  record_runtime_event("scenario_finished", "scenario_finished", nil, {}, summary.status, {
    assertion_count = #assertions
  })

  json_write(OUTPUT_ROOT .. "/assertions.json", assertions)
  json_write(OUTPUT_ROOT .. "/summary.json", summary)
  write_run_manifest(summary.status, storage.bridge.setup_result)
  write_metrics(summary.status)
  bridge_compat.reset_scenario()
  storage.bridge.completed = true
end

local function bootstrap_run(reason)
  ensure_state()

  if storage.bridge.bootstrap_complete then
    return
  end

  storage.bridge.bridge_description = bridge_compat.describe_target(CONFIG)
  write_scenario_and_plan()
  bridge_compat.reset_scenario()
  storage.bridge.setup_result = bridge_compat.setup_scenario(CONFIG.scenario_name, CONFIG.setup_options)
  storage.bridge.start_tick = game.tick
  storage.bridge.next_sample_tick = game.tick + CONFIG.sample_interval
  storage.bridge.bootstrap_complete = true
  bridge_actions.begin(CONFIG, storage.bridge)
  record_runtime_event("scenario_started", "scenario_started", nil, {}, reason or "runner-init", {
    scenarios = storage.bridge.bridge_description.scenarios,
    target_description = storage.bridge.bridge_description.target_description
  })
  capture_snapshot(reason or "start")
end

local function callbacks()
  return {
    record_runtime_event = record_runtime_event,
    capture_snapshot = function(reason)
      return capture_snapshot(reason or "action-plan")
    end,
    reset_target = function()
      bridge_compat.reset_scenario()
    end,
    setup_target = function(name, options)
      return bridge_compat.setup_scenario(name, options)
    end,
    run_target_action_plan = function(plan, options)
      return bridge_compat.run_target_action_plan(plan, options)
    end
  }
end

local function record_entity_event(category, event_name, entity, reason, extra)
  if not has_capability("events") then
    return
  end
  record_runtime_event(category, event_name, entity and entity.position or nil, {
    unit_number = entity and entity.unit_number or nil,
    entity_name = entity and entity.name or nil
  }, reason, extra or {})
end

script.on_init(function()
  ensure_state()
  bootstrap_run("runner-init")
end)

script.on_configuration_changed(function()
  ensure_state()
  bootstrap_run("runner-config-changed")
end)

script.on_event(defines.events.on_entity_damaged, function(event)
  ensure_state()
  storage.bridge.recent_event_counts.damaged = storage.bridge.recent_event_counts.damaged + 1
  record_entity_event("entity_damaged", "entity_damaged", event.entity, "runtime", {
    damage = event.final_damage_amount,
    force_name = event.force and event.force.name or nil,
    cause_name = event.cause and event.cause.name or nil
  })
end)

script.on_event(defines.events.on_entity_died, function(event)
  ensure_state()
  storage.bridge.recent_event_counts.destroyed = storage.bridge.recent_event_counts.destroyed + 1
  record_entity_event("entity_destroyed", "entity_destroyed", event.entity, "runtime", {
    force_name = event.force and event.force.name or nil,
    cause_name = event.cause and event.cause.name or nil
  })
end)

script.on_event(defines.events.on_built_entity, function(event)
  record_entity_event("entity_spawned", "entity_built", event.created_entity, "runtime", {
    player_index = event.player_index
  })
end)

script.on_event(defines.events.on_robot_built_entity, function(event)
  record_entity_event("entity_spawned", "entity_robot_built", event.created_entity, "runtime", {})
end)

script.on_event(defines.events.on_player_mined_entity, function(event)
  record_entity_event("entity_destroyed", "entity_player_mined", event.entity, "runtime", {
    player_index = event.player_index
  })
end)

script.on_event(defines.events.on_robot_mined_entity, function(event)
  record_entity_event("entity_destroyed", "entity_robot_mined", event.entity, "runtime", {})
end)

script.on_event(defines.events.on_research_finished, function(event)
  if not has_capability("events") then
    return
  end
  record_runtime_event("decision_made", "research_finished", nil, {
    technology = event.research and event.research.name or nil
  }, "runtime", {
    force_name = event.research and event.research.force and event.research.force.name or nil
  })
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

  bridge_actions.process(CONFIG, storage.bridge, callbacks())

  if event.tick >= storage.bridge.next_sample_tick then
    capture_snapshot("interval")
    storage.bridge.next_sample_tick = event.tick + CONFIG.sample_interval
  end

  if storage.bridge.active_wait and storage.bridge.active_wait.condition and storage.bridge.active_wait.condition.kind ~= "event" then
    local check_interval = storage.bridge.active_wait.condition.check_interval or CONFIG.sample_interval
    if event.tick % math.max(check_interval, 1) == 0 then
      capture_snapshot("wait-check")
    end
  end

  if event.tick - storage.bridge.start_tick >= CONFIG.max_ticks then
    finalize_run("benchmark-complete")
  end
end)
