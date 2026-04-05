from __future__ import annotations

from typing import Any


def invariant_assertion(name: str, passed: bool, *, expected: Any = True, actual: Any = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "type": "invariant",
        "passed": bool(passed),
        "expected": expected,
        "actual": actual,
        "evidence": evidence or {},
    }


def outcome_assertion(name: str, passed: bool, *, expected: Any = None, actual: Any = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "type": "outcome",
        "passed": bool(passed),
        "expected": expected,
        "actual": actual,
        "evidence": evidence or {},
    }


def evaluate_sequence_assertion(name: str, events: list[str], expected_sequence: list[str]) -> dict[str, Any]:
    index = 0
    matched: list[str] = []
    missing: list[str] = []

    for expected in expected_sequence:
        while index < len(events) and events[index] != expected:
            index += 1
        if index >= len(events):
            missing.append(expected)
            continue
        matched.append(events[index])
        index += 1

    return {
        "name": name,
        "type": "sequence",
        "passed": len(missing) == 0,
        "expected": expected_sequence,
        "actual": events,
        "evidence": {
            "matched": matched,
            "missing": missing,
        },
    }


def summarize_assertions(assertions: list[dict[str, Any]]) -> dict[str, int]:
    passed = sum(1 for assertion in assertions if assertion.get("passed"))
    failed = len(assertions) - passed
    return {
        "passed": passed,
        "failed": failed,
        "total": len(assertions),
    }
