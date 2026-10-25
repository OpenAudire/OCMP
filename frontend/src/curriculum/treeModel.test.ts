import { describe, expect, it } from 'vitest';

import { defaultVersionId, findVersion } from './currentVersion';
import { programmes, structure } from './testData';
import {
  buildTree,
  findNode,
  hasNoModules,
  LONGITUDINAL_ID,
  ROOT_ID,
  visibleNodes,
} from './treeModel';

describe('structure tree', () => {
  const root = buildTree(structure);

  it('puts phases in order, then modules without a phase in their own group', () => {
    expect(root.id).toBe(ROOT_ID);
    expect(root.children.map((node) => node.id)).toEqual(['phase:y1', 'phase:y2', LONGITUDINAL_ID]);
    expect(root.children[1].children.map((node) => node.id)).toEqual(['module:m2']);
    expect(root.children[1].children[0].children.map((node) => node.id)).toEqual([
      'event:e1',
      'event:e2',
    ]);
  });

  it('leaves out the group when every module has a phase', () => {
    const tree = buildTree({ ...structure, modules_without_phase: [] });

    expect(tree.children.map((node) => node.id)).toEqual(['phase:y1', 'phase:y2']);
  });

  it('finds a node with its ancestors', () => {
    const found = findNode(root, 'event:e2');

    expect(found?.ancestors).toEqual([ROOT_ID, 'phase:y2', 'module:m2']);
    expect(found?.node.item.kind).toBe('event');
    expect(findNode(root, 'module:unknown')).toBeNull();
  });

  it('lists only the open part of the tree, with levels and positions', () => {
    const rows = visibleNodes(root, new Set([ROOT_ID, 'phase:y2']));

    expect(rows.map((row) => [row.node.id, row.level, row.posInSet, row.setSize])).toEqual([
      [ROOT_ID, 1, 1, 1],
      ['phase:y1', 2, 1, 3],
      ['phase:y2', 2, 2, 3],
      ['module:m2', 3, 1, 1],
      [LONGITUDINAL_ID, 2, 3, 3],
    ]);
    expect(rows[3].parentId).toBe('phase:y2');
  });

  it('knows when a version has no modules', () => {
    expect(hasNoModules(structure)).toBe(false);
    expect(
      hasNoModules({
        ...structure,
        phases: structure.phases.map((phase) => ({ ...phase, modules: [] })),
        modules_without_phase: [],
      })
    ).toBe(true);
  });
});

describe('version choice', () => {
  it('opens the remembered version while it is still visible', () => {
    expect(defaultVersionId(programmes, 'n2026')).toBe('n2026');
  });

  it('otherwise opens the newest version of the first programme', () => {
    expect(defaultVersionId(programmes, 'gone')).toBe('v2027');
    expect(defaultVersionId(programmes, null)).toBe('v2027');
    expect(defaultVersionId([], null)).toBeNull();
  });

  it('finds the programme of a version', () => {
    expect(findVersion(programmes, 'v2026')?.programme.code).toBe('BHS');
    expect(findVersion(programmes, undefined)).toBeNull();
  });
});
