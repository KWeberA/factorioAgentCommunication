local bridge_actions = {}

local function copy_position(position)
  if not position then
    return nil
  end
  return {
    x = position.x,
    y = position.y
  }
end

local function append_events(target, additional)
  if type(additional) ~= "table" then
    return
  end
  for index = 1, #additional do
    target[#target + 1] = additional[index]
  end
end

local function select_surface(options)
  if options and options.surface_name and game.surfaces[options.surface_name] then
    return game.surfaces[options.surface_name]
  end
  for _, player in pairs(game.players) do
    if player.valid then
      return player.surface
    end
  end
  return game.surfaces["nauvis"] or game.surfaces[1]
end

local function find_target_entity(surface, action)
  if action.unit_number then
    return surface.find_entity(action.name or action.entity_name, action.position)
  end

  if action.name and action.position then
    return surface.find_entity(action.name, action.position)
  end

  if action.position then
    local entities = surface.find_entities_filtered({
      position = action.position,
      radius = action.radius or 0.25
    })
    return entities[1]
  end

  return nil
end

local function get_player(player_index)
  local player = game.get_player(player_index)
  if player and player.valid then
    return player
  end
  return nil
end

local function evaluate_event_wait(storage_bridge, condition, start_tick)
  local recent = storage_bridge.recent_events or {}
  for index = 1, #recent do
    local event = recent[index]
    if event.tick and event.tick >= start_tick then
      local matches_event = condition.event == nil or event.event == condition.event
      local matches_category = condition.category == nil or event.category == condition.category
      if matches_event and matches_category then
        return true, event
      end
    end
  end
  return false, nil
end

local function read_path(root, path)
  local current = root
  if not current or not path then
    return nil
  end
  for part in string.gmatch(path, "[^%.]+") do
    if type(current) ~= "table" then
      return nil
    end
    current = current[part]
  end
  return current
end

local function compare_value(actual, operator_name, expected)
  if operator_name == "eq" then
    return actual == expected
  elseif operator_name == "neq" then
    return actual ~= expected
  elseif operator_name == "gt" then
    return actual ~= nil and actual > expected
  elseif operator_name == "gte" then
    return actual ~= nil and actual >= expected
  elseif operator_name == "lt" then
    return actual ~= nil and actual < expected
  elseif operator_name == "lte" then
    return actual ~= nil and actual <= expected
  elseif operator_name == "contains" then
    return type(actual) == "string" and string.find(actual, expected, 1, true) ~= nil
  end
  return false
end

local function evaluate_predicate_wait(storage_bridge, condition)
  local snapshot = storage_bridge.latest_snapshot
  if not snapshot then
    return false, nil
  end
  local actual = read_path(snapshot, condition.path)
  local passed = compare_value(actual, condition.operator or "eq", condition.value)
  return passed, actual
end

local function enqueue_action_plan(storage_bridge, plan)
  if type(plan) ~= "table" then
    return
  end
  for index = 1, #plan do
    storage_bridge.action_plan[#storage_bridge.action_plan + 1] = plan[index]
  end
end

function bridge_actions.begin(config, storage_bridge)
  storage_bridge.action_plan = storage_bridge.action_plan or {}
  storage_bridge.action_index = storage_bridge.action_index or 1
  storage_bridge.active_wait = storage_bridge.active_wait or nil
  storage_bridge.advance_until_tick = storage_bridge.advance_until_tick or nil
  append_events(storage_bridge.action_plan, config.action_plan or {})
end

function bridge_actions.execute_step(config, storage_bridge, action, callbacks)
  local emitted = {}
  local action_name = action.action or action.name
  local surface = select_surface(action)
  local target_player = action.player_index and get_player(action.player_index) or nil

  if action_name == "reset_world" then
    callbacks.reset_target()
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "reset_world", nil, nil, "action-plan", {})
  elseif action_name == "load_scenario" then
    local scenario_name = action.scenario_name or action.scenario
    local result = callbacks.setup_target(scenario_name, action.options or {})
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "load_scenario", nil, nil, scenario_name, {
      result = result
    })
  elseif action_name == "spawn_entity" then
    local created = surface.create_entity({
      name = action.entity_name or action.name,
      position = action.position,
      force = action.force,
      amount = action.amount,
      direction = action.direction,
      player = target_player
    })
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "spawn_entity", copy_position(action.position), nil, action.entity_name or action.name, {
      created_name = created and created.name or nil,
      unit_number = created and created.unit_number or nil
    })
  elseif action_name == "destroy_entity" then
    local entity = find_target_entity(surface, action)
    if entity and entity.valid then
      entity.destroy()
      emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "destroy_entity", copy_position(entity.position), nil, action.reason or "action-plan", {
        destroyed_name = entity.name
      })
    end
  elseif action_name == "set_tiles" then
    surface.set_tiles(action.tiles or {}, action.correct_tiles ~= false, false, false, false)
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "set_tiles", nil, nil, "action-plan", {
      tile_count = action.tiles and #action.tiles or 0
    })
  elseif action_name == "teleport_player" then
    if target_player and action.position then
      target_player.teleport(action.position, surface)
      emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "teleport_player", copy_position(action.position), {
        player_index = target_player.index
      }, "action-plan", {})
    end
  elseif action_name == "insert_items" then
    local inserted = 0
    if target_player and action.items then
      inserted = target_player.insert(action.items)
    else
      local entity = find_target_entity(surface, action)
      if entity and entity.valid and action.items then
        inserted = entity.insert(action.items)
      end
    end
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "insert_items", copy_position(action.position), nil, "action-plan", {
      inserted = inserted
    })
  elseif action_name == "set_research" then
    local force = game.forces[action.force_name or "player"]
    if force and action.technology_name and force.technologies[action.technology_name] then
      force.technologies[action.technology_name].researched = action.researched ~= false
      emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "set_research", nil, {
        force_name = force.name
      }, action.technology_name, {
        researched = action.researched ~= false
      })
    end
  elseif action_name == "set_force_state" then
    local force = game.forces[action.force_name or "player"]
    if force then
      if action.evolution_factor ~= nil then
        force.evolution_factor = action.evolution_factor
      end
      if action.cease_fire then
        for other_force_name, relation in pairs(action.cease_fire) do
          force.set_cease_fire(other_force_name, relation)
        end
      end
      if action.friend then
        for other_force_name, relation in pairs(action.friend) do
          force.set_friend(other_force_name, relation)
        end
      end
      emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "set_force_state", nil, {
        force_name = force.name
      }, "action-plan", action)
    end
  elseif action_name == "advance_ticks" then
    storage_bridge.advance_until_tick = game.tick + (action.ticks or 0)
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "advance_ticks", nil, nil, "action-plan", {
      until_tick = storage_bridge.advance_until_tick
    })
  elseif action_name == "emit_frame" then
    callbacks.capture_snapshot("action-plan")
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "emit_frame", nil, nil, "action-plan", {})
  elseif action_name == "wait_until" then
    storage_bridge.active_wait = {
      started_tick = game.tick,
      timeout_tick = game.tick + (action.timeout_ticks or 300),
      condition = action.condition or {},
      reason = action.reason or "action-plan-wait"
    }
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "wait_until_started", nil, nil, storage_bridge.active_wait.reason, {
      timeout_tick = storage_bridge.active_wait.timeout_tick
    })
  elseif action_name == "run_action_plan" then
    if action.plan then
      enqueue_action_plan(storage_bridge, action.plan)
    else
      callbacks.run_target_action_plan(action.target_plan or {}, action.options or {})
    end
    emitted[#emitted + 1] = callbacks.record_runtime_event("command_executed", "run_action_plan", nil, nil, "action-plan", {
      appended_steps = action.plan and #action.plan or 0
    })
  end

  return emitted
