from factorio_agent_bridge.assertions import evaluate_sequence_assertion, invariant_assertion, outcome_assertion


def test_sequence_assertion_passes_for_subsequence() -> None:
    result = evaluate_sequence_assertion(
        "expected-event-sequence",
        ["group_registered", "contact_found", "flank_waypoint_set", "attack_selected"],
        ["group_registered", "flank_waypoint_set", "attack_selected"],
    )
    assert result["passed"] is True
    assert result["evidence"]["missing"] == []


def test_sequence_assertion_reports_missing_steps() -> None:
    result = evaluate_sequence_assertion(
        "expected-event-sequence",
        ["group_registered", "contact_found"],
        ["group_registered", "attack_selected"],
    )
    assert result["passed"] is False
    assert result["evidence"]["missing"] == ["attack_selected"]


def test_invariant_and_outcome_shapes() -> None:
    invariant = invariant_assertion("arena-created", True, actual=True)
    outcome = outcome_assertion("support-mode", False, expected="cone-siege", actual="none")
    assert invariant["type"] == "invariant"
    assert outcome["type"] == "outcome"
