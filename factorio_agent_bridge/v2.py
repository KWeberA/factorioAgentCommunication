from __future__ import annotations

from typing import Any


CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "world": {"description": "Surface, daytime, pollution, and world-level context."},
    "entities": {"description": "Filtered entities with health, force, and state summaries."},
    "players": {"description": "Player position, controller, selection, cursor, and vehicle state."},
    "forces": {"description": "Technology, recipe, diplomacy, and force-level status."},
    "combat": {"description": "Hostile pressure, combat summaries, and recent combat signals."},
    "logistics": {"description": "Robots, ghosts, roboports, and logistic infrastructure summaries."},
    "power": {"description": "Nearby electric entities and energy-buffer summaries."},
    "fluids": {"description": "Fluidbox and fluid-network-adjacent summaries."},
    "circuit": {"description": "Circuit network and signal summaries near selected entities."},
    "trains": {"description": "Train, station, and schedule state on the active surface."},
    "gui": {"description": "Semantic GUI tree snapshots for selected players."},
    "rendering": {"description": "Rendering object summaries and debug overlay observations."},
    "events": {"description": "Normalized recent runtime event stream."},
    "map": {"description": "Tiles, cliffs, resources, and terrain summaries in scope."},
}


ACTION_REGISTRY: dict[str, dict[str, Any]] = {
    "reset_world": {"description": "Reset scenario state through the compatibility layer."},
    "load_scenario": {"description": "Load or set up a named scenario."},
    "spawn_entity": {"description": "Spawn one or more entities on a surface."},
    "destroy_entity": {"description": "Destroy an entity selected by unit number or position filter."},
    "set_tiles": {"description": "Replace tiles within a selected area."},
    "teleport_player": {"description": "Move a player to a specific position."},
    "insert_items": {"description": "Insert items into a player or entity inventory."},
    "set_research": {"description": "Set research state for a force or technology."},
    "set_force_state": {"description": "Adjust evolution or diplomacy-related force state."},
    "advance_ticks": {"description": "Pause subsequent action execution for a number of ticks."},
    "wait_until": {"description": "Wait on an event or predicate until satisfied or timed out."},
    "emit_frame": {"description": "Capture a snapshot immediately."},
    "run_action_plan": {"description": "Queue a nested action plan for execution."},
}


DEFAULT_CAPABILITIES = [
    "world",
    "entities",
    "players",
    "forces",
    "combat",
    "events",
]


RUN_CONFIG_FIELDS = [
    "mod_name",
    "scenario_name",
    "max_ticks",
    "sample_interval",
    "capabilities",
    "capability_options",
    "setup_options",
    "action_plan",
    "assertion_options",
    "waits",
    "event_filters",
    "frame_filters",
]


def build_bridge_description(*, mod_key: str, registry_entry: dict[str, Any], target_mod_name: str | None = None) -> dict[str, Any]:
    return {
        "version": "2.0",
        "mod_key": mod_key,
        "target_mod_name": target_mod_name,
        "semantic_namespace": registry_entry.get("semantic_namespace"),
        "canonical_scenarios": registry_entry.get("canonical_scenarios", []),
        "default_capabilities": registry_entry.get("default_capabilities", DEFAULT_CAPABILITIES),
        "capabilities": CAPABILITY_REGISTRY,
        "actions": ACTION_REGISTRY,
        "config_fields": RUN_CONFIG_FIELDS,
        "supports_legacy_agent_bridge": True,
        "compatibility_mode": "compatibility-layer",
    }
