from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


RUN_MANIFEST = "run-manifest.json"
EVENTS = "events.jsonl"
ASSERTIONS = "assertions.json"
SUMMARY = "summary.json"
FRAMES_DIR = "frames"
SCENARIO = "scenario.json"
ACTION_PLAN = "action-plan.json"
METRICS = "metrics.json"
FAILURE = "failure.json"
FACTORIO_LOG = "factorio-current.log"


@dataclass(frozen=True)
class ArtifactPaths:
    root: Path

    @property
    def run_manifest(self) -> Path:
        return self.root / RUN_MANIFEST

    @property
    def events(self) -> Path:
        return self.root / EVENTS

    @property
    def assertions(self) -> Path:
        return self.root / ASSERTIONS

    @property
    def summary(self) -> Path:
        return self.root / SUMMARY

    @property
    def frames(self) -> Path:
        return self.root / FRAMES_DIR

    @property
    def scenario(self) -> Path:
        return self.root / SCENARIO

    @property
    def action_plan(self) -> Path:
        return self.root / ACTION_PLAN

    @property
    def metrics(self) -> Path:
        return self.root / METRICS

    @property
    def failure(self) -> Path:
        return self.root / FAILURE

    @property
    def factorio_log(self) -> Path:
        return self.root / FACTORIO_LOG


def ensure_protocol_dirs(root: Path) -> ArtifactPaths:
    root.mkdir(parents=True, exist_ok=True)
    (root / FRAMES_DIR).mkdir(parents=True, exist_ok=True)
    return ArtifactPaths(root=root)


_NON_FINITE_TOKEN_RE = re.compile(r"(?P<prefix>[:\[,]\s*)(?P<token>-?inf|nan)(?P<suffix>\s*[,}\]])")


def _sanitize_factorio_json(text: str) -> str:
    sanitized = text
    while True:
        updated = _NON_FINITE_TOKEN_RE.sub(r"\g<prefix>null\g<suffix>", sanitized)
        if updated == sanitized:
            return sanitized
        sanitized = updated


def load_json(path: Path) -> Any:
    return json.loads(_sanitize_factorio_json(path.read_text(encoding="utf-8")))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            rows.append(json.loads(_sanitize_factorio_json(stripped)))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(content, encoding="utf-8")


def list_frames(frames_dir: Path) -> list[Path]:
    if not frames_dir.exists():
        return []
    return sorted(
        child for child in frames_dir.iterdir()
        if child.is_file() and child.suffix == ".json"
    )


def build_summary(
    run_manifest: dict[str, Any],
    assertions: list[dict[str, Any]],
    frame_count: int,
    event_count: int,
    failure_reasons: list[str] | None = None,
) -> dict[str, Any]:
    passed = sum(1 for assertion in assertions if assertion.get("passed"))
    failed = sum(1 for assertion in assertions if not assertion.get("passed"))
    status = "passed" if failed == 0 else "failed"
    return {
        "status": status,
        "mod_name": run_manifest.get("mod_name"),
        "scenario_name": run_manifest.get("scenario_name"),
        "start_tick": run_manifest.get("start_tick"),
        "end_tick": run_manifest.get("end_tick"),
        "phase": run_manifest.get("phase"),
        "event_count": event_count,
        "frame_count": frame_count,
        "assertion_counts": {
            "passed": passed,
            "failed": failed,
            "total": len(assertions),
        },
        "failure_reasons": failure_reasons or [],
        "next_focus_hints": [
            assertion["name"]
            for assertion in assertions
            if not assertion.get("passed")
        ],
    }


def build_metrics(
    run_manifest: dict[str, Any],
    assertions: list[dict[str, Any]],
    frame_count: int,
    event_count: int,
) -> dict[str, Any]:
    passed = sum(1 for assertion in assertions if assertion.get("passed"))
    failed = len(assertions) - passed
    return {
        "mod_name": run_manifest.get("mod_name"),
        "scenario_name": run_manifest.get("scenario_name"),
        "phase": run_manifest.get("phase"),
        "tick_span": max((run_manifest.get("end_tick") or 0) - (run_manifest.get("start_tick") or 0), 0),
        "frame_count": frame_count,
        "event_count": event_count,
        "assertion_counts": {
            "passed": passed,
            "failed": failed,
            "total": len(assertions),
        },
    }
