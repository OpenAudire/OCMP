"""The coverage engine: how well a framework is covered by accepted mapping links (Slices 1.21
and 1.21a, ADR 050). Pure functions: no database, no network.

The four methods follow the study the owner asked us to be comparable with (Theurich et al.
2025, as specified by the owner; this module was written from that specification, not from the
paper). Every figure the reports show names its method. An **item** below means a framework item
with nothing below it (a leaf); a **group** is an item with items below it.

* **single match**: an item is covered when at least one accepted link points at it. Headline: the
  share of items covered;
* **multiple match**: an item is covered when at least ``multiple_n`` accepted links point at it
  (default 3). No partial credit. Headline: the share of items covered;
* **subordinate match**: for each group, the percentage of the items below it that are covered by
  a single match. Headline: the average of those percentages over the groups. Groups under
  ``subordinate_min_share`` are listed in the gap report;
* **weighted content coverage**: each link scores its coverage out of 5, and loses one point (of
  the five) when its depth is *below* the target; the links of an item add up to at most 1.
  Headline, the "degree of coverage": the average over the items. Items under ``weighted_low`` are
  listed in the gap report.

For every method a group's figure is built up from the items below it. Links made directly to a
group are counted and shown on its row, but **do not count towards any figure**, so nothing is
counted twice.

Only links a person has accepted count. Links waiting for review are counted separately so a gap
can say "two suggestions are waiting". Links accepted in bulk and links that need a re-check are
counted and flagged, never hidden (brief section 8; Slice 1.13). Links accepted by an import
(``accept_method = imported``: decided in another tool, no reviewer recorded) are flagged the
same way (Slice 1.27a).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class Method(StrEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    SUBORDINATE = "subordinate"
    WEIGHTED = "weighted"


class Status(StrEnum):
    COVERED = "covered"
    PARTIAL = "partial"
    NONE = "none"


# The wording of each method as the reports print it. ``{n}``, ``{share}`` and ``{low}`` are
# filled from the institution's settings.
_BUILT_UP = (
    " A group's figure is built up from the items below it; links made directly to a group are "
    "shown apart and not counted."
)
DEFINITIONS: dict[Method, str] = {
    Method.SINGLE: (
        "An item (one with nothing below it) is covered when at least one accepted link points at "
        "it. Headline: the share of items covered." + _BUILT_UP
    ),
    Method.MULTIPLE: (
        "An item is covered when at least {n} accepted links point at it; with fewer it is not "
        "covered (no partial credit). Headline: the share of items covered." + _BUILT_UP
    ),
    Method.SUBORDINATE: (
        "For each group, the percentage of the items below it that are covered by a single match. "
        "Headline: the average of those percentages over the groups. Groups under {share}% are "
        "listed in the gap report. Links made directly to a group are shown apart and not counted."
    ),
    Method.WEIGHTED: (
        "Each accepted link scores its coverage out of 5, and loses one point when its depth is "
        "below what the item expects; an item's links add up to at most 100%. Headline, the "
        "degree of coverage: the average over the items. Items under {low}% are listed in the "
        "gap report." + _BUILT_UP
    ),
}


@dataclass(frozen=True)
class Params:
    multiple_n: int = 3
    # Shares as fractions of 1. Both only decide what the gap report lists.
    subordinate_min_share: float = 0.5
    weighted_low: float = 0.4


@dataclass(frozen=True)
class Item:
    id: uuid.UUID
    code: str
    title: str
    parent_id: uuid.UUID | None
    depth: int
    position: int


@dataclass(frozen=True)
class Link:
    """An accepted link, as far as coverage cares."""

    item_id: uuid.UUID
    objective_id: uuid.UUID
    coverage: int
    depth: str | None = None
    bulk: bool = False
    needs_recheck: bool = False
    imported: bool = False
    # The column of the heatmap it falls in: a phase id, "none" (a module without a phase) or
    # "programme" (a programme outcome).
    column: str = "none"


@dataclass
class ItemResult:
    item: Item
    is_leaf: bool
    # Items below this one that have no item below them (the item itself when it is one).
    leaves: int
    # Links made directly to this item. For a group they are shown apart and not used in its
    # figure, which is built up from the items below it.
    links: int = 0
    bulk_links: int = 0
    imported_links: int = 0
    recheck_links: int = 0
    # Links waiting for a decision (suggested, in review): not counted.
    waiting: int = 0
    # Distinct objectives behind the accepted links.
    objectives: int = 0
    # Items below that the method calls covered (a single match for subordinate match); None for
    # an item with nothing below it.
    leaves_covered: int | None = None
    # The chosen method's figure for this item, 0 to 1, and what it means.
    value: float = 0.0
    status: Status = Status.NONE
    # Every link behind this item was accepted in bulk: say so next to the figure.
    only_bulk: bool = False
    # Every link behind this item was accepted by an import.
    only_imported: bool = False


@dataclass
class Tree:
    """Items of one framework: children and leaves by item."""

    items: list[Item]
    children: dict[uuid.UUID | None, list[uuid.UUID]] = field(default_factory=dict)
    by_id: dict[uuid.UUID, Item] = field(default_factory=dict)

    @classmethod
    def of(cls, items: Iterable[Item]) -> Tree:
        ordered = sorted(items, key=lambda i: (i.depth, i.position, i.code))
        tree = cls(items=[])
        children: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
        for item in ordered:
            tree.by_id[item.id] = item
        for item in ordered:
            parent = item.parent_id if item.parent_id in tree.by_id else None
            children[parent].append(item.id)
        tree.children = dict(children)
        tree.items = tree._preorder()
        return tree

    def _preorder(self) -> list[Item]:
        out: list[Item] = []
        stack = list(reversed(self.children.get(None, [])))
        while stack:
            item_id = stack.pop()
            out.append(self.by_id[item_id])
            stack.extend(reversed(self.children.get(item_id, [])))
        return out

    def is_leaf(self, item_id: uuid.UUID) -> bool:
        return not self.children.get(item_id)

    def leaves_below(self, item_id: uuid.UUID) -> list[uuid.UUID]:
        """The items below with nothing below them; the item itself if it is a leaf."""
        if self.is_leaf(item_id):
            return [item_id]
        found: list[uuid.UUID] = []
        for child in self.children[item_id]:
            found.extend(self.leaves_below(child))
        return found

    def groups(self) -> list[Item]:
        """The top level items: the groups of the heatmap."""
        return [self.by_id[i] for i in self.children.get(None, [])]


def link_weight(link: Link, params: Params | None = None) -> float:
    """What one link scores for weighted coverage: its coverage out of 5, less one point of the
    five when its depth is below what the item expects. A link without a depth loses nothing."""
    points = max(0, min(5, link.coverage))
    if link.depth == "below":
        points = max(0, points - 1)
    return points / 5


def _leaf_value(links: Sequence[Link], method: Method, params: Params) -> float:
    """What one item scores for a method (0 to 1). Single, subordinate and multiple match are
    yes or no; weighted coverage is the sum of the links' scores, at most 1."""
    if method is Method.MULTIPLE:
        return 1.0 if len(links) >= params.multiple_n else 0.0
    if method is Method.WEIGHTED:
        return min(1.0, sum(link_weight(link) for link in links))
    return 1.0 if links else 0.0


