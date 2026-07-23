"""Unit tests for the local telemetry layer (app/telemetry.py).

Pure and offline — no network, no vector store. Exercises span latency capture,
token/cost attribution, run aggregation, and the safe no-op path when disabled.
"""

import time

import pytest

from app import telemetry
from app.config import settings


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Each test starts from a clean, enabled telemetry state."""
    telemetry._current_run.set(None)
    telemetry._current_span.set(None)
    original = settings.telemetry_enabled
    settings.telemetry_enabled = True
    yield
    settings.telemetry_enabled = original
    telemetry._current_run.set(None)
    telemetry._current_span.set(None)


def test_estimate_cost_uses_configured_prices():
    # 1000 in @ 0.00015 + 2000 out @ 0.0006 = 0.00015 + 0.0012
    cost = telemetry.estimate_cost(1000, 2000)
    assert cost == pytest.approx(0.00135)


def test_span_records_latency_and_appends_to_run():
    telemetry.start_run("t")
    with telemetry.span("step-a"):
        time.sleep(0.01)
    run = telemetry.get_current_run()
    assert [s.name for s in run.spans] == ["step-a"]
    assert run.spans[0].duration_ms >= 8  # ~10ms, allow scheduler slack


def test_record_llm_usage_attaches_to_current_span():
    telemetry.start_run("t")
    with telemetry.span("recommendation_agent"):
        cost = telemetry.record_llm_usage(1000, 500)
    run = telemetry.get_current_run()
    span_rec = run.spans[0]
    assert span_rec.prompt_tokens == 1000
    assert span_rec.completion_tokens == 500
    assert span_rec.total_tokens == 1500
    assert span_rec.cost_usd == pytest.approx(cost)
    assert run.total_tokens == 1500
    assert run.cost_usd == pytest.approx(cost)


def test_usage_attributes_to_innermost_span():
    telemetry.start_run("t")
    with telemetry.span("outer"):
        with telemetry.span("inner"):
            telemetry.record_llm_usage(100, 100)
    run = telemetry.get_current_run()
    by_name = {s.name: s for s in run.spans}
    assert by_name["inner"].total_tokens == 200
    assert by_name["outer"].total_tokens == 0  # nothing recorded at the outer level
    assert run.total_tokens == 200  # run aggregates across all spans


def test_finish_run_sets_last_run_and_clears_current():
    telemetry.start_run("t")
    with telemetry.span("x"):
        telemetry.record_llm_usage(10, 10)
    finished = telemetry.finish_run()
    assert telemetry.get_current_run() is None
    assert telemetry.get_last_run() is finished
    assert finished.total_tokens == 20


def test_span_records_error_and_reraises():
    telemetry.start_run("t")
    with pytest.raises(ValueError):
        with telemetry.span("boom"):
            raise ValueError("kaboom")
    run = telemetry.get_current_run()
    assert run.spans[0].error is not None
    assert "kaboom" in run.spans[0].error


def test_disabled_telemetry_is_a_noop():
    settings.telemetry_enabled = False
    telemetry.start_run("t")  # still sets a run, but spans/usage are inert
    with telemetry.span("x"):
        assert telemetry.record_llm_usage(1000, 1000) == 0.0
    run = telemetry.get_current_run()
    assert run.spans == []  # nothing recorded while disabled


def test_run_summary_shape():
    telemetry.start_run("pipeline")
    with telemetry.span("retrieval"):
        pass
    with telemetry.span("recommendation_agent"):
        telemetry.record_llm_usage(200, 100)
    summary = telemetry.get_current_run().summary()
    assert summary["run"] == "pipeline"
    assert summary["spans"] == 2
    assert summary["total_tokens"] == 300
    assert {s["name"] for s in summary["steps"]} == {"retrieval", "recommendation_agent"}
