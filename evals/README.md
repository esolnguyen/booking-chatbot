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
| `report.py` | Routing precision/recall/F1, confusion matrix, grounding rate, CI gate. |
| `run_evals.py` | CLI entry point. |
| `test_evals.py` | pytest CI gate — asserts the deterministic hard-cap scenarios. |

## Running

```bash
# Offline — deterministic, no network, no Azure spend (this is what CI runs):
python -m evals.run_evals
python -m evals.run_evals --json        # machine-readable summary
python -m pytest evals/test_evals.py    # the CI gate as pytest

# Live — real Azure OpenAI end to end (needs creds in .env); costs credits:
python -m evals.run_evals --live
```

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

## What it currently surfaces

The offline run flags one calibration divergence by design:

> `sydney-hallucinated-evidence-ref`: a recommendation citing a fabricated
> evidence ref (`POL-999`) still routes **auto_suggest** at confidence ~0.97.

A single hallucinated citation adds one risk flag and is dropped from grounded
evidence, but it is **not** a hard cap, so it barely dents confidence. If
fabricated evidence should force human review, that's a deliberate change to
make in `pipeline.py` (e.g. cap confidence when `hallucinated_refs` is non-empty),
and this scenario will confirm it.

## Live mode

In `--live` mode nothing is faked: the real agents pick options and cite
evidence. On top of routing, the report measures the **grounding rate**
(fraction of cited refs that were actually retrieved) and checks
`must_cite` / `avoid_policy_violation` expectations — i.e. whether the LLM's own
behaviour is trustworthy, which offline mode can't measure.
