"""The figures of the evaluation harness (Slice 1.19, ADR 048): pure functions, no database.

One evaluation run keeps what the AI answered for every gold objective. These functions turn
those answers and the gold rows into precision, recall and Cohen's kappa, at any minimum coverage
and any bulk-accept floor, without calling the AI again.

**What is counted.** For each objective the *universe* is every item the AI was shown (its
shortlist) plus every item the gold set or the AI named. An item is *gold-positive* when the gold
row has coverage of at least ``GOLD_MIN_COVERAGE`` and *AI-positive* when the AI suggested it
(coverage at least the chosen minimum, and not dropped for a more specific child). Then:

* true positive: both say yes; false positive: only the AI says yes;
* false negative: only the gold set says yes (this includes items the shortlist never showed);
* true negative: neither says yes, among the universe's other items.

Cohen's kappa compares the two yes/no answers over the whole universe, so it depends on how many
items the shortlist shows (a long shortlist adds easy true negatives). Precision and recall do not
count true negatives. Both are reported with the shortlist size so a reader can see this.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

GOLD_MIN_COVERAGE = 1
MIN_COVERAGES = (1, 2, 3, 4, 5)
FLOORS = (50, 60, 70, 75, 80, 85, 90, 95, 100)


@dataclass(frozen=True)
class GoldRow:
    code: str
    coverage: int
    depth: str | None = None


@dataclass(frozen=True)
class Match:
    """One item the AI suggested for an objective."""

    code: str
    coverage: int
    depth: str | None = None
    # The model's own confidence, 0 to 1.
    confidence: float | None = None


@dataclass(frozen=True)
class CaseResult:
    """What the AI answered for one gold objective, and what the gold set says."""

    case_id: str
    gold: tuple[GoldRow, ...]
    shortlist: tuple[str, ...]
    matches: tuple[Match, ...]
    # Item code -> its parents, grandparents and so on (for the "most specific item" rule).
    ancestors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    failed: bool = False


@dataclass(frozen=True)
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn


@dataclass(frozen=True)
class Scores:
    """The figures for one setting. Ratios are ``None`` when they cannot be worked out."""

    counts: Counts
    precision: float | None
    recall: float | None
    f1: float | None
    kappa: float | None
    # Share of gold-positive items the shortlist showed at all (the ceiling for recall).
    shortlist_recall: float | None
    # On true positives: average gap between AI and gold coverage; share within one point; share
    # of gold depths (where the gold set gives one) that the AI matched.
    coverage_gap: float | None
    # Agreement on the coverage score (0 to 5) between the AI and the gold set, on the links both
    # made: the plain (unweighted) kappa, the figure comparable with the 0.68 that Theurich et al.
    # 2025 report between their two raters, and how many links it is worked out on. The
    # quadratic-weighted kappa is an extra: it forgives near misses.
    coverage_kappa: float | None
    coverage_kappa_weighted: float | None
    coverage_pairs: int
    coverage_within_one: float | None
    depth_agreement: float | None
    objectives: int
    failed: int
    suggestions: int
    average_shortlist: float | None


SCORE_LEVELS = 6  # coverage scores 0 to 5


def weighted_kappa(
    pairs: Sequence[tuple[int, int]], levels: int = SCORE_LEVELS, *, quadratic: bool = True
) -> float | None:
    """Cohen's kappa for two raters' scores on a scale. ``pairs`` are (first rater, second rater).

    With ``quadratic`` (the default) a disagreement counts for the square of its distance, so 1
    against 5 is far worse than 4 against 5. With ``quadratic=False`` it is the plain, unweighted
    kappa: any disagreement counts as one, however near, which is the figure Theurich et al. 2025
    report (0.68) and the one to compare with. ``None`` below two pairs or when the raters' scores
    give chance nothing to explain (everything identical on both sides)."""
    n = len(pairs)
    if n < 2:
        return None
    first = [0] * levels
    second = [0] * levels
    joint = [[0] * levels for _ in range(levels)]
    for a, b in pairs:
        a, b = max(0, min(levels - 1, a)), max(0, min(levels - 1, b))
        first[a] += 1
        second[b] += 1
        joint[a][b] += 1
    scale = (levels - 1) ** 2
    observed = expected = 0.0
    for i in range(levels):
        for j in range(levels):
            weight = (i - j) ** 2 / scale if quadratic else float(i != j)
            observed += weight * joint[i][j] / n
            expected += weight * (first[i] / n) * (second[j] / n)
    if expected == 0:
        return None
    return 1 - observed / expected


def score_kappa(pairs: Sequence[tuple[int, int]]) -> float | None:
    """Plain (unweighted) Cohen's kappa on the 0 to 5 coverage scores."""
    return weighted_kappa(pairs, quadratic=False)


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def kappa_of(counts: Counts) -> float | None:
    """Cohen's kappa for the two yes/no answers; ``None`` when chance agreement is complete
    (everything is one answer on both sides, so there is nothing to agree about)."""
    n = counts.total
    if n == 0:
        return None
    observed = (counts.tp + counts.tn) / n
    ai_yes = (counts.tp + counts.fp) / n
    gold_yes = (counts.tp + counts.fn) / n
    expected = ai_yes * gold_yes + (1 - ai_yes) * (1 - gold_yes)
    if expected >= 1:
        return None
    return (observed - expected) / (1 - expected)


