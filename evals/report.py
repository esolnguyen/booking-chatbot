"""Scoring and reporting for eval outcomes.

Separates two questions the harness answers:

  1. Do the DETERMINISTIC hard caps route correctly? (guaranteed scenarios — a
     real regression if any fail; CI gates on this.)
  2. Is the hand-tuned confidence formula / threshold calibration sound? (soft
     scenarios — disagreement with design intent is surfaced as a divergence,
     i.e. a calibration finding, not necessarily a bug.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evals.harness import ScenarioOutcome

ROUTES = ["auto_suggest", "suggest_with_caution", "human_review"]
_EPS = 1e-6


@dataclass
class ScenarioGrade:
    id: str
    title: str
    guaranteed: bool
    expected_route: str
    actual_route: str
    actual_confidence: float
    route_ok: bool
    confidence_ok: bool
    flags_ok: bool
    error: str | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and self.route_ok
            and self.confidence_ok
            and self.flags_ok
        )


def grade(outcome: ScenarioOutcome) -> ScenarioGrade:
    """Grade a single outcome against its expectations."""
    exp = outcome.expected
    reasons: list[str] = []

    if outcome.error is not None:
        return ScenarioGrade(
            id=outcome.id,
            title=outcome.title,
            guaranteed=bool(exp.get("guaranteed", False)),
            expected_route=exp.get("route", "?"),
            actual_route="error",
            actual_confidence=float("nan"),
            route_ok=False,
            confidence_ok=False,
            flags_ok=False,
            error=outcome.error,
            reasons=[f"pipeline error: {outcome.error}"],
        )

    route_ok = outcome.actual_route == exp["route"]
    if not route_ok:
        reasons.append(f"route {outcome.actual_route} != expected {exp['route']}")

    conf = outcome.actual_confidence
    confidence_ok = True
    if "max_confidence" in exp and conf > exp["max_confidence"] + _EPS:
        confidence_ok = False
        reasons.append(f"confidence {conf:.3f} > max {exp['max_confidence']}")
    if "min_confidence" in exp and conf < exp["min_confidence"] - _EPS:
        confidence_ok = False
        reasons.append(f"confidence {conf:.3f} < min {exp['min_confidence']}")

    flags_ok = True
    flags = outcome.result.risk_flags if outcome.result else []
    for substr in exp.get("risk_flags_include_substr", []):
        if not any(substr in f for f in flags):
            flags_ok = False
            reasons.append(f"missing risk flag containing '{substr}'")

    return ScenarioGrade(
        id=outcome.id,
        title=outcome.title,
        guaranteed=bool(exp.get("guaranteed", False)),
        expected_route=exp["route"],
        actual_route=outcome.actual_route,
        actual_confidence=conf,
        route_ok=route_ok,
        confidence_ok=confidence_ok,
        flags_ok=flags_ok,
        reasons=reasons,
    )


def confusion_matrix(grades: list[ScenarioGrade]) -> dict[str, dict[str, int]]:
    """expected (row) x actual (col) counts over routing classes."""
    matrix = {e: {a: 0 for a in ROUTES} for e in ROUTES}
    for g in grades:
        if g.expected_route in matrix and g.actual_route in matrix[g.expected_route]:
            matrix[g.expected_route][g.actual_route] += 1
    return matrix


def routing_metrics(grades: list[ScenarioGrade]) -> dict[str, dict[str, float]]:
    """Per-class precision / recall / F1 using expected as ground truth."""
    cm = confusion_matrix(grades)
    metrics: dict[str, dict[str, float]] = {}
    for c in ROUTES:
        tp = cm[c][c]
        fn = sum(cm[c][a] for a in ROUTES if a != c)
        fp = sum(cm[e][c] for e in ROUTES if e != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        metrics[c] = {"precision": precision, "recall": recall, "f1": f1,
                      "support": tp + fn}
    return metrics


def trap_avoidance(outcomes: list[ScenarioOutcome]) -> dict[str, object]:
    """How often the harness avoids the trap route on trap-labelled scenarios.

    A "trap" scenario carries ``expected.trap_route`` — the route a non-defensive
    harness would wrongly produce (the LLM's explanation reads fine, so the naive
    answer is auto_suggest) but a deterministic check should catch. The harness
    avoids the trap when its actual route differs from the trap route.
    """
    traps = [o for o in outcomes if o.expected.get("trap_route")]
    avoided = [o for o in traps if o.actual_route != o.expected["trap_route"]]
    fell_for = [o.id for o in traps if o.actual_route == o.expected["trap_route"]]
    return {
        "traps": len(traps),
        "avoided": len(avoided),
        "rate": len(avoided) / len(traps) if traps else 1.0,
        "fell_for": fell_for,
    }


def grounding_rate(outcomes: list[ScenarioOutcome]) -> dict[str, float]:
    """Aggregate evidence-grounding stats (most meaningful in live mode)."""
    grounded = sum(len(o.grounded_refs) for o in outcomes)
    hallucinated = sum(len(o.hallucinated_refs) for o in outcomes)
    total = grounded + hallucinated
    return {
        "grounded": grounded,
        "hallucinated": hallucinated,
        "claimed": total,
        "rate": grounded / total if total else 1.0,
    }


@dataclass
class Report:
    grades: list[ScenarioGrade]
    outcomes: list[ScenarioOutcome]
    live: bool

    @property
    def guaranteed(self) -> list[ScenarioGrade]:
        return [g for g in self.grades if g.guaranteed]

    @property
    def soft(self) -> list[ScenarioGrade]:
        return [g for g in self.grades if not g.guaranteed]

    @property
    def guaranteed_failures(self) -> list[ScenarioGrade]:
        return [g for g in self.guaranteed if not g.passed]

    @property
    def divergences(self) -> list[ScenarioGrade]:
        """Soft scenarios whose route disagrees with design intent."""
        return [g for g in self.soft if not g.route_ok]

    @property
    def traps_all_avoided(self) -> bool:
        """True if every trap-labelled scenario was routed away from its trap."""
        return trap_avoidance(self.outcomes)["rate"] == 1.0

    @property
    def ci_ok(self) -> bool:
        """CI gate: every guaranteed (hard-cap) scenario must pass."""
        return not self.guaranteed_failures


def build_report(outcomes: list[ScenarioOutcome], *, live: bool) -> Report:
    return Report([grade(o) for o in outcomes], outcomes, live)


# --------------------------------------------------------------------------- #
# Text formatting
# --------------------------------------------------------------------------- #

def _fmt_conf(c: float) -> str:
    return "  n/a" if c != c else f"{c:.3f}"  # NaN check


def format_report(report: Report) -> str:
    lines: list[str] = []
    mode = "LIVE (real Azure OpenAI)" if report.live else "OFFLINE (faked agents)"
    lines.append(f"Booking-chatbot routing evals — {mode}")
    lines.append("=" * 72)

    # Per-scenario table
    lines.append(
        f"{'':1} {'scenario':<34}{'conf':>7}  {'expected':<22}{'actual':<22}"
    )
    lines.append("-" * 72)
    for g in report.grades:
        mark = "OK " if g.passed else ("!! " if g.guaranteed else "~  ")
        tag = "[G]" if g.guaranteed else "   "
        lines.append(
            f"{mark}{tag}{g.id:<31}{_fmt_conf(g.actual_confidence):>7}  "
            f"{g.expected_route:<22}{g.actual_route:<22}"
        )
        for r in g.reasons:
            lines.append(f"        - {r}")
    lines.append("-" * 72)

    # Routing precision / recall
    lines.append("\nRouting metrics (expected = ground truth):")
    metrics = routing_metrics(report.grades)
    lines.append(f"  {'route':<22}{'prec':>7}{'recall':>8}{'f1':>7}{'n':>5}")
    for c in ROUTES:
        m = metrics[c]
        lines.append(
            f"  {c:<22}{m['precision']:>7.2f}{m['recall']:>8.2f}"
            f"{m['f1']:>7.2f}{int(m['support']):>5}"
        )
    overall = sum(1 for g in report.grades if g.route_ok) / max(len(report.grades), 1)
    lines.append(f"  overall routing accuracy: {overall:.2%}")

    # Confusion matrix
    lines.append("\nConfusion matrix (rows=expected, cols=actual):")
    cm = confusion_matrix(report.grades)
    short = {"auto_suggest": "auto", "suggest_with_caution": "caution",
             "human_review": "human"}
    header = "".join(f"{short[c]:>9}" for c in ROUTES)
    lines.append(f"  {'':<10}{header}")
    for e in ROUTES:
        row = "".join(f"{cm[e][a]:>9}" for a in ROUTES)
        lines.append(f"  {short[e]:<10}{row}")

    # Grounding (live is where this bites)
    gr = grounding_rate(report.outcomes)
    lines.append(
        f"\nEvidence grounding: {gr['grounded']}/{gr['claimed']} refs grounded "
        f"({gr['rate']:.1%}); {gr['hallucinated']} hallucinated"
    )

    # Trap avoidance — did deterministic checks catch the plausible-but-wrong picks?
    tr = trap_avoidance(report.outcomes)
    if tr["traps"]:
        line = (
            f"Trap avoidance: {tr['avoided']}/{tr['traps']} trap scenarios caught "
            f"({tr['rate']:.1%})"
        )
        if tr["fell_for"]:
            line += f" — FELL FOR: {', '.join(tr['fell_for'])}"
        lines.append(line)

    # Headline results
    lines.append("\n" + "=" * 72)
    n_guar = len(report.guaranteed)
    n_guar_pass = n_guar - len(report.guaranteed_failures)
    lines.append(
        f"Deterministic hard caps:  {n_guar_pass}/{n_guar} guaranteed scenarios pass"
        + ("  ✓" if report.ci_ok else "  ✗ REGRESSION")
    )
    if report.guaranteed_failures:
        for g in report.guaranteed_failures:
            lines.append(f"  ✗ {g.id}: {'; '.join(g.reasons)}")

    if report.divergences:
        lines.append(
            f"\nCalibration divergences: {len(report.divergences)} soft scenario(s) "
            "route against design intent —"
        )
        for g in report.divergences:
            lines.append(
                f"  ~ {g.id}: intent={g.expected_route} but got {g.actual_route} "
                f"at confidence {_fmt_conf(g.actual_confidence)}"
            )
        lines.append(
            "    (These indicate where the 0.85 / 0.60 thresholds or the weight "
            "formula may need tuning, not a code bug.)"
        )
    else:
        lines.append("\nCalibration: all soft scenarios match design intent.")

    return "\n".join(lines)
