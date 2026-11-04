"""Unit tests for the coverage engine's four methods (ADR 050): no database."""

import uuid

import pytest

from app.services.coverage_engine import (
    DEFINITIONS,
    Item,
    Link,
    Method,
    Params,
    Status,
    Tree,
    compute,
    heatmap,
    link_weight,
    summarise,
)

P1, A, B, C, P2 = (uuid.uuid4() for _ in range(5))
OBJECTIVES = [uuid.uuid4() for _ in range(6)]


def tree() -> Tree:
    """P1 has three items below it (A, B, C); P2 is a group with nothing below it."""
    return Tree.of(
        [
            Item(C, "P1.3", "Third", P1, 1, 2),
            Item(P1, "P1", "First group", None, 0, 0),
            Item(A, "P1.1", "First", P1, 1, 0),
            Item(P2, "P2", "Second group", None, 0, 1),
            Item(B, "P1.2", "Second", P1, 1, 1),
        ]
    )


def link(item: uuid.UUID, coverage: int = 4, depth: str | None = "matches", **kw: object) -> Link:
    return Link(item, uuid.uuid4(), coverage, depth, **kw)  # type: ignore[arg-type]


LINKS = [
    link(A, 4),
    link(A, 4),
    link(A, 2, "below"),
    link(B, 3),
    link(P2, 1, bulk=True),
    link(P2, 1, bulk=True),
    link(P2, 1, bulk=True),
]


def by_code(results: list) -> dict:  # type: ignore[type-arg]
    return {r.item.code: r for r in results}


class TestTree:
    def test_items_come_in_tree_order_with_a_group_before_the_items_below_it(self) -> None:
        assert [i.code for i in tree().items] == ["P1", "P1.1", "P1.2", "P1.3", "P2"]

    def test_leaves_and_groups(self) -> None:
        t = tree()

        assert [t.by_id[i].code for i in t.leaves_below(P1)] == ["P1.1", "P1.2", "P1.3"]
        assert t.leaves_below(P2) == [P2]
        assert [g.code for g in t.groups()] == ["P1", "P2"]

    def test_an_item_whose_parent_is_missing_is_a_group(self) -> None:
        orphan = Item(uuid.uuid4(), "X", "Orphan", uuid.uuid4(), 3, 0)

        assert [g.code for g in Tree.of([orphan]).groups()] == ["X"]


class TestSingleMatch:
    def test_covered_with_one_accepted_link_and_a_group_by_its_own_links(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.SINGLE))

        assert got["P1.1"].status is Status.COVERED and got["P1.1"].links == 3
        assert got["P1.3"].status is Status.NONE and got["P1.3"].value == 0
        # The group has no link of its own: single match does not look below it.
        assert got["P1"].status is Status.NONE and got["P1"].leaves == 3
        assert got["P1"].leaves_covered == 2

    def test_counts_distinct_objectives_waiting_bulk_and_recheck(self) -> None:
        shared = uuid.uuid4()
        links = [
            Link(A, shared, 4, "matches", bulk=True),
            Link(A, shared, 3, "matches", bulk=True, needs_recheck=True),
            Link(A, uuid.uuid4(), 3, "matches"),
        ]

        got = by_code(compute(tree(), links, Method.SINGLE, waiting={A: 2, C: 1}))

        assert (got["P1.1"].links, got["P1.1"].objectives) == (3, 2)
        assert (got["P1.1"].bulk_links, got["P1.1"].recheck_links) == (2, 1)
        assert got["P1.1"].only_bulk is False
        assert (got["P1.1"].waiting, got["P1.3"].waiting) == (2, 1)

    def test_an_item_with_only_bulk_accepted_links_says_so(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.SINGLE))

        assert got["P2"].only_bulk is True and got["P1.2"].only_bulk is False

    def test_links_to_items_of_another_framework_are_ignored(self) -> None:
        got = compute(tree(), [link(uuid.uuid4())], Method.SINGLE)

        assert all(r.links == 0 for r in got)


class TestMultipleMatch:
    def test_covered_from_n_links_partial_below(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.MULTIPLE, Params(multiple_n=3)))

        assert got["P1.1"].status is Status.COVERED  # 3 links
        assert got["P1.2"].status is Status.PARTIAL and got["P1.2"].value == pytest.approx(1 / 3)
        assert got["P1.3"].status is Status.NONE
        assert got["P2"].status is Status.COVERED

    def test_n_is_configurable(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.MULTIPLE, Params(multiple_n=1)))

        assert got["P1.2"].status is Status.COVERED