def _suggested(case: CaseResult, min_coverage: int, prefer_specific: bool) -> list[Match]:
    """The AI's suggestions for a case as the pipeline would save them at these settings."""
    kept = [m for m in case.matches if m.coverage >= max(1, min_coverage)]
    if prefer_specific:
        named = {m.code for m in kept}
        kept = [
            m
            for m in kept
            if not any(
                m.code in case.ancestors.get(other, ()) for other in named if other != m.code
            )
        ]
    return kept


def _case_sets(
    case: CaseResult, min_coverage: int, prefer_specific: bool
) -> tuple[set[str], set[str], set[str], list[Match]]:
    gold_yes = {g.code for g in case.gold if g.coverage >= GOLD_MIN_COVERAGE}
    suggested = _suggested(case, min_coverage, prefer_specific)
    ai_yes = {m.code for m in suggested}
    universe = set(case.shortlist) | {g.code for g in case.gold} | {m.code for m in case.matches}
    return gold_yes, ai_yes, universe, suggested


def score(
    cases: Sequence[CaseResult],
    *,
    min_coverage: int = 1,
    prefer_specific: bool = True,
    floor: float | None = None,
) -> Scores:
    """The figures over all cases the AI answered. With ``floor`` (0 to 1) only the suggestions
    whose confidence reaches it count as AI-positive: those are what bulk accept would accept."""
    tp = fp = fn = tn = 0
    gaps: list[int] = []
    score_pairs: list[tuple[int, int]] = []
    depth_pairs: list[bool] = []
    shown = gold_total = 0
    suggestions = 0
    lengths: list[int] = []
    answered = [c for c in cases if not c.failed]
    for case in answered:
        gold_yes, ai_yes, universe, suggested = _case_sets(case, min_coverage, prefer_specific)
        if floor is not None:
            ai_yes = {
                m.code
                for m in suggested
                if m.confidence is not None and m.confidence >= floor - 1e-9
            }
        gold_by_code = {g.code: g for g in case.gold}
        suggested_by_code = {m.code: m for m in suggested}
        both = ai_yes & gold_yes
        tp += len(both)
        fp += len(ai_yes - gold_yes)
        fn += len(gold_yes - ai_yes)
        tn += len(universe - gold_yes - ai_yes)
        suggestions += len(ai_yes)
        lengths.append(len(case.shortlist))
        gold_total += len(gold_yes)
        shown += len(gold_yes & set(case.shortlist))
        for code in both:
            g, m = gold_by_code[code], suggested_by_code[code]
            gaps.append(abs(g.coverage - m.coverage))
            score_pairs.append((g.coverage, m.coverage))
            if g.depth is not None:
                depth_pairs.append(g.depth == m.depth)
    counts = Counts(tp, fp, fn, tn)
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    f1 = (
        None
        if precision is None or recall is None or precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )
    return Scores(
        counts=counts,
        precision=precision,
        recall=recall,
        f1=f1,
        kappa=kappa_of(counts),
        shortlist_recall=ratio(shown, gold_total),
        coverage_gap=ratio(sum(gaps), len(gaps)),
        coverage_kappa=score_kappa(score_pairs),
        coverage_kappa_weighted=weighted_kappa(score_pairs),
        coverage_pairs=len(score_pairs),
        coverage_within_one=ratio(sum(1 for g in gaps if g <= 1), len(gaps)),
        depth_agreement=ratio(sum(depth_pairs), len(depth_pairs)),
        objectives=len(answered),
        failed=len(cases) - len(answered),
        suggestions=suggestions,
        average_shortlist=ratio(sum(lengths), len(lengths)),
    )