def _leaf_status(value: float, method: Method, params: Params) -> Status:
    if method is Method.WEIGHTED:
        if value <= 0:
            return Status.NONE
        return Status.COVERED if value >= params.weighted_low - 1e-9 else Status.PARTIAL
    return Status.COVERED if value >= 1.0 else Status.NONE


def _group_status(value: float, method: Method, params: Params) -> Status:
    """Used to list groups in the gap report: subordinate match lists those under its share, the
    others call a group covered when every item below is (or, for weighted coverage, from the
    low line)."""
    if value <= 0:
        return Status.NONE
    if method is Method.SUBORDINATE:
        return Status.COVERED if value >= params.subordinate_min_share - 1e-9 else Status.PARTIAL
    if method is Method.WEIGHTED:
        return Status.COVERED if value >= params.weighted_low - 1e-9 else Status.PARTIAL
    return Status.COVERED if value >= 1.0 - 1e-9 else Status.PARTIAL


def compute(
    tree: Tree,
    links: Sequence[Link],
    method: Method,
    params: Params | None = None,
    waiting: dict[uuid.UUID, int] | None = None,
) -> list[ItemResult]:
    """One result per item, in tree order (a group before the items below it). A group's value is
    built up from the items below it; its own links are counted but not used."""
    params = params or Params()
    waiting = waiting or {}
    by_item: dict[uuid.UUID, list[Link]] = defaultdict(list)
    for link in links:
        if link.item_id in tree.by_id:
            by_item[link.item_id].append(link)

    leaf_values: dict[uuid.UUID, float] = {}
    leaf_covered: dict[uuid.UUID, bool] = {}
    for item in tree.items:
        if tree.is_leaf(item.id):
            leaf_values[item.id] = _leaf_value(by_item.get(item.id, []), method, params)
            leaf_covered[item.id] = (
                _leaf_status(leaf_values[item.id], method, params) is Status.COVERED
            )

    results: list[ItemResult] = []
    for item in tree.items:
        own = by_item.get(item.id, [])
        leaf = tree.is_leaf(item.id)
        leaves = tree.leaves_below(item.id)
        result = ItemResult(item=item, is_leaf=leaf, leaves=len(leaves))
        result.links = len(own)
        result.bulk_links = sum(1 for link in own if link.bulk)
        result.imported_links = sum(1 for link in own if link.imported)
        result.recheck_links = sum(1 for link in own if link.needs_recheck)
        result.waiting = waiting.get(item.id, 0)
        result.objectives = len({link.objective_id for link in own})
        result.only_bulk = bool(own) and result.bulk_links == len(own)
        result.only_imported = bool(own) and result.imported_links == len(own)
        if leaf:
            result.value = leaf_values[item.id]
            result.status = _leaf_status(result.value, method, params)
        else:
            result.leaves_covered = sum(1 for i in leaves if leaf_covered[i])
            if method is Method.WEIGHTED:
                result.value = sum(leaf_values[i] for i in leaves) / len(leaves)
            else:
                result.value = result.leaves_covered / len(leaves)
            result.status = _group_status(result.value, method, params)
        results.append(result)
    return results


