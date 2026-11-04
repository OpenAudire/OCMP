"""The rules of the role balance report (ADR 053, Slice 1.24a), without a database."""

import uuid

import pytest

from app.services.role_balance import NOTHING, Resolution, resolve, split_minutes

G1, G2, G3 = (uuid.uuid4() for _ in range(3))


class TestResolve:
    def test_an_objectives_own_links_come_first_and_are_not_estimated(self) -> None:
        assert resolve({G1}, [{G2}], {G3}) == Resolution(frozenset({G1}), False)

    def test_without_its_own_it_takes_the_groups_of_the_module_outcomes_it_links_up_to(
        self,
    ) -> None:
        assert resolve(set(), [{G2}, {G3}], {G1}) == Resolution(frozenset({G2, G3}), True)

    def test_upward_links_whose_outcomes_are_unmapped_leave_it_unmapped_not_the_modules(
        self,
    ) -> None:
        assert resolve(set(), [set()], {G1}) == NOTHING

    def test_with_no_upward_link_at_all_it_falls_back_to_the_outcomes_of_its_module(self) -> None:
        assert resolve(set(), [], {G1}) == Resolution(frozenset({G1}), True)
        assert resolve(set(), None, {G1}) == Resolution(frozenset({G1}), True)

    def test_nothing_found_is_not_mapped(self) -> None:
        assert resolve(set(), None, set()) == NOTHING


class TestSplit:
    def test_each_objective_gets_an_equal_share_divided_among_its_groups(self) -> None:
        # Two objectives share 120 minutes: 60 each. The first maps to two groups (30 + 30),
        # the second to one (60). Not an equal split per group (which would give 40 each).
        placed = split_minutes(
            120, [Resolution(frozenset({G1, G2}), False), Resolution(frozenset({G1}), False)]
        )

        totals: dict[uuid.UUID | None, float] = {}
        for group, minutes, _ in placed:
            totals[group] = totals.get(group, 0) + minutes
        assert totals == {G1: pytest.approx(90), G2: pytest.approx(30)}
        assert sum(totals.values()) == pytest.approx(120)

    def test_an_unmapped_objectives_share_is_not_mapped_and_estimates_are_marked(self) -> None:
        placed = split_minutes(
            90, [NOTHING, Resolution(frozenset({G3}), True), Resolution(frozenset({G1}), False)]
        )

        assert (None, 30, False) in [(g, pytest.approx(m), e) for g, m, e in placed]
        assert (G3, pytest.approx(30), True) in [(g, pytest.approx(m), e) for g, m, e in placed]
        assert (G1, pytest.approx(30), False) in [(g, pytest.approx(m), e) for g, m, e in placed]

    def test_no_time_or_no_objective_gives_nothing(self) -> None:
        assert split_minutes(0, [NOTHING]) == []
        assert split_minutes(60, []) == []
