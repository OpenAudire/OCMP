"""Tests for the evaluation figures (ADR 048): precision, recall, kappa and the sweeps."""

import pytest

from app.services.eval_metrics import (
    CaseResult,
    Counts,
    GoldRow,
    Match,
    bulk_accept,
    bulk_sweep,
    case_differences,
    kappa_of,
    score,
    sweep,
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
        # Agree 85 of 100; the AI says yes to 25 and the gold set to 30: chance agreement 0.6.
        assert kappa_of(Counts(tp=20, fp=5, fn=10, tn=65)) == pytest.approx(0.625)

    def test_perfect_agreement_is_one(self) -> None:
        assert kappa_of(Counts(tp=5, fp=0, fn=0, tn=15)) == pytest.approx(1.0)

    def test_agreement_no_better_than_chance_is_zero(self) -> None:
        assert kappa_of(Counts(tp=1, fp=1, fn=1, tn=1)) == pytest.approx(0.0)

    def test_systematic_disagreement_is_negative(self) -> None:
        assert kappa_of(Counts(tp=0, fp=5, fn=5, tn=0)) < 0

    def test_nothing_to_agree_about_is_undefined(self) -> None:
        assert kappa_of(Counts(tp=0, fp=0, fn=0, tn=10)) is None
        assert kappa_of(Counts()) is None


class TestScore:
    def test_counts_precision_recall_and_f1(self) -> None:
        cases = [
            case(
                [GoldRow("A", 4), GoldRow("B", 3)],
                [Match("A", 4), Match("C", 2)],
                shortlist=["A", "B", "C", "D"],
            )
        ]

        result = score(cases)

        assert (result.counts.tp, result.counts.fp, result.counts.fn, result.counts.tn) == (
            1,
            1,
            1,
            1,
        )
        assert result.precision == 0.5 and result.recall == 0.5 and result.f1 == 0.5
        assert result.suggestions == 2 and result.objectives == 1

    def test_an_objective_that_maps_to_nothing_counts_wrong_suggestions_against_precision(
        self,
    ) -> None:
        result = score([case([], [Match("A", 3)], shortlist=["A", "B"])])

        assert result.precision == 0.0 and result.recall is None

    def test_a_gold_row_with_coverage_zero_is_a_no_and_stays_in_the_universe(self) -> None:
        result = score([case([GoldRow("A", 0)], [], shortlist=["B"])])

        assert result.counts == Counts(tp=0, fp=0, fn=0, tn=2)

    def test_gold_items_the_shortlist_never_showed_are_misses_and_lower_shortlist_recall(
        self,
    ) -> None:
        result = score([case([GoldRow("A", 4), GoldRow("Z", 4)], [Match("A", 4)], ["A", "B"])])

        assert result.counts.fn == 1
        assert result.shortlist_recall == 0.5
        assert result.recall == 0.5

    def test_failed_objectives_are_left_out_and_counted(self) -> None:
        result = score(
            [case([GoldRow("A", 4)], [Match("A", 4)]), case([GoldRow("A", 4)], [], failed=True)]
        )

        assert result.objectives == 1 and result.failed == 1 and result.recall == 1.0

    def test_no_cases_gives_no_ratios(self) -> None:
        result = score([])

        assert result.precision is None and result.kappa is None and result.objectives == 0

    def test_coverage_and_depth_agreement_are_read_on_agreed_items_only(self) -> None:
        cases = [
            case(
                [GoldRow("A", 4, "matches"), GoldRow("B", 5, "above"), GoldRow("C", 2)],
                [Match("A", 4, "matches"), Match("B", 3, "matches"), Match("D", 5, "below")],
            )
        ]

        result = score(cases)

        assert result.coverage_gap == pytest.approx(1.0)  # (0 + 2) / 2
        assert result.coverage_within_one == pytest.approx(0.5)
        assert result.depth_agreement == pytest.approx(0.5)  # A agrees, B does not

    def test_depth_is_not_compared_where_the_gold_set_gives_none(self) -> None:
        result = score([case([GoldRow("A", 4)], [Match("A", 4, "matches")])])

        assert result.depth_agreement is None


class TestThresholds:
    def test_a_higher_minimum_coverage_drops_weak_suggestions(self) -> None:
        cases = [case([GoldRow("A", 4)], [Match("A", 4), Match("B", 1), Match("C", 2)])]

        by_minimum = {row["min_coverage"]: row for row in sweep(cases)}

        assert by_minimum[1]["suggestions"] == 3
        assert by_minimum[2]["suggestions"] == 2
        assert by_minimum[3]["suggestions"] == 1
        assert by_minimum[1]["precision"] == pytest.approx(1 / 3)
        assert by_minimum[3]["precision"] == 1.0

    def test_the_most_specific_item_is_kept_when_a_child_is_also_suggested(self) -> None:
        cases = [
            case(
                [GoldRow("P.1", 4)],
                [Match("P", 4), Match("P.1", 4)],
                ancestors={"P.1": ("P",), "P": ()},
            )
        ]

        kept = score(cases, prefer_specific=True)
        both = score(cases, prefer_specific=False)

        assert kept.suggestions == 1 and kept.precision == 1.0
        assert both.suggestions == 2 and both.precision == 0.5

    def test_a_parent_alone_is_kept(self) -> None:
        cases = [case([GoldRow("P", 3)], [Match("P", 3)], ancestors={"P.1": ("P",)})]

        assert score(cases, prefer_specific=True).suggestions == 1

    def test_the_floor_keeps_only_confident_suggestions_and_the_rest_are_for_review(self) -> None:
        cases = [
            case(
                [GoldRow("A", 4), GoldRow("B", 4)],
                [
                    Match("A", 4, confidence=0.95),
                    Match("B", 4, confidence=0.7),
                    Match("C", 4, confidence=0.6),
                ],
            )
        ]

        high = bulk_accept(cases, floor=90)
        mid = bulk_accept(cases, floor=65)
        everything = bulk_accept(cases, floor=50)

        assert (high.accepted, high.right, high.wrong, high.left_for_review) == (1, 1, 0, 2)
        assert high.precision == 1.0 and high.recall == 0.5
        assert (mid.accepted, mid.right, mid.wrong) == (2, 2, 0)
        assert (everything.accepted, everything.wrong, everything.left_for_review) == (3, 1, 0)

    def test_a_suggestion_without_a_confidence_is_never_accepted_in_bulk(self) -> None:
        cases = [case([GoldRow("A", 4)], [Match("A", 4, confidence=None)])]

        assert bulk_accept(cases, floor=50).accepted == 0

    def test_bulk_sweep_lists_every_floor_in_order(self) -> None:
        cases = [case([GoldRow("A", 4)], [Match("A", 4, confidence=0.8)])]

        rows = bulk_sweep(cases)

        assert [r["floor"] for r in rows] == sorted(r["floor"] for r in rows)
        assert rows[0]["accepted"] == 1 and rows[-1]["accepted"] == 0


class TestDifferences:
    def test_lists_agreement_and_each_side_alone(self) -> None:
        one = case(
            [GoldRow("A", 4), GoldRow("Z", 3)], [Match("A", 4), Match("B", 3)], ["A", "B", "C"]
        )

        diff = case_differences(one)

        assert diff == {
            "agreed": ["A"],
            "only_ai": ["B"],
            "only_gold": ["Z"],
            "not_shown": ["Z"],
        }
