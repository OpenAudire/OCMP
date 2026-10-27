import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type {
  FrameworkItemDetail,
  FrameworkLibrary,
  MappingWorkspace,
  WhereMapped,
  WorkspaceLink,
  WorkspaceObjective,
} from '../api/types';
import { programmes } from '../curriculum/testData';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchMappingWorkspace: vi.fn(),
  fetchReviewCount: vi.fn(),
  fetchFrameworkLibrary: vi.fn(),
  fetchFrameworkItems: vi.fn(),
  searchFramework: vi.fn(),
  fetchFrameworkItem: vi.fn(),
  fetchWhereMapped: vi.fn(),
  addMappingLink: vi.fn(),
  updateMappingLink: vi.fn(),
  removeMappingLink: vi.fn(),
  confirmMappingRecheck: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const library: FrameworkLibrary = {
  can_manage: false,
  frameworks: [
    {
      id: 'f1',
      key: 'demo',
      name: 'Demo Graduate Competencies',
      version_label: '1.0',
      publisher: 'Demo University',
      licence_note: '',
      description: '',
      url: null,
      profile: 'core',
      status: 'active',
      item_count: 2,
      top_level_count: 2,
      level_count: 1,
    },
  ],
};

const itemA = { id: 'ia', code: 'A', title: 'Clinical reasoning', depth: 0, child_count: 0, mapped_count: 0 };
const itemB = { id: 'ib', code: 'B', title: 'Communication', depth: 0, child_count: 0, mapped_count: 0 };

function link(overrides: Partial<WorkspaceLink> = {}): WorkspaceLink {
  return {
    id: 'l1',
    framework_id: 'f1',
    framework_name: 'Demo Graduate Competencies',
    framework_version_label: '1.0',
    item_id: 'ia',
    item_code: 'A',
    item_title: 'Clinical reasoning',
    coverage: 4,
    depth_match: 'matches',
    rationale: 'Direct match.',
    source: 'human',
    status: 'accepted',
    accept_method: 'individual',
    needs_recheck: false,
    needs_discussion: false,
    ...overrides,
  };
}

function objective(overrides: Partial<WorkspaceObjective> = {}): WorkspaceObjective {
  return {
    id: 'o1',
    text: 'Describe the heart.',
    level: 'module',
    phase_id: null,
    phase_name: null,
    module_id: 'm1',
    module_code: 'HSC101',
    module_name: 'Anatomy',
    learning_event_id: null,
    learning_event_title: null,
    can_edit: true,
    can_review: true,
    links: [],
    ...overrides,
  };
}

function workspace(overrides: Partial<MappingWorkspace> = {}): MappingWorkspace {
  return {
    version_id: 'v2027',
    academic_year: 2027,
    version_status: 'draft',
    programme_id: 'p1',
    programme_name: 'BSc Health Sciences (Demo)',
    editable: true,
    four_eyes: false,
    objectives: [
      objective({ links: [link()] }),
      objective({
        id: 'o2',
        text: 'Explain gas exchange.',
        module_id: 'm2',
        module_code: 'HSC102',
        module_name: 'Physiology',
      }),
      objective({
        id: 'o3',
        text: 'Reason clinically.',
        level: 'programme',
        module_id: null,
        module_code: null,
        module_name: null,
        can_edit: false,
        can_review: false,
      }),
    ],
    ...overrides,
  };
}

const noMappings: WhereMapped = { item_id: 'ia', total: 0, limit: 200, mappings: [] };

function itemDetail(source: typeof itemA): FrameworkItemDetail {
  return {
    id: source.id,
    framework_id: 'f1',
    code: source.code,
    title: source.title,
    description: `About ${source.title}.`,
    depth: 0,
    child_count: 0,
    mapped_count: 0,
    path: [],
    sibling_index: 0,
  };
}

