local bridge_capabilities = {}

local MAX_ENTITY_ROWS = 100
local MAX_GUI_CHILDREN = 20
local MAX_GUI_DEPTH = 3
local MAX_RECENT_EVENTS = 64

local function copy_position(position)
  if not position then
    return nil
  end
  return {
    x = position.x,
    y = position.y
  }
end

local function shallow_copy(list)
  local copy = {}
  for index = 1, #list do
    copy[index] = list[index]
  end
  return copy
end

local function safe_call(fn, default)
  local ok, result = pcall(fn)
  if ok then
    return result
  end
  return default
end

local function normalize_bounds(center, radius)
  return {
    left_top = {
      x = center.x - radius,
      y = center.y - radius
    },
    right_bottom = {
      x = center.x + radius,
      y = center.y + radius
    }
  }
end

local function get_surface_by_name(name)
  if name and game.surfaces[name] then
    return game.surfaces[name]
  end
  return nil
end

local function select_surface(options)
  local surface = get_surface_by_name(options.surface_name)
  if surface then
    return surface
  end

  if options.player_index then
    local player = game.get_player(options.player_index)
    if player and player.valid then
      return player.surface
    end
  end

  for _, player in pairs(game.players) do
    if player and player.valid then
      return player.surface
    end
  end

  return game.surfaces["nauvis"] or game.surfaces[1]
end

local function select_center(surface, options)
  if options.position then
    return {
      x = options.position.x or 0,
      y = options.position.y or 0
    }
  end

  if options.center then
    return {
      x = options.center.x or 0,
      y = options.center.y or 0
    }
  end

  if options.player_index then
    local player = game.get_player(options.player_index)
    if player and player.valid then
      return copy_position(player.position)
    end
  end

  return {x = 0, y = 0}
end

local function entity_matches_filters(entity, filters)
  filters = filters or {}
  if filters.names and #filters.names > 0 then
    local matched = false
    for index = 1, #filters.names do
      if entity.name == filters.names[index] then
        matched = true
        break
      end
    end
    if not matched then
      return false
    end
  end

  if filters.types and #filters.types > 0 then
    local matched = false
    for index = 1, #filters.types do
      if entity.type == filters.types[index] then
        matched = true
        break
      end
    end
    if not matched then
      return false
    end
  end

  if filters.forces and #filters.forces > 0 then
    local force_name = entity.force and entity.force.name or nil
    local matched = false
    for index = 1, #filters.forces do
      if force_name == filters.forces[index] then
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

local function summarize_inventory(entity)
  local inventories = {}
  local inventory_names = {
    defines.inventory.chest,
    defines.inventory.furnace_source,
    defines.inventory.furnace_result,
    defines.inventory.assembling_machine_input,
    defines.inventory.assembling_machine_output,
    defines.inventory.lab_input,
    defines.inventory.turret_ammo,
    defines.inventory.cargo_wagon,
    defines.inventory.roboport_robot,
    defines.inventory.roboport_material,
  }

  for index = 1, #inventory_names do
    local inventory_id = inventory_names[index]
    local inventory = safe_call(function()
      return entity.get_inventory(inventory_id)
    end, nil)
    if inventory and inventory.valid then
      inventories[#inventories + 1] = {
        inventory = inventory_id,
        item_count = #inventory.get_contents()
      }
    end
  end

  return inventories
end

local function capture_world(surface, center)
  local surfaces = {}
  for _, candidate in pairs(game.surfaces) do
    surfaces[#surfaces + 1] = {
      index = candidate.index,
      name = candidate.name,
      daytime = candidate.daytime,
      freeze_daytime = candidate.freeze_daytime,
      wind_orientation = candidate.wind_orientation
    }
  end

  return {
    active_surface = {
      index = surface.index,
      name = surface.name,
      daytime = surface.daytime,
      freeze_daytime = surface.freeze_daytime,
      pollution = safe_call(function()
        return surface.get_pollution(center)
      end, 0)
    },
    surfaces = surfaces
  }
end

