"""The coverage engine: how well a framework is covered by accepted mapping links (Slice 1.21,
ADR 050). Pure functions: no database, no network.

The brief asks for four labelled methods, and every figure the reports show names its method:

* **single match**: an item is covered when at least one accepted link points at it;
* **multiple match**: an item is covered when at least ``multiple_n`` accepted links point at it
  (default 3, configurable);
* **subordinate match**: a group is covered by the share of the items below it that are covered
  by a single match. A group is covered when that share reaches ``subordinate_min_share``;
* **weighted content coverage**: every link counts for its coverage score (0 to 5, as a share of
  5), reduced when the depth is below the target (``below_depth_factor``); the links of an item
  add up to at most 1; a group is the best of its own links and the average of the items below it.

Only links a person has accepted count. Links waiting for review are counted separately so a gap
can say "two suggestions are waiting". Links accepted in bulk and links that need a re-check are
counted and flagged, never hidden (brief section 8; Slice 1.13).
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


# The wording of each method as the reports print it. ``{n}``, ``{share}``, ``{factor}`` and
# ``{low}`` are filled from the institution's settings.
DEFINITIONS: dict[Method, str] = {
    Method.SINGLE: "Covered when at least one accepted link points at the item.",
    Method.MULTIPLE: (
        "Covered when at least {n} accepted links point at the item; fewer is partial."
    ),
    Method.SUBORDINATE: (
        "A group is covered when at least {share}% of the items below it are covered by a single "
        "match; an item without items below it is covered by a single match."
    ),
    Method.WEIGHTED: (
        "Each accepted link counts for its coverage score out of 5, and {factor}% of that when "
        "its depth is below what the item expects; an item's links add up to at most 100%. A "
        "group is the better of its own links and the average of the items below it. "
        "Covered from {low}%, partial below that."
    ),
}


@dataclass(frozen=True)
class Params:
    multiple_n: int = 3
    # Shares as fractions of 1.
    subordinate_min_share: float = 0.5
    below_depth_factor: float = 0.5
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
    # The column of the heatmap it falls in: a phase id, "none" (a module without a phase) or
    # "programme" (a programme outcome).
    column: str = "none"


@dataclass
class ItemResult:
    item: Item
    is_leaf: bool
    # Items below this one that have no item below them (the item itself when it is one).
    leaves: int
    links: int = 0
    bulk_links: int = 0
    recheck_links: int = 0
    # Links waiting for a decision (suggested, in review): not counted.
    waiting: int = 0
    # Distinct objectives behind the accepted links.
    objectives: int = 0
    # Leaves below covered by a single match; None for a leaf.
    leaves_covered: int | None = None
    # The share the chosen method gives, 0 to 1, and what it means.
    value: float = 0.0
    status: Status = Status.NONE
    # Every link behind this item was accepted in bulk: say so next to the figure.
    only_bulk: bool = False


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


def link_weight(link: Link, params: Params) -> float:
    """What one link contributes to weighted coverage: its coverage out of 5, reduced when its
    depth is below what the item expects. A link without a depth is not reduced."""
    base = max(0, min(5, link.coverage)) / 5
    return base * params.below_depth_factor if link.depth == "below" else base


def _leaf_value(links: Sequence[Link], method: Method, params: Params) -> float:
    """What one item without items below it scores for a method (0 to 1)."""
    if method is Method.MULTIPLE:
        return min(1.0, len(links) / params.multiple_n)
    if method is Method.WEIGHTED:
        return min(1.0, sum(link_weight(link, params) for link in links))
    return 1.0 if links else 0.0


def _status(value: float, method: Method, params: Params, links: int) -> Status:
    if method is Method.WEIGHTED:
        if value <= 0:
            return Status.NONE
        return Status.COVERED if value >= params.weighted_low - 1e-9 else Status.PARTIAL
    if method is Method.MULTIPLE:
        if links >= params.multiple_n:
            return Status.COVERED
        return Status.PARTIAL if links > 0 else Status.NONE
    if method is Method.SUBORDINATE:
        if value <= 0:
            return Status.NONE
        return Status.COVERED if value >= params.subordinate_min_share - 1e-9 else Status.PARTIAL
    return Status.COVERED if links > 0 else Status.NONE


def compute(
    tree: Tree,
    links: Sequence[Link],
    method: Method,
    params: Params | None = None,
    waiting: dict[uuid.UUID, int] | None = None,
) -> list[ItemResult]:
    """One result per item, in tree order (a group before the items below it)."""
    params = params or Params()
    waiting = waiting or {}
    by_item: dict[uuid.UUID, list[Link]] = defaultdict(list)
    for link in links:
        if link.item_id in tree.by_id:
            by_item[link.item_id].append(link)

    leaf_values: dict[uuid.UUID, float] = {}
    for item in tree.items:
        if tree.is_leaf(item.id):
            leaf_values[item.id] = _leaf_value(by_item.get(item.id, []), method, params)

    results: list[ItemResult] = []
    for item in tree.items:
        own = by_item.get(item.id, [])
        leaf = tree.is_leaf(item.id)
        leaves = tree.leaves_below(item.id)
        result = ItemResult(item=item, is_leaf=leaf, leaves=len(leaves))
        result.links = len(own)
        result.bulk_links = sum(1 for link in own if link.bulk)
        result.recheck_links = sum(1 for link in own if link.needs_recheck)
        result.waiting = waiting.get(item.id, 0)
        result.objectives = len({link.objective_id for link in own})
        result.only_bulk = bool(own) and result.bulk_links == len(own)
        if not leaf:
            result.leaves_covered = sum(1 for leaf_id in leaves if by_item.get(leaf_id))
        # The value of the chosen method. A group's single and multiple match use its own links;
        # subordinate and weighted match look at the items below it.
        if not leaf and method is Method.SUBORDINATE:
            result.value = (result.leaves_covered or 0) / len(leaves)
        elif not leaf and method is Method.WEIGHTED:
            mean = sum(leaf_values[i] for i in leaves) / len(leaves)
            result.value = max(_leaf_value(own, method, params), mean)
        else:
            result.value = _leaf_value(own, method, params)
        result.status = _status(result.value, method, params, len(own))
        results.append(result)
    return results


# --- Roll-ups ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Summary:
    """The framework as a whole, for each method (shares of the items that have nothing below
    them) and the counts a reader needs next to them."""

    leaves: int
    covered: dict[Method, int]
    partial: dict[Method, int]
    uncovered: dict[Method, int]
    links: int
    bulk_links: int
    recheck_links: int
    waiting_links: int


def summarise(
    tree: Tree, links: Sequence[Link], params: Params | None = None, waiting_links: int = 0
) -> Summary:
    params = params or Params()
    leaf_ids = [i.id for i in tree.items if tree.is_leaf(i.id)]
    covered: dict[Method, int] = {}
    partial: dict[Method, int] = {}
    uncovered: dict[Method, int] = {}
    by_item: dict[uuid.UUID, list[Link]] = defaultdict(list)
    for link in links:
        if link.item_id in tree.by_id:
            by_item[link.item_id].append(link)
    for method in Method:
        statuses = [
            _status(
                _leaf_value(by_item.get(i, []), method, params),
                method,
                params,
                len(by_item.get(i, [])),
            )
            for i in leaf_ids
        ]
        covered[method] = statuses.count(Status.COVERED)
        partial[method] = statuses.count(Status.PARTIAL)
        uncovered[method] = statuses.count(Status.NONE)
    known = [link for link in links if link.item_id in tree.by_id]
    return Summary(
        leaves=len(leaf_ids),
        covered=covered,
        partial=partial,
        uncovered=uncovered,
        links=len(known),
        bulk_links=sum(1 for link in known if link.bulk),
        recheck_links=sum(1 for link in known if link.needs_recheck),
        waiting_links=waiting_links,
    )


def heatmap(
    tree: Tree,
    links: Sequence[Link],
    method: Method,
    columns: Sequence[str],
    params: Params | None = None,
) -> dict[uuid.UUID, dict[str, float]]:
    """For each group (top level item) and column: the average, over the group's items that have
    nothing below them, of the item's value for the method using only the links in that column.
    The column ``"all"`` uses every link. Single and subordinate match give the same figure here:
    the share of the group's items that have at least one link."""
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
