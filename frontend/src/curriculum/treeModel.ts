import type {
  StructureEvent,
  StructureModule,
  StructurePhase,
  VersionStructure,
} from '../api/types';

/**
 * The builder's structure tree: programme (the version) > phases > modules > sessions,
 * with longitudinal modules in their own group after the phases.
 *
 * Node ids are also the `item` search parameter: `programme`, `phase:<id>`,
 * `module:<id>`, `event:<id>` and `longitudinal`.
 */
export type TreeItem =
  | { kind: 'programme'; structure: VersionStructure }
  | { kind: 'phase'; phase: StructurePhase }
  | { kind: 'longitudinal'; modules: StructureModule[] }
  | { kind: 'module'; module: StructureModule; phase: StructurePhase | null }
  | {
      kind: 'event';
      event: StructureEvent;
      module: StructureModule;
      phase: StructurePhase | null;
    };

export interface TreeNode {
  id: string;
  item: TreeItem;
  children: TreeNode[];
}

export const ROOT_ID = 'programme';
export const LONGITUDINAL_ID = 'longitudinal';

function moduleNode(module: StructureModule, phase: StructurePhase | null): TreeNode {
  return {
    id: `module:${module.id}`,
    item: { kind: 'module', module, phase },
    children: module.events.map((event) => ({
      id: `event:${event.id}`,
      item: { kind: 'event', event, module, phase },
      children: [],
    })),
  };
}

export function buildTree(structure: VersionStructure): TreeNode {
  const children: TreeNode[] = structure.phases.map((phase) => ({
    id: `phase:${phase.id}`,
    item: { kind: 'phase', phase },
    children: phase.modules.map((module) => moduleNode(module, phase)),
  }));
  if (structure.modules_without_phase.length > 0) {
    children.push({
      id: LONGITUDINAL_ID,
      item: { kind: 'longitudinal', modules: structure.modules_without_phase },
      children: structure.modules_without_phase.map((module) => moduleNode(module, null)),
    });
  }
  return { id: ROOT_ID, item: { kind: 'programme', structure }, children };
}

/** Whether the version has no modules at all (phases may exist). */
export function hasNoModules(structure: VersionStructure): boolean {
  return (
    structure.modules_without_phase.length === 0 &&
    structure.phases.every((phase) => phase.modules.length === 0)
  );
}

/** The node with this id and the ids of its ancestors (root first), or null. */
export function findNode(
  root: TreeNode,
  id: string
): { node: TreeNode; ancestors: string[] } | null {
  const walk = (node: TreeNode, ancestors: string[]): ReturnType<typeof findNode> => {
    if (node.id === id) return { node, ancestors };
    for (const child of node.children) {
      const found = walk(child, [...ancestors, node.id]);
      if (found) return found;
    }
    return null;
  };
  return walk(root, []);
}

export interface VisibleNode {
  node: TreeNode;
  /** 1 for the root. */
  level: number;
  /** Position among its siblings, from 1, and the number of siblings. */
  posInSet: number;
  setSize: number;
  parentId: string | null;
}

/** The nodes a person can see with these nodes expanded, in reading order. */
export function visibleNodes(root: TreeNode, expanded: ReadonlySet<string>): VisibleNode[] {
  const result: VisibleNode[] = [];
  const walk = (
    node: TreeNode,
    level: number,
    posInSet: number,
    setSize: number,
    parentId: string | null
  ) => {
    result.push({ node, level, posInSet, setSize, parentId });
    if (!expanded.has(node.id)) return;
    node.children.forEach((child, index) =>
      walk(child, level + 1, index + 1, node.children.length, node.id)
    );
  };
  walk(root, 1, 1, 1, null);
  return result;
}