end

function bridge_actions.process(config, storage_bridge, callbacks)
  if storage_bridge.advance_until_tick and game.tick < storage_bridge.advance_until_tick then
    return
  end

  if storage_bridge.advance_until_tick and game.tick >= storage_bridge.advance_until_tick then
    storage_bridge.advance_until_tick = nil
  end

  if storage_bridge.active_wait then
    local condition = storage_bridge.active_wait.condition or {}
    local passed, evidence
    if (condition.kind or "event") == "event" then
      passed, evidence = evaluate_event_wait(storage_bridge, condition, storage_bridge.active_wait.started_tick)
    else
      passed, evidence = evaluate_predicate_wait(storage_bridge, condition)
    end

    if passed then
      callbacks.record_runtime_event("command_executed", "wait_until_satisfied", nil, nil, storage_bridge.active_wait.reason, {
        evidence = evidence
      })
      storage_bridge.active_wait = nil
      storage_bridge.action_index = storage_bridge.action_index + 1
      return
    end

    if game.tick >= storage_bridge.active_wait.timeout_tick then
      callbacks.record_runtime_event("command_executed", "wait_until_timed_out", nil, nil, storage_bridge.active_wait.reason, {
        condition = condition
      })
      storage_bridge.active_wait = nil
      storage_bridge.action_index = storage_bridge.action_index + 1
    end
    return
  end

  local action = storage_bridge.action_plan[storage_bridge.action_index]
  if not action then
    return
  end

  local scheduled_tick = storage_bridge.start_tick + (action.tick or 0)
  if game.tick < scheduled_tick then
    return
  end

  bridge_actions.execute_step(config, storage_bridge, action, callbacks)
  if not storage_bridge.active_wait then
    storage_bridge.action_index = storage_bridge.action_index + 1
  end
end

return bridge_actions
