local bridge_compat = {}

local function get_agent_bridge_interface()
  return remote.interfaces and remote.interfaces["agent_bridge"] or nil
end

function bridge_compat.has_method(name)
  local interface = get_agent_bridge_interface()
  return interface ~= nil and interface[name] ~= nil
end

function bridge_compat.safe_call(name, ...)
  if not bridge_compat.has_method(name) then
    return false, nil
  end

  local ok, result = pcall(remote.call, "agent_bridge", name, ...)
  if not ok then
    return false, result
  end
  return true, result
end

function bridge_compat.list_scenarios()
  local ok, result = bridge_compat.safe_call("list_scenarios")
  if ok and type(result) == "table" then
    return result
  end
  return {}
end

function bridge_compat.setup_scenario(name, options)
  local ok, result = bridge_compat.safe_call("setup_scenario", name, options or {})
  if ok then
    return result
  end
  return {
    error = result,
  }
end

function bridge_compat.evaluate_assertions(name, options)
  local ok, result = bridge_compat.safe_call("evaluate_assertions", name, options or {})
  if ok and type(result) == "table" then
    return result
  end
  return {
    {
      name = "bridge-evaluate-assertions-call",
      type = "invariant",
      passed = false,
      expected = "target agent_bridge.evaluate_assertions",
      actual = result,
      evidence = {
        method = "evaluate_assertions"
      }
    }
  }
end

function bridge_compat.reset_scenario()
  bridge_compat.safe_call("reset_scenario")
end

function bridge_compat.capture_semantic_snapshot(config, options)
  local ok, result

  ok, result = bridge_compat.safe_call("capture_snapshot", options or {})
  if ok and type(result) == "table" then
    return result
  end

  ok, result = bridge_compat.safe_call("capture_frame", options or {})
  if ok and type(result) == "table" then
    local namespace = config.semantic_namespace or string.gsub(config.mod_name or "mod", "[^%w]+", "_")
    return {
      compatibility_mode = "legacy-capture-frame",
      semantic_extensions = {
        [namespace] = {
          legacy_frame = result
        }
      }
    }
  end

  return {
    compatibility_mode = "no-semantic-snapshot",
    semantic_extensions = {
      harness = {
        snapshot_error = result
      }
    }
  }
end

function bridge_compat.describe_target(config)
  local base = {
    target_mod_name = config.mod_name,
    supports_legacy_agent_bridge = true,
    legacy_methods = {
      list_scenarios = bridge_compat.has_method("list_scenarios"),
      setup_scenario = bridge_compat.has_method("setup_scenario"),
      capture_frame = bridge_compat.has_method("capture_frame"),
      evaluate_assertions = bridge_compat.has_method("evaluate_assertions"),
      reset_scenario = bridge_compat.has_method("reset_scenario")
    },
    v2_methods = {
      describe_bridge = bridge_compat.has_method("describe_bridge"),
      list_capabilities = bridge_compat.has_method("list_capabilities"),
      list_actions = bridge_compat.has_method("list_actions"),
      capture_snapshot = bridge_compat.has_method("capture_snapshot"),
      run_action_plan = bridge_compat.has_method("run_action_plan")
    },
    scenarios = bridge_compat.list_scenarios()
  }

  local ok, result = bridge_compat.safe_call("describe_bridge")
  if ok and type(result) == "table" then
    base.target_description = result
  end

  return base
end

function bridge_compat.run_target_action_plan(plan, options)
  local ok, result = bridge_compat.safe_call("run_action_plan", plan or {}, options or {})
  if ok then
    return result
  end
  return nil
end

return bridge_compat