@dataclass(frozen=True)
class BulkAccept:
    """What bulk accept at one floor would do to the suggestions of one setting."""

    floor: int
    # Suggestions at or above the floor (they would be accepted in bulk).
    accepted: int
    # Of those, the ones the gold set also has (right) and the ones it does not (wrong).
    right: int
    wrong: int
    # Share of the accepted suggestions that are right; None when none are accepted.
    precision: float | None
    # Suggestions left for a person to review, and how many of them are right.
    left_for_review: int
    left_right: int
    # Share of all gold-positive items that bulk accept alone would have accepted.
    recall: float | None


def bulk_accept(
    cases: Sequence[CaseResult], *, floor: int, min_coverage: int = 1, prefer_specific: bool = True
) -> BulkAccept:
    all_suggestions = score(cases, min_coverage=min_coverage, prefer_specific=prefer_specific)
    auto = score(
        cases, min_coverage=min_coverage, prefer_specific=prefer_specific, floor=floor / 100
    )
    right = auto.counts.tp
    wrong = auto.counts.fp
    return BulkAccept(
        floor=floor,
        accepted=auto.suggestions,
        right=right,
        wrong=wrong,
        precision=auto.precision,
        left_for_review=all_suggestions.suggestions - auto.suggestions,
        left_right=all_suggestions.counts.tp - right,
        recall=auto.recall,
    )


def sweep(
    cases: Sequence[CaseResult],
    *,
    min_coverages: Iterable[int] = MIN_COVERAGES,
    prefer_specific: bool = True,
) -> list[dict[str, Any]]:
    """The figures at each minimum coverage (for choosing ``ai_min_coverage``)."""
    rows = []
    for minimum in min_coverages:
        scores = score(cases, min_coverage=minimum, prefer_specific=prefer_specific)
        rows.append({"min_coverage": minimum, **scores_dict(scores)})
    return rows


def bulk_sweep(
    cases: Sequence[CaseResult],
    *,
    min_coverage: int = 1,
    floors: Iterable[int] = FLOORS,
    prefer_specific: bool = True,
) -> list[dict[str, Any]]:
    """What bulk accept would do at each floor (for choosing ``bulk_accept_min_percent``)."""
    return [
        asdict(
            bulk_accept(cases, floor=f, min_coverage=min_coverage, prefer_specific=prefer_specific)
        )
        for f in floors
    ]


def scores_dict(scores: Scores) -> dict[str, Any]:
    data = asdict(scores)
    data["counts"] = {**data["counts"], "total": scores.counts.total}
    return data


def case_differences(
    case: CaseResult, *, min_coverage: int = 1, prefer_specific: bool = True
) -> dict[str, list[str]]:
    """For one objective: items both agree on, items only the AI suggested, items only the
    gold set has, and which of those the shortlist never showed."""
    gold_yes, ai_yes, _, _ = _case_sets(case, min_coverage, prefer_specific)
    only_gold = sorted(gold_yes - ai_yes)
    return {
        "agreed": sorted(gold_yes & ai_yes),
        "only_ai": sorted(ai_yes - gold_yes),
        "only_gold": only_gold,
        "not_shown": [c for c in only_gold if c not in set(case.shortlist)],
    }
