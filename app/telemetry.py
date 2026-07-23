"""Local-first telemetry: spans, latency, and token/cost accounting.

Everything stays on-machine by default — no third-party SaaS. This is the
"logging + verification" layer of the harness: every pipeline step and LLM call
is measured so cost, latency, and token usage are visible and testable.

Design:
  - ``start_run()`` opens a RunTrace; ``span()`` / ``aspan()`` record nested steps
    with wall-clock latency; ``record_llm_usage()`` attaches tokens + estimated
    cost to the currently-open span and the run totals.
  - Safe by default: if telemetry is disabled or no run is open, every call is an
    inert no-op — instrumentation never breaks the pipeline.
  - Optional OpenTelemetry export when ``settings.telemetry_otel`` is on and the
    SDK is installed (guarded import). LangSmith is deliberately NOT wired here;
    enable it yourself with LANGCHAIN_TRACING_V2 if you ever want the SaaS.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import time
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger("booking.telemetry")


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass
class SpanRecord:
    name: str
    duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    attributes: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class RunTrace:
    name: str = "pipeline"
    spans: list[SpanRecord] = field(default_factory=list)

    @property
    def prompt_tokens(self) -> int:
        return sum(s.prompt_tokens for s in self.spans)

    @property
    def completion_tokens(self) -> int:
        return sum(s.completion_tokens for s in self.spans)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        return round(sum(s.cost_usd for s in self.spans), 6)

    @property
    def latency_ms(self) -> float:
        return round(sum(s.duration_ms for s in self.spans), 3)

    def summary(self) -> dict:
        return {
            "run": self.name,
            "spans": len(self.spans),
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "steps": [
                {
                    "name": s.name,
                    "ms": round(s.duration_ms, 1),
                    "tokens": s.total_tokens,
                    "cost_usd": round(s.cost_usd, 6),
                    **({"error": s.error} if s.error else {}),
                }
                for s in self.spans
            ],
        }


# --------------------------------------------------------------------------- #
# Context — current run / span (contextvars so async tasks stay isolated)
# --------------------------------------------------------------------------- #
_current_run: contextvars.ContextVar[RunTrace | None] = contextvars.ContextVar(
    "telemetry_current_run", default=None
)
_current_span: contextvars.ContextVar[SpanRecord | None] = contextvars.ContextVar(
    "telemetry_current_span", default=None
)

# The most recently completed run — a side channel for observability / tests so
# the pipeline's return contract (RecommendationResult) stays untouched.
_last_run: RunTrace | None = None


def start_run(name: str = "pipeline") -> RunTrace:
    """Open a fresh run trace and make it current. Returns the RunTrace."""
    run = RunTrace(name=name)
    _current_run.set(run)
    return run


def get_current_run() -> RunTrace | None:
    return _current_run.get()


def get_last_run() -> RunTrace | None:
    """The most recently completed run (for logging / assertions)."""
    return _last_run


def finish_run() -> RunTrace | None:
    """Close the current run: stash it as last_run, optionally log/console it."""
    global _last_run
    run = _current_run.get()
    if run is None:
        return None
    _last_run = run
    _current_run.set(None)
    if settings.telemetry_enabled:
        logger.info("telemetry %s", json.dumps(run.summary()))
        if settings.telemetry_console:
            _print_console(run)
    return run


# --------------------------------------------------------------------------- #
# Cost
# --------------------------------------------------------------------------- #
def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost estimate from the configurable per-1k chat prices."""
    return round(
        (prompt_tokens / 1000.0) * settings.chat_input_cost_per_1k
        + (completion_tokens / 1000.0) * settings.chat_output_cost_per_1k,
        6,
    )


def record_llm_usage(prompt_tokens: int, completion_tokens: int) -> float:
    """Attach LLM token usage + estimated cost to the current span.

    No-op (returns 0.0) if telemetry is off or no span is open. Returns the cost.
    """
    if not settings.telemetry_enabled:
        return 0.0
    span_rec = _current_span.get()
    cost = estimate_cost(prompt_tokens, completion_tokens)
    if span_rec is not None:
        span_rec.prompt_tokens += prompt_tokens
        span_rec.completion_tokens += completion_tokens
        span_rec.cost_usd += cost
    return cost


def _finalize_span(rec: SpanRecord, start: float, token, otel_span) -> None:
    rec.duration_ms = (time.perf_counter() - start) * 1000.0
    _current_span.reset(token)
    run = _current_run.get()
    if run is not None:
        run.spans.append(rec)
    if otel_span is not None:  # pragma: no cover - exercised only with OTel on
        otel_span.set_attribute("duration_ms", rec.duration_ms)
        otel_span.set_attribute("total_tokens", rec.total_tokens)
        otel_span.set_attribute("cost_usd", rec.cost_usd)
        if rec.error:
            otel_span.set_attribute("error", rec.error)
        otel_span.end()


@contextlib.contextmanager
def span(name: str, **attributes):
    """Synchronous span. Records latency; yields the SpanRecord for annotation."""
    if not settings.telemetry_enabled:
        yield SpanRecord(name=name)
        return
    rec = SpanRecord(name=name, attributes=dict(attributes))
    otel_span = _maybe_start_otel(name, attributes)
    token = _current_span.set(rec)
    start = time.perf_counter()
    try:
        yield rec
    except Exception as exc:  # noqa: BLE001 — record then re-raise
        rec.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _finalize_span(rec, start, token, otel_span)


@contextlib.asynccontextmanager
async def aspan(name: str, **attributes):
    """Async span — same semantics as ``span`` for ``async with`` blocks."""
    if not settings.telemetry_enabled:
        yield SpanRecord(name=name)
        return
    rec = SpanRecord(name=name, attributes=dict(attributes))
    otel_span = _maybe_start_otel(name, attributes)
    token = _current_span.set(rec)
    start = time.perf_counter()
    try:
        yield rec
    except Exception as exc:  # noqa: BLE001
        rec.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _finalize_span(rec, start, token, otel_span)


# --------------------------------------------------------------------------- #
# Optional OpenTelemetry backing (fully local; console/OTLP exporter is the
# user's choice via standard OTEL_* env vars). Import is guarded so the SDK is
# never a hard dependency.
# --------------------------------------------------------------------------- #
_otel_tracer = None


def _get_otel_tracer():
    global _otel_tracer
    if _otel_tracer is not None:
        return _otel_tracer
    try:  # pragma: no cover - only when opentelemetry is installed + enabled
        from opentelemetry import trace

        _otel_tracer = trace.get_tracer("booking.telemetry")
    except Exception:  # noqa: BLE001
        _otel_tracer = None
    return _otel_tracer


def _maybe_start_otel(name: str, attributes: dict):
    if not settings.telemetry_otel:
        return None
    tracer = _get_otel_tracer()
    if tracer is None:
        return None
    span_obj = tracer.start_span(name)  # pragma: no cover
    for k, v in attributes.items():  # pragma: no cover
        span_obj.set_attribute(str(k), v)
    return span_obj


def _print_console(run: RunTrace) -> None:
    line = (
        f"[telemetry] {run.name}: {run.latency_ms:.0f}ms, "
        f"{run.total_tokens} tok, ${run.cost_usd:.4f}"
    )
    print(line)
    for s in run.spans:
        print(
            f"    - {s.name:<24} {s.duration_ms:7.1f}ms  "
            f"{s.total_tokens:>6} tok  ${s.cost_usd:.4f}"
            + (f"  ERROR {s.error}" if s.error else "")
        )
