# Routing eval harness

A golden-set evaluation harness for the recommendation pipeline. It answers the
question the unit tests can't: **are the confidence thresholds and routing rules
actually calibrated, and do the deterministic guardrails route as intended?**

It runs the **real** pipeline — router, policy/fact checkers, hard caps,
freshness, approval routing — and only fakes the two LLM agents and the vector
store. So it exercises the trust-critical decision logic with zero Azure cost.

## Layout

| File | Purpose |
|------|---------|
| `golden_set.yaml` | Labeled scenarios: request + agent pick + verifier signal + expected route/caps/citations. Built from the **real** `app/mock/seed_data.py`. |
| `fakes.py` | Deterministic stand-ins for `retrieve_context` and the two agents. |
| `harness.py` | Loads the golden set, runs each scenario (offline or live), captures the outcome. |
| `report.py` | Routing precision/recall/F1, confusion matrix, grounding rate, trap avoidance, CI gate. |
| `run_evals.py` | CLI entry point. |
| `test_evals.py` | pytest CI gate — asserts the deterministic hard-cap scenarios + trap avoidance. |

The deterministic hard caps themselves live in `app/validation/hard_caps.py` — a
single composable registry (`HARD_CAPS`) the pipeline applies. Adding a new trust
boundary is a one-line entry there plus the signal that drives it in the pipeline.

## Running

```bash
# Offline — deterministic, no network, no Azure spend (this is what CI runs):
python -m evals.run_evals
python -m evals.run_evals --json        # machine-readable summary
python -m pytest evals/test_evals.py    # the CI gate as pytest

# Live — real Azure OpenAI end to end (needs creds in .env); costs credits:
python -m evals.run_evals --live

# Live + RAGAS RAG-quality metrics (faithfulness / answer-relevancy / context
# precision). Needs `pip install ragas datasets` + Azure creds (the LLM judge):
python -m evals.run_evals --live --ragas
```

Every run also emits **local telemetry** (per-step latency, token counts, USD
cost) via `app/telemetry.py` — on-machine only, no third-party SaaS. Set
`TELEMETRY_CONSOLE=1` to print the span tree per run.

Exit code is non-zero if any **guaranteed** (deterministic hard-cap) scenario
regresses. Soft calibration divergences are reported but don't fail the run
unless you pass `--strict`.

## Two kinds of scenario

- **Guaranteed `[G]`** — the route is forced by a deterministic hard cap
  (inventory / policy / price / claim / no-inventory). A failure here is a real
  bug in the trust boundary. **CI gates on these.**
- **Soft** — the route depends on the hand-tuned confidence formula and the
  `0.85 / 0.60` thresholds. Disagreement with design intent is surfaced as a
  *calibration divergence* — a finding about threshold tuning, not a code bug.

## Trap scenarios

Some scenarios carry an `expected.trap_route` — the route a **non-defensive**
harness would wrongly produce. The recommendation agent's explanation reads fine
(so the naive answer is `auto_suggest`), but a deterministic check catches a
fabrication: a wrong total price, a hallucinated stop count, or a fabricated
citation. The harness "avoids the trap" when its actual route differs from the
trap route. The report prints a **trap-avoidance rate** and CI asserts it stays
at 100%. This is the harness-engineering version of the eval-harness "trap
answer": prove the guardrail fires on the plausible-but-wrong case, not just the
obvious one.

## Fabricated evidence is now a hard cap

Earlier this harness surfaced a calibration gap: a recommendation citing a
fabricated evidence ref (`POL-999`) still routed **auto_suggest** at ~0.97,
because a hallucinated citation was only a soft risk flag. That gap is closed —
`hallucinated_evidence` is now a deterministic hard cap (ceiling 0.70) in
`app/validation/hard_caps.py`, so any fabricated citation is forced to at least
`suggest_with_caution` and can never silently auto-suggest.
`sydney-hallucinated-evidence-ref` and `london-mixed-evidence-ref` (one real +
one fabricated ref) are now `[G]` guaranteed scenarios that confirm it.

## Retrieval relevance floor

`search_knowledge_base` supports an optional relevance floor
(`settings.retrieval_min_score`, default `0.0` = off) that drops weak matches so
they can't pollute the prompt context. When retrieval returns no evidence at all,
the pipeline's `no_evidence_retrieved` hard cap forces the recommendation into
review rather than letting the agent answer ungrounded.

## Live mode

In `--live` mode nothing is faked: the real agents pick options and cite
evidence. On top of routing, the report measures the **grounding rate**
(fraction of cited refs that were actually retrieved) and checks
`must_cite` / `avoid_policy_violation` expectations — i.e. whether the LLM's own
behaviour is trustworthy, which offline mode can't measure.