class TestSubordinateMatch:
    def test_a_group_is_covered_by_the_share_of_items_below_it_that_have_a_link(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.SUBORDINATE))

        assert got["P1"].value == pytest.approx(2 / 3)
        assert got["P1"].status is Status.COVERED  # 67% of three items, from 50%
        assert got["P1.2"].status is Status.COVERED and got["P1.3"].status is Status.NONE

    def test_the_minimum_share_is_configurable(self) -> None:
        strict = Params(subordinate_min_share=0.8)

        got = by_code(compute(tree(), LINKS, Method.SUBORDINATE, strict))

        assert got["P1"].status is Status.PARTIAL

    def test_a_group_with_nothing_covered_below_it_is_a_gap(self) -> None:
        got = by_code(compute(tree(), [link(P1)], Method.SUBORDINATE))

        # A link on the group itself does not make the items below it covered.
        assert got["P1"].status is Status.NONE


class TestWeightedCoverage:
    def test_a_link_counts_its_coverage_out_of_five_and_a_low_depth_counts_less(self) -> None:
        params = Params()

        assert link_weight(link(A, 4), params) == pytest.approx(0.8)
        assert link_weight(link(A, 4, "below"), params) == pytest.approx(0.4)
        assert link_weight(link(A, 4, "above"), params) == pytest.approx(0.8)
        assert link_weight(link(A, 4, None), params) == pytest.approx(0.8)
        assert link_weight(link(A, 0), params) == 0

    def test_an_items_links_add_up_to_at_most_one(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.WEIGHTED))

        assert got["P1.1"].value == 1.0  # 0.8 + 0.8 + 0.2, capped
        assert got["P1.2"].value == pytest.approx(0.6)
        assert got["P1.3"].value == 0

    def test_a_group_is_the_better_of_its_own_links_and_the_average_below_it(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.WEIGHTED))
        own_better = compute(tree(), [*LINKS, link(P1, 5)], Method.WEIGHTED)

        assert got["P1"].value == pytest.approx((1.0 + 0.6 + 0.0) / 3)
        assert by_code(own_better)["P1"].value == 1.0

    def test_partial_below_the_low_line_covered_from_it(self) -> None:
        got = by_code(
            compute(
                tree(), [link(A, 2), link(B, 1), link(C, 4, "below")], Method.WEIGHTED, Params()
            )
        )

        assert got["P1.1"].status is Status.COVERED  # 0.4, exactly the line
        assert got["P1.2"].status is Status.PARTIAL  # 0.2
        assert got["P1.3"].status is Status.COVERED  # 0.8 halved is 0.4

    def test_the_settings_change_the_figures(self) -> None:
        params = Params(below_depth_factor=0.0, weighted_low=0.7)

        got = by_code(compute(tree(), [link(A, 4, "below"), link(B, 4)], Method.WEIGHTED, params))

        assert got["P1.1"].value == 0 and got["P1.2"].status is Status.COVERED


class TestSummaryAndHeatmap:
    def test_summary_counts_the_items_with_nothing_below_them_for_each_method(self) -> None:
        summary = summarise(tree(), LINKS, waiting_links=4)

        assert summary.leaves == 4  # P1.1, P1.2, P1.3 and P2
        assert summary.covered[Method.SINGLE] == 3 and summary.uncovered[Method.SINGLE] == 1
        assert summary.covered[Method.MULTIPLE] == 2 and summary.partial[Method.MULTIPLE] == 1
        assert summary.covered[Method.WEIGHTED] == 3
        assert (summary.links, summary.bulk_links, summary.waiting_links) == (7, 3, 4)

    def test_heatmap_gives_each_group_a_share_per_column(self) -> None:
        links = [
            link(A, column="y1"),
            link(B, column="y1"),
            link(B, column="y2"),
            link(P2, 1, column="programme"),
        ]

        grid = heatmap(tree(), links, Method.SINGLE, ["y1", "y2", "programme"])

        assert grid[P1]["all"] == pytest.approx(2 / 3)
        assert grid[P1]["y1"] == pytest.approx(2 / 3) and grid[P1]["y2"] == pytest.approx(1 / 3)
        assert grid[P1]["programme"] == 0
        assert grid[P2]["programme"] == 1 and grid[P2]["all"] == 1

    def test_heatmap_by_multiple_match_counts_links_towards_n(self) -> None:
        links = [link(A, column="y1"), link(A, column="y1"), link(A, column="y2")]

        grid = heatmap(tree(), links, Method.MULTIPLE, ["y1", "y2"])

        assert grid[P1]["y1"] == pytest.approx((2 / 3) / 3)
        assert grid[P1]["all"] == pytest.approx(1 / 3)

    def test_heatmap_weighted_adds_up_to_one_per_item(self) -> None:
        links = [link(A, 5, column="y1"), link(A, 5, column="y1")]

        grid = heatmap(tree(), links, Method.WEIGHTED, ["y1"])

        assert grid[P1]["y1"] == pytest.approx(1 / 3)


def test_every_method_has_its_own_definition_with_the_settings_it_names() -> None:
    assert set(DEFINITIONS) == set(Method)
    assert "{n}" in DEFINITIONS[Method.MULTIPLE]
    assert "{share}" in DEFINITIONS[Method.SUBORDINATE]
    assert "{factor}" in DEFINITIONS[Method.WEIGHTED] and "{low}" in DEFINITIONS[Method.WEIGHTED]