function signIn(permissions = ['curriculum.view', 'mapping.edit', 'mapping.review']) {
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([role('r', permissions)]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
}

const HELP_TEXT =
  'Coverage: how much of this framework item the objective teaches, from 0 (none) to 5 (more than 80%). Depth: whether the objective asks students to work at the level the item expects (for example, knowing versus doing). Both affect the weighted coverage report.';

describe('mapping workspace', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    signIn();
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchMappingWorkspace.mockResolvedValue(workspace());
    mocked.fetchReviewCount.mockResolvedValue({ first: 0, second: 0, recheck: 0, waiting: 0, total: 0 });
    mocked.fetchFrameworkLibrary.mockResolvedValue(library);
    mocked.fetchFrameworkItems.mockResolvedValue({
      parent_id: null,
      offset: 0,
      total: 2,
      items: [itemA, itemB],
    });
    mocked.fetchFrameworkItem.mockImplementation(async (_f, id) =>
      itemDetail(id === 'ib' ? itemB : itemA)
    );
    mocked.fetchWhereMapped.mockResolvedValue(noMappings);
  });

  it('opens the remembered version and lists its objectives with their link counts', async () => {
    renderAt('/mapping');

    const list = within(await screen.findByRole('list', { name: 'Objectives' }));
    expect(list.getAllByRole('listitem')).toHaveLength(3);
    expect(list.getByText('1 link')).toBeInTheDocument();
    expect(mocked.fetchMappingWorkspace).toHaveBeenCalledWith('v2027');
    expect(screen.getByRole('heading', { level: 1, name: 'Mapping' })).toBeInTheDocument();
  });

  it('shows the links of the selected objective with coverage in words, depth and status', async () => {
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Describe the heart/ }));

    const links = within(screen.getByRole('list', { name: 'Links of this objective' }));
    expect(links.getByText('Coverage 4 of 5: 61 to 80%')).toBeInTheDocument();
    expect(links.getByText('Depth: matches the item')).toBeInTheDocument();
    expect(links.getByText('Accepted')).toBeInTheDocument();
    expect(links.getByText('Direct match.')).toBeInTheDocument();
  });

  it('filters by module and to objectives without links', async () => {
    renderAt('/mapping/v2027');
    await screen.findByRole('list', { name: 'Objectives' });

    fireEvent.change(screen.getByLabelText('Course'), { target: { value: 'm2' } });
    expect(screen.getByText('Showing 1 of 3 objectives')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Course'), { target: { value: '' } });
    fireEvent.click(screen.getByLabelText('Only those without links'));

    const list = within(screen.getByRole('list', { name: 'Objectives' }));
    expect(list.getAllByRole('listitem')).toHaveLength(2);
    expect(list.queryByText('Describe the heart.')).not.toBeInTheDocument();
  });

  it('gives the help text word for word, with every level and depth defined', async () => {
    renderAt('/mapping/v2027');
    await screen.findByRole('list', { name: 'Objectives' });

    fireEvent.click(screen.getByRole('button', { name: 'Help with coverage and depth' }));

    const help = screen.getByRole('region', { name: 'Coverage and depth' });
    expect(within(help).getByText(HELP_TEXT)).toBeInTheDocument();
    const levels = within(within(help).getByLabelText('Coverage levels'));
    expect(levels.getByText('None (0%)')).toBeInTheDocument();
    expect(levels.getByText('1 to 20%')).toBeInTheDocument();
    expect(levels.getByText('21 to 40%')).toBeInTheDocument();
    expect(levels.getByText('41 to 60%')).toBeInTheDocument();
    expect(levels.getByText('61 to 80%')).toBeInTheDocument();
    expect(levels.getByText('81 to 100%')).toBeInTheDocument();
    const depths = within(within(help).getByLabelText('Depth choices'));
    expect(depths.getByText('Not applicable')).toBeInTheDocument();
    expect(depths.getByText(/asks for less than the item expects/)).toBeInTheDocument();
    expect(depths.getByText('The objective asks for the same level as the item.')).toBeInTheDocument();
    expect(depths.getByText('The objective goes beyond what the item expects.')).toBeInTheDocument();
  });

  it('links the selected objective to an item with coverage and depth', async () => {
    mocked.addMappingLink.mockResolvedValue(
      link({ id: 'l9', item_id: 'ib', item_code: 'B', item_title: 'Communication', coverage: 5, depth_match: 'above' })
    );
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Explain gas exchange/ }));
    fireEvent.click(await screen.findByText('Communication'));
    fireEvent.click(await screen.findByRole('button', { name: 'Link to the selected objective' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add link' }));
    expect(await within(dialog).findByText('Choose a coverage from 0 to 5.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText('5: 81 to 100%'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add link' }));
    expect(await within(dialog).findByText('Choose a depth.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText('Above'));
    expect(within(dialog).getByText('The objective goes beyond what the item expects.')).toBeInTheDocument();
    expect(
      within(dialog).getByText('You may review mappings here, so this link is accepted when you save.')
    ).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: ' Fits well ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add link' }));

    await waitFor(() =>
      expect(mocked.addMappingLink).toHaveBeenCalledWith('o2', 'ib', {
        coverage: 5,
        depth_match: 'above',
        rationale: 'Fits well',
      })
    );
    expect(await screen.findByText(/Linked to B Communication\. The link is accepted\./)).toBeInTheDocument();
    await waitFor(() => expect(mocked.fetchMappingWorkspace).toHaveBeenCalledTimes(2));
  });

  it('says a second review is needed in four-eyes mode and a suggestion for non-reviewers', async () => {
    mocked.fetchMappingWorkspace.mockResolvedValue(workspace({ four_eyes: true }));
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Explain gas exchange/ }));
    fireEvent.click(await screen.findByText('Communication'));
    fireEvent.click(await screen.findByRole('button', { name: 'Link to the selected objective' }));

    expect(
      within(await screen.findByRole('dialog')).getByText(
        'A second reviewer must agree before this link counts as accepted.'
      )
    ).toBeInTheDocument();
  });

  it('offers no linking for an objective the user may only read, or in a published version', async () => {
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Reason clinically/ }));
    expect(screen.getByText('You may read the links of this objective but not change them.')).toBeInTheDocument();
    fireEvent.click(await screen.findByText('Communication'));
    expect(screen.queryByRole('button', { name: 'Link to the selected objective' })).not.toBeInTheDocument();
  });

  it('is read only for a published version', async () => {
    mocked.fetchMappingWorkspace.mockResolvedValue(
      workspace({ editable: false, version_status: 'published' })
    );
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Describe the heart/ }));

    expect(screen.getByText(/This version is published, so its links can be read but not changed/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit the link/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Remove the link/ })).not.toBeInTheDocument();
  });

  it('changes a link, starting from its current values', async () => {
    mocked.updateMappingLink.mockResolvedValue(link({ coverage: 2, depth_match: 'below' }));
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Describe the heart/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Edit the link to A Clinical reasoning' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('4: 61 to 80%')).toBeChecked();
    expect(within(dialog).getByLabelText('Matches')).toBeChecked();
    fireEvent.click(within(dialog).getByLabelText('2: 21 to 40%'));
    fireEvent.click(within(dialog).getByLabelText('Below'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save link' }));

    await waitFor(() =>
      expect(mocked.updateMappingLink).toHaveBeenCalledWith('l1', {
        coverage: 2,
        depth_match: 'below',
        rationale: 'Direct match.',
      })
    );
    expect(await screen.findByText(/Saved the link to A Clinical reasoning/)).toBeInTheDocument();
  });

  it('asks before removing a link', async () => {
    mocked.removeMappingLink.mockResolvedValue({ deleted: true });
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Describe the heart/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove the link to A Clinical reasoning' }));

    const dialog = await screen.findByRole('dialog');
    expect(mocked.removeMappingLink).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove link' }));

    expect(await screen.findByText('Removed the link to A Clinical reasoning.')).toBeInTheDocument();
    expect(mocked.removeMappingLink).toHaveBeenCalledWith('l1');
  });

  it('confirms that a changed-wording link still fits, only clearing the flag', async () => {
    mocked.fetchMappingWorkspace.mockResolvedValue(
      workspace({ objectives: [objective({ links: [link({ needs_recheck: true })] })] })
    );
    mocked.confirmMappingRecheck.mockResolvedValue(link());
    renderAt('/mapping/v2027');
    fireEvent.click(await screen.findByRole('button', { name: /Describe the heart/ }));

    expect(screen.getAllByText('Wording changed: check it still fits').length).toBeGreaterThan(0);
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Confirm that the link to A Clinical reasoning still fits the changed wording',
      })
    );

    expect(await screen.findByText(/Confirmed that the link to A Clinical reasoning still fits/)).toBeInTheDocument();
    expect(mocked.confirmMappingRecheck).toHaveBeenCalledWith('l1');
  });
});
