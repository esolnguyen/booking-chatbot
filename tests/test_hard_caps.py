"""Unit tests for the composable hard-cap registry (app/validation/hard_caps.py).

Pure and offline — no vector store, no network. These pin the deterministic
trust boundary: each signal forces confidence to its ceiling and (where
applicable) appends its risk flag.
"""

from app.validation.hard_caps import (
    HARD_CAPS,
    HARD_CAPS_BY_NAME,
    apply_hard_caps,
)


def test_no_signals_leaves_confidence_untouched():
    conf, flags = apply_hard_caps(0.97, {})
    assert conf == 0.97
    assert flags == []


def test_all_false_signals_leaves_confidence_untouched():
    triggered = {name: False for name in HARD_CAPS_BY_NAME}
    conf, flags = apply_hard_caps(0.97, triggered)
    assert conf == 0.97
    assert flags == []


def test_price_mismatch_caps_at_030_and_flags():
    conf, flags = apply_hard_caps(0.9, {"price_mismatch": True})
    assert conf == 0.30
    assert "price_mismatch_in_explanation" in flags


def test_fabricated_claims_caps_at_040_and_flags():
    conf, flags = apply_hard_caps(0.9, {"fabricated_claims": True})
    assert conf == 0.40
    assert "fabricated_claims_in_explanation" in flags


def test_inventory_unavailable_caps_at_040_and_flags():
    conf, flags = apply_hard_caps(0.9, {"inventory_unavailable": True})
    assert conf == 0.40
    assert "inventory_unavailable" in flags


def test_policy_violation_caps_at_050_without_flag():
    # Policy violations are already flagged upstream (with the specific reason),
    # so the cap itself adds no duplicate flag.
    conf, flags = apply_hard_caps(0.9, {"policy_violation": True})
    assert conf == 0.50
    assert flags == []


def test_no_evidence_retrieved_caps_at_050_and_flags():
    conf, flags = apply_hard_caps(0.9, {"no_evidence_retrieved": True})
    assert conf == 0.50
    assert "no_evidence_retrieved" in flags


def test_hallucinated_evidence_caps_into_caution_band_without_flag():
    # Caps at 0.70 -> below auto_suggest (0.85), at/above human_review (0.60):
    # forces at least suggest_with_caution. The descriptive "...refs: <ids>" flag
    # is appended by the pipeline where the ids are known, not here.
    conf, flags = apply_hard_caps(0.97, {"hallucinated_evidence": True})
    assert conf == 0.70
    assert flags == []


def test_hallucinated_evidence_does_not_raise_low_confidence():
    # A cap is a ceiling, never a floor — it must not lift an already-low score.
    conf, _ = apply_hard_caps(0.42, {"hallucinated_evidence": True})
    assert conf == 0.42


def test_multiple_signals_take_the_strictest_cap():
    # min() composition: price (0.30) beats hallucination (0.70).
    conf, flags = apply_hard_caps(
        0.95, {"hallucinated_evidence": True, "price_mismatch": True}
    )
    assert conf == 0.30
    assert "price_mismatch_in_explanation" in flags


def test_cap_order_is_commutative_for_confidence():
    a, _ = apply_hard_caps(0.9, {"inventory_unavailable": True, "price_mismatch": True})
    b, _ = apply_hard_caps(0.9, {"price_mismatch": True, "inventory_unavailable": True})
    assert a == b == 0.30


def test_unknown_signal_keys_are_ignored():
    conf, flags = apply_hard_caps(0.9, {"totally_made_up_signal": True})
    assert conf == 0.9
    assert flags == []


def test_registry_is_well_formed():
    names = [hc.name for hc in HARD_CAPS]
    assert len(names) == len(set(names)), "duplicate hard-cap names"
    for hc in HARD_CAPS:
        assert 0.0 <= hc.cap <= 1.0