local function capture_entities(surface, bounds, options)
  local filters = options or {}
  local entities = surface.find_entities_filtered({
    area = bounds
  })
  local rows = {}
  local limit = math.min(filters.limit or MAX_ENTITY_ROWS, MAX_ENTITY_ROWS)

  for _, entity in pairs(entities) do
    if entity.valid and entity_matches_filters(entity, filters) then
      rows[#rows + 1] = {
        unit_number = entity.unit_number,
        name = entity.name,
        type = entity.type,
        force = entity.force and entity.force.name or nil,
        position = copy_position(entity.position),
        health = entity.health,
        energy = entity.energy,
        status = safe_call(function()
          return entity.status
        end, nil),
        crafting_progress = safe_call(function()
          return entity.crafting_progress
        end, nil),
        mining_progress = safe_call(function()
          return entity.mining_progress
        end, nil),
        inventories = summarize_inventory(entity)
      }
      if #rows >= limit then
        break
      end
    end
  end

  return {
    summary = {
      entity_count = #entities,
      captured_count = #rows
    },
    entities = rows
  }
end

local function capture_players(options)
  local rows = {}
  for _, player in pairs(game.players) do
    if player.valid and (not options or not options.player_indexes or #options.player_indexes == 0) then
      rows[#rows + 1] = {
        player_index = player.index,
        name = player.name,
        position = copy_position(player.position),
        surface = player.surface and player.surface.name or nil,
        controller_type = player.controller_type,
        opened = player.opened and player.opened.name or nil,
        selected = player.selected and player.selected.name or nil,
        vehicle = player.vehicle and player.vehicle.name or nil,
        cursor_stack = player.cursor_stack and player.cursor_stack.valid_for_read and player.cursor_stack.name or nil
      }
    elseif player.valid and options.player_indexes and #options.player_indexes > 0 then
      for index = 1, #options.player_indexes do
        if player.index == options.player_indexes[index] then
          rows[#rows + 1] = {
            player_index = player.index,
            name = player.name,
            position = copy_position(player.position),
            surface = player.surface and player.surface.name or nil,
            controller_type = player.controller_type,
            opened = player.opened and player.opened.name or nil,
            selected = player.selected and player.selected.name or nil,
            vehicle = player.vehicle and player.vehicle.name or nil,
            cursor_stack = player.cursor_stack and player.cursor_stack.valid_for_read and player.cursor_stack.name or nil
          }
          break
        end
      end
    end
  end
  return {
    players = rows
  }
end

local function capture_forces()
  local rows = {}
  for _, force in pairs(game.forces) do
    local researched_count = 0
    for _, technology in pairs(force.technologies) do
      if technology.researched then
        researched_count = researched_count + 1
      end
    end
    rows[#rows + 1] = {
      name = force.name,
      evolution_factor = safe_call(function()
        return force.evolution_factor
      end, nil),
      current_research = force.current_research and force.current_research.name or nil,
      researched_technology_count = researched_count,
      kill_count_statistics = safe_call(function()
        return force.kill_count_statistics.input_counts
      end, {})
    }
  end
  return {
    forces = rows
  }
end

local function capture_combat(surface, bounds, recent_events)
  local units = surface.find_entities_filtered({
    area = bounds,
    type = {"unit", "turret", "unit-spawner"}
  })
  local hostile = 0
  for _, entity in pairs(units) do
    if entity.valid and entity.force and entity.force.name == "enemy" then
      hostile = hostile + 1
    end
  end
  return {
    summary = {
      hostile_entity_count = hostile,
      nearby_combat_entities = #units
    },
    recent_damage_events = recent_events.damage or 0,
    recent_destroy_events = recent_events.destroyed or 0
  }
end

local function capture_logistics(surface, bounds)
  local ghosts = surface.count_entities_filtered({
    area = bounds,
    type = "entity-ghost"
  })
  local robots = surface.count_entities_filtered({
    area = bounds,
    type = {"construction-robot", "logistic-robot"}
  })
  local roboports = surface.count_entities_filtered({
    area = bounds,
    type = "roboport"
  })
  return {
    summary = {
      ghost_count = ghosts,
      robot_count = robots,
      roboport_count = roboports
    }
  }
end

local function capture_power(surface, bounds)
  local entities = surface.find_entities_filtered({
    area = bounds,
    type = {
      "electric-pole",
      "generator",
      "solar-panel",
      "accumulator",
      "reactor"
    }
  })
  local total_energy = 0
  for _, entity in pairs(entities) do
    total_energy = total_energy + (entity.energy or 0)
  end
  return {
    summary = {
      electric_entity_count = #entities,
      total_energy = total_energy
    }
  }
end

local function capture_fluids(surface, bounds)
  local entities = surface.find_entities_filtered({
    area = bounds,
    type = {
      "pipe",
      "pipe-to-ground",
      "storage-tank",
      "offshore-pump",
      "pump"
    }
  })
  local samples = {}
  for _, entity in pairs(entities) do
    local fluidbox_length = safe_call(function()
      return #entity.fluidbox
    end, 0)
    if fluidbox_length > 0 then
      local box = entity.fluidbox[1]
      samples[#samples + 1] = {
        name = entity.name,
        position = copy_position(entity.position),
        fluid = box and box.name or nil,
        amount = box and box.amount or 0
      }
    end
    if #samples >= 20 then
      break
    end
  end
  return {
    summary = {
      fluid_entity_count = #entities,
      sampled_count = #samples
    },
    samples = samples
  }
end

local function capture_circuit(surface, bounds)
  local entities = surface.find_entities_filtered({
    area = bounds,
    type = {
      "constant-combinator",
      "arithmetic-combinator",
      "decider-combinator",
      "programmable-speaker",
      "lamp",
      "power-switch",
      "train-stop",
      "roboport"
    }
  })
  local rows = {}
  for _, entity in pairs(entities) do
    local red = safe_call(function()
      local network = entity.get_circuit_network(defines.wire_connector_id.circuit_red, defines.circuit_connector_id.combinator_input)
      return network and network.network_id or nil
    end, nil)
    local green = safe_call(function()
      local network = entity.get_circuit_network(defines.wire_connector_id.circuit_green, defines.circuit_connector_id.combinator_input)
      return network and network.network_id or nil
    end, nil)
    rows[#rows + 1] = {
      name = entity.name,
      type = entity.type,
      position = copy_position(entity.position),
      red_network_id = red,
      green_network_id = green
    }
    if #rows >= 30 then
      break
    end
  end
  return {
    summary = {
      circuit_entity_count = #entities,
      sampled_count = #rows
    },
    entities = rows
  }
end

local function capture_trains(surface)
  local trains = safe_call(function()
    return surface.get_trains()
  end, {})
  local rows = {}
  for _, train in pairs(trains) do
    rows[#rows + 1] = {
      id = train.id,
      state = train.state,
      manual_mode = train.manual_mode,
      schedule_records = train.schedule and #train.schedule.records or 0,
      station = train.station and train.station.backer_name or nil,
      front_position = train.front_stock and copy_position(train.front_stock.position) or nil
    }
    if #rows >= 40 then
      break
    end
  end
  return {
    summary = {
      train_count = #trains,
      sampled_count = #rows
    },
    trains = rows
  }
end

local function serialize_gui_element(element, depth)
  if not element or not element.valid then
    return nil
  end

  local node = {
    name = element.name,
    type = element.type,
    caption = safe_call(function()
      return element.caption
    end, nil),
    visible = element.visible,
    enabled = element.enabled
  }

  if depth >= MAX_GUI_DEPTH then
    return node
  end

  local children = {}
  local limit = math.min(#element.children, MAX_GUI_CHILDREN)
  for index = 1, limit do
    children[#children + 1] = serialize_gui_element(element.children[index], depth + 1)
  end
  node.children = children
  node.selected_index = safe_call(function()
    return element.selected_index
  end, nil)
  node.state = safe_call(function()
    return element.state
  end, nil)
  return node
end

local function capture_gui(options)
  local payload = {}
  for _, player in pairs(game.players) do
    if player.valid then
      payload[#payload + 1] = {
        player_index = player.index,
        screen = serialize_gui_element(player.gui.screen, 0),
        left = serialize_gui_element(player.gui.left, 0),
        top = serialize_gui_element(player.gui.top, 0)
      }
    end
  end
  return {
    players = payload
  }
end

local function capture_rendering()
  local ids = safe_call(function()
    return rendering.get_all_ids()
  end, {})
  local rows = {}
  for index = 1, math.min(#ids, 50) do
    local id = ids[index]
    rows[#rows + 1] = {
      id = id,
      type = safe_call(function()
        return rendering.get_type(id)
      end, nil),
      surface = safe_call(function()
        local surface = rendering.get_surface(id)
        return surface and surface.name or nil
      end, nil),
      target = safe_call(function()
        return rendering.get_target(id)
      end, nil),
      time_to_live = safe_call(function()
        return rendering.get_time_to_live(id)
      end, nil)
    }
  end
  return {
    summary = {
      rendering_count = #ids,
      sampled_count = #rows
    },
    objects = rows
  }
end

local function capture_events(storage_bridge)
  local recent = storage_bridge.recent_events or {}
  local copy = {}
  local first = math.max(#recent - MAX_RECENT_EVENTS + 1, 1)
  for index = first, #recent do
    copy[#copy + 1] = recent[index]
  end
  return {
    recent = copy
  }
end

local function capture_map(surface, bounds)
  local resources = surface.find_entities_filtered({
    area = bounds,
    type = "resource"
  })
  local cliffs = surface.count_entities_filtered({
    area = bounds,
    type = "cliff"
  })
  local sample_tiles = {}
  local step = math.max(((bounds.right_bottom.x - bounds.left_top.x) / 4), 1)
  local y = bounds.left_top.y
  while y <= bounds.right_bottom.y do
    local x = bounds.left_top.x
    while x <= bounds.right_bottom.x do
      local tile = surface.get_tile(x, y)
      sample_tiles[#sample_tiles + 1] = {
        name = tile.name,
        position = {x = x, y = y}
      }
      if #sample_tiles >= 25 then
        break
      end
      x = x + step
    end
    if #sample_tiles >= 25 then
      break
    end
    y = y + step
  end
  return {
    summary = {
      resource_count = #resources,
      cliff_count = cliffs,
      sampled_tile_count = #sample_tiles
    },
    tiles = sample_tiles
  }
end

local CAPTURE_FUNCTIONS = {
  world = function(context, options)
    return capture_world(context.surface, context.center)
  end,
  entities = function(context, options)
    return capture_entities(context.surface, context.bounds, options)
  end,
  players = function(_, options)
    return capture_players(options)
  end,
  forces = function()
    return capture_forces()
  end,
  combat = function(context)
    return capture_combat(context.surface, context.bounds, context.recent_event_counts)
  end,
  logistics = function(context)
    return capture_logistics(context.surface, context.bounds)
  end,
  power = function(context)
    return capture_power(context.surface, context.bounds)
  end,
  fluids = function(context)
    return capture_fluids(context.surface, context.bounds)
  end,
  circuit = function(context)
    return capture_circuit(context.surface, context.bounds)
  end,
  trains = function(context)
    return capture_trains(context.surface)
  end,
  gui = function(_, options)
    return capture_gui(options)
  end,
  rendering = function()
    return capture_rendering()
  end,
  events = function(context)
    return capture_events(context.storage_bridge)
  end,
  map = function(context)
    return capture_map(context.surface, context.bounds)
  end,
}

function bridge_capabilities.capture(config, storage_bridge, options)
  options = options or {}
  local radius = options.radius or (config.capture_options and config.capture_options.radius) or 48
  local surface = select_surface(options)
  local center = select_center(surface, options)
  local bounds = normalize_bounds(center, radius)
  local context = {
    surface = surface,
    center = center,
    bounds = bounds,
    storage_bridge = storage_bridge,
    recent_event_counts = storage_bridge.recent_event_counts or {}
  }

  local observations = {}
  local capabilities = shallow_copy(config.capabilities or {})
  for index = 1, #capabilities do
    local capability = capabilities[index]
    local capture = CAPTURE_FUNCTIONS[capability]
    if capture then
      observations[capability] = capture(context, (config.capability_options and config.capability_options[capability]) or {})
    end
  end

  return {
    tick = game.tick,
    surface = surface and surface.name or nil,
    bounds = bounds,
    capabilities = capabilities,
    observations = observations
  }
end

return bridge_capabilities
