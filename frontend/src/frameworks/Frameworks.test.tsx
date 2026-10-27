import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type {
  FrameworkItemDetail,
  FrameworkItemPage,
  FrameworkLibrary,
  FrameworkSummary,
  FrameworkTreeItem,
  WhereMapped,
} from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchFrameworkLibrary: vi.fn(),
  fetchFrameworkItems: vi.fn(),
  searchFramework: vi.fn(),
  fetchFrameworkItem: vi.fn(),
  fetchWhereMapped: vi.fn(),
  deleteFramework: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function framework(overrides: Partial<FrameworkSummary> = {}): FrameworkSummary {
  return {
    id: 'f1',
    key: 'demo',
    name: 'Demo Graduate Competencies',
    version_label: '1.0',
    publisher: 'Demo University',
    licence_note: 'Fictional framework for tests',
    description: 'A fictional framework.',
    url: null,
    profile: 'core',
    status: 'active',
    item_count: 6,
    top_level_count: 2,
    level_count: 3,
    ...overrides,
  };
}

const library: FrameworkLibrary = {
  can_manage: true,
  frameworks: [
    framework(),
    framework({ id: 'f0', version_label: '0.9', status: 'superseded', item_count: 4 }),
    framework({
      id: 'f2',
      key: 'nqf',
      name: 'NQF levels',
      licence_note: '',
      profile: 'other',
      status: 'draft',
      item_count: 0,
      top_level_count: 0,
      level_count: 0,
    }),
  ],
};

function item(code: string, title: string, extra: Partial<FrameworkTreeItem> = {}) {
  return {
    id: `id-${code}`,
    code,
    title,
    depth: 0,
    child_count: 0,
    mapped_count: 0,
    ...extra,
  } satisfies FrameworkTreeItem;
}

const areaA = item('A', 'Clinical reasoning', { child_count: 2, mapped_count: 3 });
const areaB = item('B', 'Communication');
const childA1 = item('A.1', 'Gather history', { depth: 1, mapped_count: 2 });
const childA2 = item('A.2', 'Examine the patient', { depth: 1 });

function page(parentId: string | null, items: FrameworkTreeItem[], total = items.length, offset = 0) {
  return { parent_id: parentId, offset, total, items } satisfies FrameworkItemPage;
}

function detail(
  source: FrameworkTreeItem,
  extra: Partial<FrameworkItemDetail> = {}
): FrameworkItemDetail {
  return {
    id: source.id,
    framework_id: 'f1',
    code: source.code,
    title: source.title,
    description: `About ${source.title}.`,
    depth: source.depth,
    child_count: source.child_count,
    mapped_count: source.mapped_count,
    path: [],
    sibling_index: 0,
    ...extra,
  };
}

const mappings: WhereMapped = {
  item_id: childA1.id,
  total: 2,
  limit: 200,
  mappings: [
    {
      link_id: 'l1',
      status: 'accepted',
      source: 'human',
      coverage: 4,
      depth_match: 'matches',
      needs_recheck: true,
      needs_discussion: false,
      objective_id: 'o1',
      objective_text: 'Describe the cardiac cycle.',
      level: 'learning_event',
      programme_id: 'p1',
      programme_name: 'BSc Health Sciences (Demo)',
      version_id: 'v1',
      academic_year: 2026,
      version_status: 'published',
      module_id: 'm1',
      module_code: 'HSC201',
      module_name: 'Cardiovascular system',
      learning_event_id: 'e1',
      learning_event_title: 'Cardiac cycle',
    },
    {
      link_id: 'l2',
      status: 'suggested',
      source: 'ai',
      coverage: null,
      depth_match: null,
      needs_recheck: false,
      needs_discussion: false,
      objective_id: 'o2',
      objective_text: 'Reason clinically.',
      level: 'programme',
      programme_id: 'p1',
      programme_name: 'BSc Health Sciences (Demo)',
      version_id: 'v1',
      academic_year: 2026,
      version_status: 'published',
      module_id: null,
      module_code: null,
      module_name: null,
      learning_event_id: null,
      learning_event_title: null,
    },
  ],
};

