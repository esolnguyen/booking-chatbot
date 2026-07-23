"""CLI entry point for the routing eval harness.

Examples:
    python -m evals.run_evals                 # offline, zero Azure cost
    python -m evals.run_evals --live          # real LLM (needs Azure creds)
    python -m evals.run_evals --json          # machine-readable summary

Exit code is non-zero if any GUARANTEED (deterministic hard-cap) scenario fails,
so this is safe to wire into CI. Calibration divergences on soft scenarios are
reported but do NOT fail the run unless --strict is passed.
"""

from __future__ import annotations

import argparse
import json
import sys

from evals.harness import run_all
from evals.report import (
    build_report,
    format_report,
    grounding_rate,
    routing_metrics,
    trap_avoidance,
)


def _check_live_credentials() -> str | None:
    from app.config import settings

    missing = [
        name
        for name, val in (
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_CHAT_DEPLOYMENT", settings.azure_openai_chat_deployment),
        )
        if not val
    ]
    if missing:
        return "Missing Azure config for --live: " + ", ".join(missing)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Booking-chatbot routing evals")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run the real pipeline against Azure OpenAI (costs credits).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit a machine-readable JSON summary."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail the run on soft calibration divergences.",
    )
    parser.add_argument(
        "--ragas",
        action="store_true",
        help="Also run RAGAS RAG-quality metrics (requires --live + ragas installed).",
    )
    args = parser.parse_args(argv)

    if args.ragas and not args.live:
        print("--ragas requires --live (RAGAS needs a real LLM judge).", file=sys.stderr)
        return 2

    if args.live:
        err = _check_live_credentials()
        if err:
            print(err, file=sys.stderr)
            return 2

    outcomes = run_all(live=args.live)
    report = build_report(outcomes, live=args.live)

    ragas_scores = None
    if args.ragas:
        from evals.harness import load_golden_set
        from evals.ragas_eval import evaluate_rag

        try:
            ragas_scores = evaluate_rag(load_golden_set(), outcomes)
        except RuntimeError as exc:
            print(f"RAGAS skipped: {exc}", file=sys.stderr)

    if args.json:
        summary = {
            "mode": "live" if args.live else "offline",
            "ci_ok": report.ci_ok,
            "guaranteed_total": len(report.guaranteed),
            "guaranteed_failures": [g.id for g in report.guaranteed_failures],
            "divergences": [g.id for g in report.divergences],
            "routing_metrics": routing_metrics(report.grades),
            "grounding": grounding_rate(report.outcomes),
            "trap_avoidance": trap_avoidance(report.outcomes),
            **({"ragas": ragas_scores} if ragas_scores is not None else {}),
            "scenarios": [
                {
                    "id": g.id,
                    "guaranteed": g.guaranteed,
                    "expected_route": g.expected_route,
                    "actual_route": g.actual_route,
                    "confidence": None
                    if g.actual_confidence != g.actual_confidence
                    else round(g.actual_confidence, 3),
                    "passed": g.passed,
                    "reasons": g.reasons,
                }
                for g in report.grades
            ],
        }
        print(json.dumps(summary, indent=2))
    else:
        print(format_report(report))
        if ragas_scores is not None:
            print("\nRAGAS RAG-quality metrics:")
            for name, score in ragas_scores.items():
                print(f"  {name:<22}{score:.3f}" if isinstance(score, float)
                      else f"  {name:<22}{score}")

    failed = not report.ci_ok or (args.strict and report.divergences)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
