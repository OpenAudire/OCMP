import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { moveLearningEvent, moveModule, movePhase } from '../api/endpoints';
import type { VersionStructure } from '../api/types';
import { editErrorMessage, useRefreshCurriculum } from './editing';
import type { TreeItem, TreeNode } from './treeModel';

/** Items that can be moved and copied: phases, modules and sessions. */
export type MovableItem = Extract<TreeItem, { kind: 'phase' | 'module' | 'event' }>;

export function isMovable(item: TreeItem): item is MovableItem {
  return item.kind === 'phase' || item.kind === 'module' || item.kind === 'event';
}

/** The item's name as people see it in the tree. */
export function itemName(item: MovableItem): string {
  switch (item.kind) {
    case 'phase':
      return item.phase.name;
    case 'module':
      return `${item.module.code} ${item.module.name}`;
    case 'event':
      return item.event.title;
  }
}

/**
 * Whether the user may move or copy the item (from the structure's `can_edit` flags;
 * the API checks every change). Phases and modules are the programme's structure;
 * sessions belong to their module.
 */
export function canRearrange(item: TreeItem, structure: VersionStructure): boolean {
  switch (item.kind) {
    case 'phase':
    case 'module':
      return structure.can_edit;
    case 'event':
      return item.module.can_edit;
    default:
      return false;
  }
}

/** Whether the user may move anything in this version (phases, modules or sessions). */
export function canRearrangeAny(structure: VersionStructure): boolean {
  const modules = [
    ...structure.phases.flatMap((phase) => phase.modules),
    ...structure.modules_without_phase,
  ];
  return structure.can_edit || modules.some((module) => module.can_edit);
}

/** Where a node sits among its siblings (from 0), or null for the root. */
export interface Placement {
  index: number;
  count: number;
}

export function placementOf(root: TreeNode, id: string): Placement | null {
  const walk = (node: TreeNode): Placement | null => {
    const target = node.children.find((child) => child.id === id);
    if (target) {
      // Phases share the root with the "Across phases" group, which stays last.
      const siblings = node.children.filter((child) => child.item.kind === target.item.kind);
      return { index: siblings.indexOf(target), count: siblings.length };
    }
    for (const child of node.children) {
      const found = walk(child);
      if (found) return found;
    }
    return null;
  };
  return walk(root);
}

function move(item: MovableItem, position: number): Promise<unknown> {
  switch (item.kind) {
    case 'phase':
      return movePhase(item.phase.id, position);
    case 'module':
      return moveModule(item.module.id, position);
    case 'event':
      return moveLearningEvent(item.event.id, position);
  }
}

export interface MoveRequest {
  item: MovableItem;
  /** The new place among the item's siblings, from 0. */
  position: number;
  count: number;
}

/**
 * Moves an item among its siblings and refetches the structure. `onMoved` gets the
 * confirmation to show; failures come back as a plain-language `error`.
 */
export function useMoveItem(versionId: string, onMoved: (message: string) => void) {
  const { t } = useTranslation();
  const refresh = useRefreshCurriculum(versionId);
  const mutation = useMutation({
    mutationFn: ({ item, position }: MoveRequest) => move(item, position),
    onSuccess: async (_saved, { item, position, count }) => {
      await refresh();
      onMoved(
        t('curriculum.reorder.moved', { name: itemName(item), position: position + 1, count })
      );
    },
  });
  return {
    move: (request: MoveRequest) => mutation.mutate(request),
    busy: mutation.isPending,
    error: mutation.isError ? editErrorMessage(t, mutation.error) : null,
    reset: mutation.reset,
  };
}