function signIn(permissions: string[]) {
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([role('r', permissions)]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
}

describe('framework library', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    signIn(['frameworks.manage', 'curriculum.view']);
    mocked.fetchFrameworkLibrary.mockResolvedValue(library);
  });

  it('lists each framework once with its versions, counts and licence note', async () => {
    renderAt('/frameworks');

    const cards = within(await screen.findByRole('list', { name: 'Frameworks' }));
    expect(cards.getAllByRole('listitem')).toHaveLength(2);
    expect(cards.getByText('Demo Graduate Competencies')).toBeInTheDocument();
    expect(cards.getByText(/Version 1\.0, 6 items, 3 levels/)).toBeInTheDocument();
    expect(cards.getByText(/2 versions/)).toBeInTheDocument();
    expect(cards.getByText('Nothing in this version yet', { exact: false })).toBeInTheDocument();

    const details = within(screen.getByRole('region', { name: 'Framework details' }));
    expect(details.getByText('Fictional framework for tests')).toBeInTheDocument();
    expect(details.getByText('Demo University')).toBeInTheDocument();
    expect(details.getByText('Version 0.9')).toBeInTheDocument();
    expect(details.getByText('Superseded')).toBeInTheDocument();
    expect(details.getAllByText('Active').length).toBeGreaterThan(0);
  });

  it('shows another framework when its card is pressed', async () => {
    renderAt('/frameworks');
    await screen.findByRole('list', { name: 'Frameworks' });

    const second = screen.getByRole('button', { name: /NQF levels/ });
    expect(second).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(second);

    expect(second).toHaveAttribute('aria-pressed', 'true');
    const details = within(screen.getByRole('region', { name: 'Framework details' }));
    expect(details.getByRole('heading', { name: 'NQF levels' })).toBeInTheDocument();
    expect(details.getByText('No licence note was given with this framework.')).toBeInTheDocument();
  });

  it('links each version to its browser', async () => {
    renderAt('/frameworks');

    const link = await screen.findByRole('link', {
      name: 'Browse Demo Graduate Competencies version 0.9',
    });

    expect(link).toHaveAttribute('href', '/frameworks/f0');
  });

  it('offers import and delete only to people who manage frameworks', async () => {
    signIn(['curriculum.view']);
    mocked.fetchFrameworkLibrary.mockResolvedValue({ ...library, can_manage: false });
    renderAt('/frameworks');

    await screen.findByRole('list', { name: 'Frameworks' });

    expect(screen.queryByRole('link', { name: 'Import framework pack' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Delete / })).not.toBeInTheDocument();
    expect(screen.queryByText('A framework that is not here?')).not.toBeInTheDocument();
  });

  it('asks before deleting a version and then removes it from the list', async () => {
    mocked.deleteFramework.mockResolvedValue(undefined);
    renderAt('/frameworks');
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete Demo Graduate Competencies version 0.9' })
    );

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/hides the version from the library/)).toBeInTheDocument();
    expect(mocked.deleteFramework).not.toHaveBeenCalled();
    mocked.fetchFrameworkLibrary.mockResolvedValue({
      ...library,
      frameworks: library.frameworks.filter((f) => f.id !== 'f0'),
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete version' }));

    expect(await screen.findByText('Deleted Demo Graduate Competencies version 0.9.')).toBeInTheDocument();
    expect(mocked.deleteFramework).toHaveBeenCalledWith('f0');
    await waitFor(() => expect(screen.queryByText(/2 versions/)).not.toBeInTheDocument());
  });

  it('explains why a version in use cannot be deleted and keeps it', async () => {
    mocked.deleteFramework.mockRejectedValue(new ApiError(409, 'mapped'));
    renderAt('/frameworks');
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete Demo Graduate Competencies version 1.0' })
    );

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete version' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      /cannot be deleted while objectives are mapped to it/
    );
    expect(screen.getByRole('list', { name: 'Frameworks' })).toBeInTheDocument();
  });

  it('says so when no framework has been imported', async () => {
    mocked.fetchFrameworkLibrary.mockResolvedValue({ can_manage: true, frameworks: [] });
    renderAt('/frameworks');

    expect(await screen.findByText('No frameworks yet')).toBeInTheDocument();
  });

  it('shows an error with a way to retry when the library cannot be loaded', async () => {
    mocked.fetchFrameworkLibrary.mockRejectedValueOnce(new ApiError(500, 'boom'));
    renderAt('/frameworks');

    expect(await screen.findByRole('alert')).toHaveTextContent('The frameworks could not be loaded');
    mocked.fetchFrameworkLibrary.mockResolvedValue(library);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByRole('list', { name: 'Frameworks' })).toBeInTheDocument();
  });
});

