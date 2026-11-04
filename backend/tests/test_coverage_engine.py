"""Unit tests for the coverage engine's four methods (ADR 050, as changed by Slice 1.21a): no
database. An "item" is a framework item with nothing below it; a "group" has items below it."""

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


def tree() -> Tree:
    """P1 is a group with three items below it (A, B, C); P2 is an item with nothing below it."""
    return Tree.of(
        [
            Item(C, "P1.3", "Third", P1, 1, 2),
            Item(P1, "P1", "First group", None, 0, 0),
            Item(A, "P1.1", "First", P1, 1, 0),
            Item(P2, "P2", "Second", None, 0, 1),
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

    def test_an_item_whose_parent_is_missing_is_top_level(self) -> None:
        orphan = Item(uuid.uuid4(), "X", "Orphan", uuid.uuid4(), 3, 0)

        assert [g.code for g in Tree.of([orphan]).groups()] == ["X"]


class TestSingleMatch:
    def test_an_item_is_covered_by_one_link_and_a_group_by_the_share_of_its_items(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.SINGLE))

        assert got["P1.1"].status is Status.COVERED and got["P1.1"].value == 1.0
        assert got["P1.3"].status is Status.NONE and got["P1.3"].value == 0
        assert got["P1"].value == pytest.approx(2 / 3) and got["P1"].leaves_covered == 2
        assert got["P1"].leaves == 3 and got["P1"].status is Status.PARTIAL

    def test_links_made_to_a_group_are_shown_but_do_not_count(self) -> None:
        with_group_link = [*LINKS, link(P1, 5), link(P1, 5), link(P1, 5)]

        plain = by_code(compute(tree(), LINKS, Method.SINGLE))
        got = by_code(compute(tree(), with_group_link, Method.SINGLE))

        assert got["P1"].links == 3 and plain["P1"].links == 0
        assert got["P1"].value == plain["P1"].value == pytest.approx(2 / 3)
        for method in (Method.MULTIPLE, Method.SUBORDINATE, Method.WEIGHTED):
            a = by_code(compute(tree(), LINKS, method))["P1"].value
            b = by_code(compute(tree(), with_group_link, method))["P1"].value
            assert a == b, method

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
    def test_an_item_is_covered_from_n_links_and_gets_no_partial_credit(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.MULTIPLE, Params(multiple_n=3)))

        assert got["P1.1"].status is Status.COVERED and got["P1.1"].value == 1.0
        assert got["P1.2"].status is Status.NONE and got["P1.2"].value == 0.0  # 1 link of 3
        assert got["P1.3"].status is Status.NONE
        assert got["P2"].status is Status.COVERED
        assert got["P1"].value == pytest.approx(1 / 3)  # one of its three items

    def test_n_is_configurable(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.MULTIPLE, Params(multiple_n=1)))

        assert got["P1.2"].status is Status.COVERED
        assert got["P1"].value == pytest.approx(2 / 3)


class TestSubordinateMatch:
    def test_a_group_is_the_percentage_of_its_items_covered_by_a_single_match(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.SUBORDINATE))

        assert got["P1"].value == pytest.approx(2 / 3)
        assert got["P1"].leaves_covered == 2 and got["P1"].leaves == 3

    def test_the_share_only_decides_whether_a_group_is_listed_as_a_gap(self) -> None:
        loose = by_code(compute(tree(), LINKS, Method.SUBORDINATE, Params()))
        strict = by_code(
            compute(tree(), LINKS, Method.SUBORDINATE, Params(subordinate_min_share=0.8))
        )

        assert loose["P1"].status is Status.COVERED
        assert strict["P1"].status is Status.PARTIAL
        assert loose["P1"].value == strict["P1"].value

    def test_a_group_with_nothing_covered_below_it_is_none_whatever_is_linked_to_it(self) -> None:
        got = by_code(compute(tree(), [link(P1)], Method.SUBORDINATE))

        assert got["P1"].status is Status.NONE and got["P1"].value == 0


