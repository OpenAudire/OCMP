"""Tests for the evaluation figures (ADR 048): precision, recall, kappa and the sweeps."""

import pytest

from app.services.eval_metrics import (
    CaseResult,
    GoldRow,
    Match,
    score,
    score_kappa,
    weighted_kappa,
)


def case(
    gold: list[GoldRow],
    matches: list[Match],
    shortlist: list[str] | None = None,
    ancestors: dict[str, tuple[str, ...]] | None = None,
    failed: bool = False,
) -> CaseResult:
    codes = shortlist if shortlist is not None else sorted({m.code for m in matches})
    return CaseResult(
        case_id="c",
        gold=tuple(gold),
        shortlist=tuple(codes),
        matches=tuple(matches),
        ancestors=ancestors or {},
        failed=failed,
    )


class TestKappa:
    def test_a_worked_example(self) -> None:
        # The first rater says 3, 5, 3, 5 and the second 3, 5, 5, 5. Only the third pair differs,
        # by 2 points: weight (2/5)^2 = 0.16, so observed disagreement is 0.16 / 4 = 0.04.
        # Chance: the first rater's shares (3: 1/2, 5: 1/2) against the second's (3: 1/4, 5: 3/4)
        # disagree at 0.16 x (1/2 x 3/4 + 1/2 x 1/4) = 0.08. Kappa = 1 - 0.04 / 0.08 = 0.5.
        pairs = [(3, 3), (5, 5), (3, 5), (5, 5)]

        assert weighted_kappa(pairs) == pytest.approx(0.5)

    def test_plain_kappa_counts_all_disagreements_alike_and_weighted_forgives_near_misses(
        self,
    ) -> None:
        # Seven links; one differs by a single point (3 against 4). Disagreement seen: 1/7.
        # By chance (first rater 1: 2, 3: 3, 5: 2; second 1: 2, 3: 2, 4: 1, 5: 2): 1 - 14/49 = 5/7.
        # Plain kappa = 1 - (1/7) / (5/7) = 0.8.
        pairs = [(3, 4), (1, 1), (5, 5), (3, 3), (1, 1), (5, 5), (3, 3)]

        assert score_kappa(pairs) == pytest.approx(0.8)
        weighted = weighted_kappa(pairs)
        assert weighted is not None and weighted > 0.8

    def test_not_enough_to_say(self) -> None:
        assert weighted_kappa([]) is None
        assert weighted_kappa([(3, 3)]) is None
        assert weighted_kappa([(3, 3), (3, 3)]) is None  # nothing for chance to explain

    def test_the_figures_carry_it_with_the_number_of_links_it_rests_on(self) -> None:
        cases = [
            case(
                [GoldRow("A", 4), GoldRow("B", 5), GoldRow("C", 2)],
                [Match("A", 4), Match("B", 3), Match("C", 2), Match("D", 5)],
            )
        ]

        result = score(cases)

        assert result.coverage_pairs == 3  # D is not in the gold set
        assert result.coverage_kappa is not None and result.coverage_kappa_weighted is not None
        one = score([case([GoldRow("A", 4)], [Match("A", 4)])])
        assert one.coverage_pairs == 1 and one.coverage_kappa is None
        assert score([]).coverage_kappa is None
