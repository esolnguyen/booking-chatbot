"""Run golden-set scenarios through the real pipeline (offline or live)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import yaml

from app.models.request import BookingRequest, TravelerProfile
from app.models.response import RecommendationResult
from app.orchestrator import pipeline
from evals.fakes import (
    make_fake_recommendation_agent,
    make_fake_verification_agent,
    offline_retrieve_context,
)

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.yaml"


@dataclass
class ScenarioOutcome:
    """The result of running one golden scenario."""

    id: str
    title: str
    expected: dict
    result: RecommendationResult | None = None
    error: str | None = None
    # Parsed evidence accounting (populated for both modes where available).
    grounded_refs: list[str] = field(default_factory=list)
    hallucinated_refs: list[str] = field(default_factory=list)

    @property
    def actual_route(self) -> str:
        return self.result.route if self.result else "error"

    @property
    def actual_confidence(self) -> float:
        return self.result.confidence if self.result else float("nan")


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[dict]:
    """Load and lightly validate the golden scenarios."""
    data = yaml.safe_load(path.read_text())
    scenarios = data.get("scenarios", [])
    for s in scenarios:
        if "id" not in s or "expected" not in s or "request" not in s:
            raise ValueError(f"Malformed scenario (need id/request/expected): {s!r}")
    return scenarios


def _build_request(req: dict) -> BookingRequest:
    return BookingRequest(
        traveler=TravelerProfile(
            employee_id=req.get("employee_id", "E-EVAL"),
            name=req.get("name", "Eval Traveler"),
            department=req.get("department", "QA"),
            org_policy_tier=req.get("tier", "standard"),
        ),
        origin=req["origin"],
        destination=req["destination"],
        departure_date=req["departure_date"],
        return_date=req["return_date"],
        trip_purpose=req.get("trip_purpose", "business"),
        preferences=req.get("preferences", []),
        max_budget=req.get("max_budget"),
    )


_HALLUCINATED_FLAG_PREFIX = "hallucinated_evidence_refs:"


def _split_evidence(result: RecommendationResult) -> tuple[list[str], list[str]]:
    """Recover grounded vs. hallucinated refs from a pipeline result.

    The pipeline keeps only grounded refs in ``evidence_refs`` and records any
    hallucinated ones inside a risk-flag string; we reconstruct both here so the
    grounding metric works identically in offline and live mode.
    """
    grounded = list(result.evidence_refs)
    hallucinated: list[str] = []
    for flag in result.risk_flags:
        if flag.startswith(_HALLUCINATED_FLAG_PREFIX):
            refs = flag[len(_HALLUCINATED_FLAG_PREFIX):].strip()
            hallucinated.extend(r.strip() for r in refs.split(",") if r.strip())
    return grounded, hallucinated


async def _run_one_offline(scenario: dict) -> RecommendationResult:
    request = _build_request(scenario["request"])
    fake_rec = make_fake_recommendation_agent(scenario.get("agent_pick", {}))
    fake_ver = make_fake_verification_agent(scenario.get("verifier"))
    with patch.object(pipeline, "retrieve_context", offline_retrieve_context), \
         patch.object(pipeline, "run_recommendation_agent", fake_rec), \
         patch.object(pipeline, "run_verification_agent", fake_ver):
        return await pipeline.run_pipeline(request)


async def _run_one_live(scenario: dict) -> RecommendationResult:
    request = _build_request(scenario["request"])
    return await pipeline.run_pipeline(request)


def run_scenario(scenario: dict, *, live: bool = False) -> ScenarioOutcome:
    """Execute a single scenario and capture its outcome."""
    outcome = ScenarioOutcome(
        id=scenario["id"],
        title=scenario.get("title", scenario["id"]),
        expected=scenario["expected"],
    )
    try:
        runner = _run_one_live if live else _run_one_offline
        result = asyncio.run(runner(scenario))
        outcome.result = result
        outcome.grounded_refs, outcome.hallucinated_refs = _split_evidence(result)
    except Exception as exc:  # noqa: BLE001 — surface any failure as a scenario error
        outcome.error = f"{type(exc).__name__}: {exc}"
    return outcome


def run_all(*, live: bool = False, path: Path = GOLDEN_SET_PATH) -> list[ScenarioOutcome]:
    """Run every scenario in the golden set."""
    return [run_scenario(s, live=live) for s in load_golden_set(path)]