describe('framework browser', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    signIn(['curriculum.view']);
    mocked.fetchFrameworkLibrary.mockResolvedValue({ ...library, can_manage: false });
    mocked.fetchFrameworkItems.mockImplementation(async (_id, params = {}) =>
      params.parentId === areaA.id
        ? page(areaA.id, [childA1, childA2])
        : page(null, [areaA, areaB])
    );
    mocked.fetchFrameworkItem.mockImplementation(async (_id, itemId) => {
      const all = [areaA, areaB, childA1, childA2];
      const found = all.find((i) => i.id === itemId)!;
      return detail(found, found === childA1 ? { path: [{ id: areaA.id, code: 'A', title: areaA.title, sibling_index: 0 }] } : {});
    });
    mocked.fetchWhereMapped.mockResolvedValue({ item_id: 'x', total: 0, limit: 200, mappings: [] });
  });

  async function openTree() {
    renderAt('/frameworks/f1');
    return screen.findByRole('tree', { name: 'Demo Graduate Competencies items' });
  }

  it('shows the top level as a tree with one row in the tab order', async () => {
    const tree = within(await openTree());

    const items = tree.getAllByRole('treeitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveAttribute('aria-level', '1');
    expect(items[0]).toHaveAttribute('aria-expanded', 'false');
    expect(items[0]).toHaveAttribute('aria-setsize', '2');
    expect(items[1]).not.toHaveAttribute('aria-expanded');
    expect(items.filter((i) => i.tabIndex === 0)).toEqual([items[0]]);
    expect(tree.getByText('3 objectives mapped')).toBeInTheDocument();
    expect(mocked.fetchFrameworkItems).toHaveBeenCalledTimes(1);
  });

  it('loads children when an item is opened with the keyboard and closes it again', async () => {
    const tree = within(await openTree());
    const first = tree.getAllByRole('treeitem')[0];
    first.focus();

    fireEvent.keyDown(first, { key: 'ArrowRight' });

    expect(await tree.findByText('Gather history')).toBeInTheDocument();
    expect(mocked.fetchFrameworkItems).toHaveBeenLastCalledWith('f1', {
      parentId: areaA.id,
      offset: 0,
      limit: 100,
    });
    expect(first).toHaveAttribute('aria-expanded', 'true');
    const child = tree.getByRole('treeitem', { name: /Gather history/ });
    expect(child).toHaveAttribute('aria-level', '2');

    fireEvent.keyDown(first, { key: 'ArrowRight' });
    await waitFor(() => expect(child).toHaveFocus());
    fireEvent.keyDown(child, { key: 'ArrowLeft' });
    await waitFor(() => expect(first).toHaveFocus());
    fireEvent.keyDown(first, { key: 'ArrowLeft' });
    await waitFor(() => expect(tree.queryByText('Gather history')).not.toBeInTheDocument());
    expect(first).toHaveAttribute('aria-expanded', 'false');
  });

  it('moves with the arrow keys, Home and End', async () => {
    const tree = within(await openTree());
    const [first, second] = tree.getAllByRole('treeitem');
    first.focus();

    fireEvent.keyDown(first, { key: 'ArrowDown' });
    expect(second).toHaveFocus();
    fireEvent.keyDown(second, { key: 'Home' });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: 'End' });
    expect(second).toHaveFocus();
    expect(second.tabIndex).toBe(0);
    expect(first.tabIndex).toBe(-1);
  });

  it('selects an item and shows its details, path and an empty where-mapped list', async () => {
    const tree = within(await openTree());
    fireEvent.click(tree.getByRole('treeitem', { name: /Communication/ }));

    expect(await screen.findByRole('heading', { level: 2, name: /Communication/ })).toBeInTheDocument();
    expect(screen.getByText('About Communication.')).toBeInTheDocument();
    expect(await screen.findByText('No objectives you can see are mapped to this item yet.')).toBeInTheDocument();
    expect(tree.getByRole('treeitem', { name: /Communication/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('shows where an item is mapped, read only, with links into the curriculum', async () => {
    mocked.fetchWhereMapped.mockResolvedValue(mappings);
    renderAt('/frameworks/f1?item=' + childA1.id);

    expect(await screen.findByText('2 links you can see')).toBeInTheDocument();
    const list = within(screen.getByRole('list', { name: 'Objectives mapped to this item' }));
    expect(list.getByText('Describe the cardiac cycle.')).toBeInTheDocument();
    expect(list.getByRole('link', { name: 'HSC201 Cardiovascular system: Cardiac cycle' })).toHaveAttribute(
      'href',
      '/curriculum/versions/v1?item=event%3Ae1'
    );
    expect(list.getByRole('link', { name: 'BSc Health Sciences (Demo) outcome' })).toHaveAttribute(
      'href',
      '/curriculum/versions/v1?item=programme'
    );
    expect(list.getByText('Accepted')).toBeInTheDocument();
    expect(list.getByText('Suggested, not reviewed')).toBeInTheDocument();
    expect(list.getByText('Coverage 4 of 5')).toBeInTheDocument();
    expect(list.getByText('Coverage not set yet')).toBeInTheDocument();
    expect(list.getByText('Wording changed: check it still fits')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /link|accept|reject/i })).not.toBeInTheDocument();
  });

  it('opens the tree down to an item named in the address', async () => {
    renderAt('/frameworks/f1?item=' + childA1.id);

    const tree = within(await screen.findByRole('tree', { name: 'Demo Graduate Competencies items' }));

    const child = await tree.findByRole('treeitem', { name: /Gather history/ });
    expect(child).toHaveAttribute('aria-selected', 'true');
    expect(tree.getByRole('treeitem', { name: /Clinical reasoning/ })).toHaveAttribute('aria-expanded', 'true');
  });

  it('loads the rest of a long list when asked', async () => {
    const first = [item('K1', 'One'), item('K2', 'Two')];
    mocked.fetchFrameworkItems.mockImplementation(async (_id, params = {}) =>
      params.offset === 2
        ? page(null, [item('K3', 'Three')], 3, 2)
        : page(null, first, 3, 0)
    );
    const tree = within(await openTree());

    fireEvent.click(tree.getByRole('treeitem', { name: /Show more items/ }));

    expect(await tree.findByText('Three')).toBeInTheDocument();
    expect(mocked.fetchFrameworkItems).toHaveBeenLastCalledWith('f1', {
      parentId: null,
      offset: 2,
      limit: 100,
    });
    expect(tree.queryByRole('treeitem', { name: /Show more items/ })).not.toBeInTheDocument();
    expect(tree.getByRole('treeitem', { name: /Three/ })).toHaveAttribute('aria-posinset', '3');
  });

  describe('search', () => {
    function type(text: string) {
      fireEvent.change(screen.getByRole('searchbox', { name: /Search this framework/ }), {
        target: { value: text },
      });
    }

    it('finds items by code or words and shows the match with its details', async () => {
      mocked.searchFramework.mockResolvedValue({
        query: 'history',
        offset: 0,
        total: 1,
        hits: [{ ...childA1, path: [{ id: areaA.id, code: 'A', title: areaA.title }] }],
      });
      await openTree();

      type('history');

      const results = within(await screen.findByRole('list', { name: 'Search results' }));
      expect(await screen.findByText('1 match')).toBeInTheDocument();
      expect(mocked.searchFramework).toHaveBeenCalledWith('f1', 'history', 0);
      expect(screen.queryByRole('tree')).not.toBeInTheDocument();
      fireEvent.click(results.getByRole('button', { name: /Gather history/ }));
      expect(await screen.findByRole('heading', { level: 2, name: /Gather history/ })).toBeInTheDocument();
      expect(results.getByRole('button', { name: /Gather history/ })).toHaveAttribute('aria-current', 'true');
    });

    it('says when nothing matches', async () => {
      mocked.searchFramework.mockResolvedValue({ query: 'zzz', offset: 0, total: 0, hits: [] });
      await openTree();

      type('zzz');

      expect(await screen.findByText(/Nothing matches "zzz"/)).toBeInTheDocument();
    });

    it('shows a found item in the tree and moves focus to it', async () => {
      mocked.searchFramework.mockResolvedValue({
        query: 'history',
        offset: 0,
        total: 1,
        hits: [{ ...childA1, path: [{ id: areaA.id, code: 'A', title: areaA.title }] }],
      });
      await openTree();
      type('history');
      fireEvent.click(await screen.findByRole('button', { name: /Gather history/ }));
      fireEvent.click(await screen.findByRole('button', { name: 'Show in tree' }));

      const row = await screen.findByRole('treeitem', { name: /Gather history/ });

      await waitFor(() => expect(row).toHaveFocus());
      expect(screen.queryByRole('list', { name: 'Search results' })).not.toBeInTheDocument();
      expect(screen.getByRole('searchbox', { name: /Search this framework/ })).toHaveValue('');
    });

    it('clears the search with a button', async () => {
      mocked.searchFramework.mockResolvedValue({ query: 'a', offset: 0, total: 0, hits: [] });
      await openTree();
      type('a');
      await screen.findByText(/Nothing matches/);

      fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));

      expect(await screen.findByRole('tree')).toBeInTheDocument();
    });
  });

  it('says so when the framework has no items', async () => {
    mocked.fetchFrameworkItems.mockResolvedValue(page(null, []));
    renderAt('/frameworks/f1');

    expect(await screen.findByText('This version has no items.')).toBeInTheDocument();
  });

  it('explains when the framework is not in the library', async () => {
    renderAt('/frameworks/missing');

    expect(await screen.findByText('This framework could not be opened')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'All frameworks' })).toHaveAttribute('href', '/frameworks');
  });

  it('keeps the page usable and says so when items fail to load', async () => {
    mocked.fetchFrameworkItems.mockRejectedValue(new ApiError(500, 'boom'));
    renderAt('/frameworks/f1');

    expect(await screen.findByText('Some items could not be loaded. Nothing was changed.')).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: /Search this framework/ })).toBeInTheDocument();
  });
});
