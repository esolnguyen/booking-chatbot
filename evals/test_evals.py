"""CI gate for the routing eval harness (offline, no Azure cost).

These tests assert the DETERMINISTIC trust boundary: every scenario whose route
is forced by a hard cap (inventory / policy / price / claim / no-inventory) must
route exactly as labelled. They run in plain pytest with the LLM agents and the
vector store faked, so they're safe on every push.

Soft calibration scenarios are deliberately NOT hard-asserted here — they are
scored by ``python -m evals.run_evals`` and surfaced as divergences. Pin their
*observed* routes below so an unintended change in the confidence formula still
trips a test, without turning a known calibration gap into a red build.
"""

import pytest

from evals.harness import run_all
from evals.report import build_report


@pytest.fixture(scope="module")
def report():
    return build_report(run_all(live=False), live=False)


def test_harness_runs_every_scenario(report):
    assert report.grades, "no scenarios were graded"
    assert all(g.error is None for g in report.grades), [
        (g.id, g.error) for g in report.grades if g.error
    ]


def test_all_guaranteed_hard_cap_scenarios_pass(report):
    """The deterministic trust boundary must hold — this is the real CI gate."""
    failures = [(g.id, g.reasons) for g in report.guaranteed_failures]
    assert not failures, f"guaranteed scenarios regressed: {failures}"


def test_ci_gate_is_green(report):
    assert report.ci_ok


def test_all_traps_avoided(report):
    """No plausible-but-wrong pick may route to its trap route (auto_suggest)."""
    from evals.report import trap_avoidance

    tr = trap_avoidance(report.outcomes)
    assert tr["traps"] > 0, "expected at least one trap-labelled scenario"
    assert tr["rate"] == 1.0, f"harness fell for traps: {tr['fell_for']}"


# --- Observed (snapshot) routes for soft, calibration-sensitive scenarios. ----
# Update intentionally when the confidence formula / thresholds change.
# NOTE: sydney-hallucinated-evidence-ref used to live here as a "known calibration
# gap" that routed auto_suggest. It is now a DETERMINISTIC hard cap
# (hallucinated_evidence, cap 0.70) and is covered by the guaranteed CI gate above.
_OBSERVED_SOFT_ROUTES = {
    "tokyo-cherry-blossom-caution": "suggest_with_caution",
}


@pytest.mark.parametrize("scenario_id,expected_route", _OBSERVED_SOFT_ROUTES.items())
def test_soft_scenarios_match_observed_behaviour(report, scenario_id, expected_route):
    grade = next((g for g in report.grades if g.id == scenario_id), None)
    assert grade is not None, f"scenario {scenario_id} missing from golden set"
    assert grade.actual_route == expected_route, (
        f"{scenario_id} now routes {grade.actual_route} at "
        f"{grade.actual_confidence:.3f} (was {expected_route}). If this is an "
        "intentional calibration change, update _OBSERVED_SOFT_ROUTES."
    )