class TestWeightedCoverage:
    def test_a_link_scores_its_coverage_out_of_five_and_a_depth_below_loses_one_point(self) -> None:
        assert link_weight(link(A, 4)) == pytest.approx(0.8)
        assert link_weight(link(A, 4, "below")) == pytest.approx(0.6)
        assert link_weight(link(A, 4, "above")) == pytest.approx(0.8)
        assert link_weight(link(A, 4, None)) == pytest.approx(0.8)
        assert link_weight(link(A, 1, "below")) == 0
        assert link_weight(link(A, 0, "below")) == 0
        assert link_weight(link(A, 0)) == 0

    def test_an_items_links_add_up_to_at_most_one(self) -> None:
        got = by_code(compute(tree(), LINKS, Method.WEIGHTED))

        assert got["P1.1"].value == 1.0  # 0.8 + 0.8 + 0.2, capped
        assert got["P1.2"].value == pytest.approx(0.6)
        assert got["P1.3"].value == 0
        assert got["P2"].value == pytest.approx(0.6)  # three links of 0.2

    def test_a_group_is_the_average_of_its_items_not_better_for_links_made_to_it(self) -> None:
        got = by_code(compute(tree(), [*LINKS, link(P1, 5)], Method.WEIGHTED))

        assert got["P1"].value == pytest.approx((1.0 + 0.6 + 0.0) / 3)

    def test_the_low_line_only_decides_what_the_gap_report_lists(self) -> None:
        got = by_code(
            compute(
                tree(), [link(A, 2), link(B, 1), link(C, 4, "below")], Method.WEIGHTED, Params()
            )
        )

        assert got["P1.1"].status is Status.COVERED  # 0.4, exactly the line
        assert got["P1.2"].status is Status.PARTIAL  # 0.2
        assert got["P1.3"].status is Status.COVERED  # (4 - 1) / 5 = 0.6
        assert got["P1.3"].value == pytest.approx(0.6)

    def test_the_low_line_is_configurable(self) -> None:
        got = by_code(compute(tree(), [link(B, 4)], Method.WEIGHTED, Params(weighted_low=0.9)))

        assert got["P1.2"].status is Status.PARTIAL


class TestSummaryAndHeatmap:
    def test_headlines(self) -> None:
        summary = summarise(tree(), LINKS, waiting_links=4)

        assert (summary.leaves, summary.groups) == (4, 1)
        single = summary.methods[Method.SINGLE]
        assert single.headline == pytest.approx(3 / 4) and single.unit == "items"
        assert (single.covered, single.uncovered, single.total) == (3, 1, 4)
        multiple = summary.methods[Method.MULTIPLE]
        assert multiple.headline == pytest.approx(2 / 4) and multiple.partial == 0
        subordinate = summary.methods[Method.SUBORDINATE]
        assert subordinate.headline == pytest.approx(2 / 3) and subordinate.unit == "groups"
        assert subordinate.total == 1
        weighted = summary.methods[Method.WEIGHTED]
        assert weighted.headline == pytest.approx((1.0 + 0.6 + 0.0 + 0.6) / 4)
        assert weighted.unit == "items"

    def test_the_subordinate_headline_averages_the_percentages_of_the_groups(self) -> None:
        d1, d2, d3, d4, d5 = (uuid.uuid4() for _ in range(5))
        two_groups = Tree.of(
            [
                Item(d1, "G1", "One", None, 0, 0),
                Item(d2, "G1.1", "a", d1, 1, 0),
                Item(d3, "G1.2", "b", d1, 1, 1),
                Item(d4, "G2", "Two", None, 0, 1),
                Item(d5, "G2.1", "c", d4, 1, 0),
            ]
        )

        summary = summarise(two_groups, [link(d2), link(d3)])  # G1 is 100%, G2 is 0%

        assert summary.methods[Method.SUBORDINATE].headline == pytest.approx(0.5)

    def test_no_groups_means_no_subordinate_headline(self) -> None:
        flat = Tree.of([Item(A, "A", "a", None, 0, 0)])

        summary = summarise(flat, [link(A)])

        assert summary.methods[Method.SUBORDINATE].headline is None
        assert summary.methods[Method.SINGLE].headline == 1.0

    def test_links_to_groups_are_counted_apart(self) -> None:
        summary = summarise(tree(), [*LINKS, link(P1), link(P1)])

        assert summary.group_links == 2 and summary.links == 9
        assert (summary.bulk_links, summary.recheck_links, summary.waiting_links) == (3, 0, 0)

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

    def test_heatmap_by_multiple_match_needs_n_links_in_the_same_column(self) -> None:
        links = [link(A, column="y1"), link(A, column="y1"), link(A, column="y2")]

        grid = heatmap(tree(), links, Method.MULTIPLE, ["y1", "y2"])

        assert grid[P1]["all"] == pytest.approx(1 / 3)  # three links in all
        assert grid[P1]["y1"] == 0 and grid[P1]["y2"] == 0  # no column alone has three

    def test_heatmap_weighted_adds_up_to_one_per_item(self) -> None:
        links = [link(A, 5, column="y1"), link(A, 5, column="y1"), link(P1, 5, column="y1")]

        grid = heatmap(tree(), links, Method.WEIGHTED, ["y1"])

        assert grid[P1]["y1"] == pytest.approx(1 / 3)  # the link made to the group is not used


def test_every_method_has_its_own_definition_with_the_settings_it_names() -> None:
    assert set(DEFINITIONS) == set(Method)
    assert "{n}" in DEFINITIONS[Method.MULTIPLE]
    assert "{share}" in DEFINITIONS[Method.SUBORDINATE]
    assert "{low}" in DEFINITIONS[Method.WEIGHTED]
    assert "{factor}" not in DEFINITIONS[Method.WEIGHTED]
    for text in DEFINITIONS.values():
        assert "not counted" in text  # links made to a group
