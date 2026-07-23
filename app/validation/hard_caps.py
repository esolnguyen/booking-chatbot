"""Composable deterministic hard caps on recommendation confidence.

A *hard cap* is an architectural constraint the model cannot argue its way past:
when a deterministic signal fires (policy fail, inventory gone, fabricated price,
hallucinated evidence, ...), the harness forces confidence down to a ceiling,
regardless of what the LLM agents scored. This is the "make it legible and
enforceable" half of harness engineering — the caps live in one inspectable
registry instead of being scattered as inline ``min(confidence, x)`` calls.

Guardrails vs. verify (the distinction that motivates this file):
    - The confidence *formula* (router) and the LLM verifier catch soft, graded
      risk. They can be wrong.
    - These caps are the hard floor underneath them. They cannot be bypassed,
      so a wrong-but-confident recommendation still gets routed for review.

Ordering does not matter: caps compose by ``min``, which is commutative. Adding
a new deterministic trust boundary is a one-line entry here plus the signal that
drives it in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HardCap:
    """A single deterministic ceiling on confidence.

    name:  the signal key the pipeline sets True/False for this cap.
    cap:   confidence is forced to at most this value when the signal fires.
    flag:  risk flag to append when it fires, or None if the descriptive flag is
           added elsewhere (e.g. the hallucinated-refs flag carries the ref ids,
           so it is appended by the pipeline where those ids are known).
    """

    name: str
    cap: float
    flag: str | None = None


# The registry. Order is cosmetic (caps compose by min); it only affects the
# order appended flags appear in. Keep the strictest, most objective failures
# first for readability.
HARD_CAPS: list[HardCap] = [
    HardCap("price_mismatch", 0.30, "price_mismatch_in_explanation"),
    HardCap("fabricated_claims", 0.40, "fabricated_claims_in_explanation"),
    HardCap("inventory_unavailable", 0.40, "inventory_unavailable"),
    HardCap("policy_violation", 0.50, None),  # violations already flagged upstream
    HardCap("no_evidence_retrieved", 0.50, "no_evidence_retrieved"),
    # A fabricated citation is a trust failure even when the pick is compliant:
    # cap into the caution band (< auto_suggest 0.85, >= human_review 0.60) so it
    # can never silently auto-suggest. The "hallucinated_evidence_refs: <ids>"
    # flag is appended by the pipeline where the ids are known.
    HardCap("hallucinated_evidence", 0.70, None),
]

# Fast lookup / introspection for callers and tests.
HARD_CAPS_BY_NAME: dict[str, HardCap] = {hc.name: hc for hc in HARD_CAPS}


def apply_hard_caps(
    confidence: float,
    triggered: dict[str, bool],
) -> tuple[float, list[str]]:
    """Apply every triggered hard cap to ``confidence``.

    Args:
        confidence: the pre-cap confidence from the formula + verifier.
        triggered:  mapping of hard-cap name -> whether its signal fired. Unknown
                    keys are ignored; missing keys are treated as not-triggered.

    Returns:
        (capped_confidence, added_flags) — ``added_flags`` are the ``flag`` values
        of the caps that fired (in registry order), skipping any whose flag is
        None. The caller is responsible for extending its risk-flag list with them.
    """
    added_flags: list[str] = []
    for hc in HARD_CAPS:
        if triggered.get(hc.name):
            confidence = min(confidence, hc.cap)
            if hc.flag is not None:
                added_flags.append(hc.flag)
    return confidence, added_flags