# --- Roll-ups ------------------------------------------------------------------------------


@dataclass(frozen=True)
class MethodFigure:
    """One method's headline for the whole framework, with the counts behind it."""

    # A share of items (single, multiple, weighted) or the average over groups (subordinate); None
    # when there is nothing to average (subordinate match needs at least one group).
    headline: float | None
    # What the counts count: "items" or "groups".
    unit: str
    total: int
    covered: int
    partial: int
    uncovered: int


@dataclass(frozen=True)
class Summary:
    """The framework as a whole, for each method, and the counts a reader needs next to them."""

    leaves: int
    groups: int
    methods: dict[Method, MethodFigure]
    links: int
    # Accepted links made directly to a group: shown apart, not counted in any figure.
    group_links: int
    bulk_links: int
    recheck_links: int
    waiting_links: int
    imported_links: int = 0


def summarise(
    tree: Tree, links: Sequence[Link], params: Params | None = None, waiting_links: int = 0
) -> Summary:
    params = params or Params()
    known = [link for link in links if link.item_id in tree.by_id]
    leaves = [i for i in tree.items if tree.is_leaf(i.id)]
    groups = [i for i in tree.items if not tree.is_leaf(i.id)]
    methods: dict[Method, MethodFigure] = {}
    for method in Method:
        results = compute(tree, known, method, params)
        if method is Method.SUBORDINATE:
            rows = [r for r in results if not r.is_leaf]
            unit = "groups"
        else:
            rows = [r for r in results if r.is_leaf]
            unit = "items"
        statuses = [r.status for r in rows]
        if not rows:
            headline = None
        elif method in (Method.SUBORDINATE, Method.WEIGHTED):
            headline = sum(r.value for r in rows) / len(rows)
        else:
            headline = statuses.count(Status.COVERED) / len(rows)
        methods[method] = MethodFigure(
            headline=headline,
            unit=unit,
            total=len(rows),
            covered=statuses.count(Status.COVERED),
            partial=statuses.count(Status.PARTIAL),
            uncovered=statuses.count(Status.NONE),
        )
    group_ids = {g.id for g in groups}
    return Summary(
        leaves=len(leaves),
        groups=len(groups),
        methods=methods,
        links=len(known),
        group_links=sum(1 for link in known if link.item_id in group_ids),
        bulk_links=sum(1 for link in known if link.bulk),
        recheck_links=sum(1 for link in known if link.needs_recheck),
        waiting_links=waiting_links,
        imported_links=sum(1 for link in known if link.imported),
    )


def heatmap(
    tree: Tree,
    links: Sequence[Link],
    method: Method,
    columns: Sequence[str],
    params: Params | None = None,
) -> dict[uuid.UUID, dict[str, float]]:
    """For each group (top level item) and column: the average, over the items below it, of the
    item's value for the method using only the links in that column. The column ``"all"`` uses
    every link. Single and subordinate match give the same figure here: the share of items with
    at least one link. Links made directly to a group are not used."""
    params = params or Params()
    by_cell: dict[tuple[uuid.UUID, str], list[Link]] = defaultdict(list)
    by_item: dict[uuid.UUID, list[Link]] = defaultdict(list)
    for link in links:
        if link.item_id not in tree.by_id:
            continue
        by_cell[(link.item_id, link.column)].append(link)
        by_item[link.item_id].append(link)
    grid: dict[uuid.UUID, dict[str, float]] = {}
    for group in tree.groups():
        leaves = tree.leaves_below(group.id)
        row: dict[str, float] = {}
        for column in ("all", *columns):
            total = 0.0
            for leaf_id in leaves:
                cell = (
                    by_item.get(leaf_id, [])
                    if column == "all"
                    else by_cell.get((leaf_id, column), [])
                )
                total += _leaf_value(cell, method, params)
            row[column] = total / len(leaves) if leaves else 0.0
        grid[group.id] = row
    return grid
