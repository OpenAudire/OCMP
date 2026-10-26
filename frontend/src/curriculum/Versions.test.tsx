import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { CopyForwardPreview, VersionDiff, VersionStructure } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { programmes, structure } from './testData';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchProgramme: vi.fn(),
  fetchVersionStructure: vi.fn(),
  fetchProgrammeOutcomes: vi.fn(),
  fetchModule: vi.fn(),
  fetchLearningEvent: vi.fn(),
  changeVersionStatus: vi.fn(),
  deleteVersion: vi.fn(),
  fetchCopyForwardPreview: vi.fn(),
  copyForward: vi.fn(),
  fetchVersionDiff: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

// The first render of the whole app inside a busy parallel run can take several seconds.
vi.setConfig({ testTimeout: 20_000 });

const director: VersionStructure = {
  ...structure,
  can_edit: true,
  can_change_status: true,
  can_copy_forward: true,
};

const published: VersionStructure = {
  ...director,
  version: programmes[0].versions[1],
  can_edit: false,
};

const preview: CopyForwardPreview = {
  academic_year: 2028,
  taken_years: [2026, 2027],
  phases: 2,
  modules: 3,
  learning_events: 7,
  objectives: 40,
  mappings: 5,
  can_copy_roles: true,
  role_assignments: [
    {
      id: 'ra1',
      user_name: 'Lindiwe Dube',
      role_name: 'Module coordinator',
      scope_type: 'module',
      item: 'HSC201 Cardiovascular system',
      expires_at: null,
      skip_reason: null,
    },
    {
      id: 'ra2',
      user_name: 'Pieter van Wyk',
      role_name: 'Lecturer / facilitator',
      scope_type: 'module',
      item: 'HSC201 Cardiovascular system',
      expires_at: null,
      skip_reason: 'account_inactive',
    },
  ],
};

const diff: VersionDiff = {
  programme: { id: 'p1', code: 'BHS', name: 'BSc Health Sciences (Demo)' },
  base: programmes[0].versions[1],
  version: programmes[0].versions[0],
  summary: {
    phase: { added: 0, removed: 0, changed: 0 },
    module: { added: 0, removed: 0, changed: 1 },
    learning_event: { added: 1, removed: 0, changed: 0 },
    objective: { added: 0, removed: 0, changed: 0 },
  },
  changes: [
    {
      kind: 'module',
      change: 'changed',
      id: 'm2',
      base_id: 'm2-old',
      label: 'HSC201 Cardiovascular system',
      context: null,
      level: null,
      fields: [{ field: 'credits', before: '12', after: '15' }],
    },
    {
      kind: 'learning_event',
      change: 'added',
      id: 'e9',
      base_id: null,
      label: 'The nervous system',
      context: 'HSC201 Cardiovascular system',
      level: null,
      fields: [],
    },
  ],
};

function setup(view: VersionStructure, permissions: string[]) {
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([role('programme_director', permissions)]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
  mocked.fetchProgrammes.mockResolvedValue(programmes);
  mocked.fetchProgramme.mockRejectedValue(new ApiError(500, 'not needed'));
  mocked.fetchProgrammeOutcomes.mockResolvedValue([]);
  mocked.fetchModule.mockRejectedValue(new ApiError(500, 'not needed'));
  mocked.fetchLearningEvent.mockRejectedValue(new ApiError(500, 'not needed'));
  mocked.fetchVersionStructure.mockResolvedValue(view);
}

function bar() {
  return screen.findByRole('group', { name: 'Version actions' });
}

describe('curriculum versions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
  });

  it('publishes a draft after confirming', async () => {
    setup(director, ['curriculum.view', 'curriculum.publish']);
    mocked.changeVersionStatus.mockResolvedValue(programmes[0].versions[0]);

    renderAt('/curriculum/versions/v2027');
    const actions = await bar();
    fireEvent.click(within(actions).getByRole('button', { name: 'Publish version' }));
    const dialog = await screen.findByRole('dialog', { name: 'Publish the 2027 draft?' });
    expect(dialog).toHaveTextContent('can no longer be changed');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish version' }));

    await waitFor(() => expect(mocked.changeVersionStatus).toHaveBeenCalledWith('v2027', 'published'));
    expect(await screen.findByText('2027 published.')).toBeInTheDocument();
  });

  it('a published version offers return to draft and archive, and no editing', async () => {
    setup(published, ['curriculum.view', 'curriculum.publish']);

    renderAt('/curriculum/versions/v2026');
    const actions = await bar();

    expect(within(actions).getByRole('button', { name: 'Return to draft' })).toBeInTheDocument();
    expect(within(actions).getByRole('button', { name: 'Archive' })).toBeInTheDocument();
    expect(within(actions).queryByRole('button', { name: 'Delete draft' })).toBeNull();
    expect(screen.getByText(/it is read-only and visible to students/)).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Changes' })).toBeNull();
  });

  it('shows a failed status change', async () => {
    setup(director, ['curriculum.view', 'curriculum.publish']);
    mocked.changeVersionStatus.mockRejectedValue(new ApiError(409, 'no modules'));

    renderAt('/curriculum/versions/v2027');
    fireEvent.click(within(await bar()).getByRole('button', { name: 'Publish version' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish version' }));

    // The noun follows the institution's terminology.
    await waitFor(() => expect(dialog.textContent).toMatch(/needs at least one \w+ before/));
  });

  it('offers no version actions to people who cannot use them', async () => {
    setup({ ...structure, can_edit: false }, ['curriculum.view']);

    renderAt('/curriculum/versions/v2027');
    const actions = await bar();

    expect(within(actions).queryByRole('button')).toBeNull();
    expect(within(actions).getByRole('link', { name: 'Compare versions' })).toBeInTheDocument();
  });

  it('copies a version forward with the ticked role assignments', async () => {
    setup(published, ['curriculum.view', 'curriculum.edit']);
    mocked.fetchCopyForwardPreview.mockResolvedValue(preview);
    mocked.copyForward.mockResolvedValue({ ...programmes[0].versions[0], id: 'v2028' });

    renderAt('/curriculum/versions/v2026');
    fireEvent.click(within(await bar()).getByRole('button', { name: 'Copy forward' }));
    const dialog = await screen.findByRole('dialog', { name: 'Copy the 2026 published forward' });

    const year = await within(dialog).findByLabelText(/Academic year of the new version/);
    expect(year).toHaveValue('2028');
    expect(within(dialog).getByText('7')).toBeInTheDocument();
    const lindiwe = within(dialog).getByRole('checkbox', { name: /Lindiwe Dube/ });
    expect(lindiwe).toBeChecked();
    expect(within(dialog).queryByRole('checkbox', { name: /Pieter/ })).toBeNull();
    expect(within(dialog).getByText(/Pieter van Wyk.*the account is deactivated/)).toBeVisible();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Copy forward' }));

    await waitFor(() => expect(mocked.copyForward).toHaveBeenCalledWith('v2026', 2028, ['ra1']));
  });

  it('lets people untick roles and refuses a year that is taken', async () => {
    setup(published, ['curriculum.view', 'curriculum.edit']);
    mocked.fetchCopyForwardPreview.mockResolvedValue(preview);

    renderAt('/curriculum/versions/v2026');
    fireEvent.click(within(await bar()).getByRole('button', { name: 'Copy forward' }));
    const dialog = await screen.findByRole('dialog');
    const year = await within(dialog).findByLabelText(/Academic year of the new version/);
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /Lindiwe Dube/ }));
    fireEvent.change(year, { target: { value: '2027' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Copy forward' }));

    expect(await within(dialog).findByText('This year already has a version. Choose another year.'))
      .toBeInTheDocument();
    expect(mocked.copyForward).not.toHaveBeenCalled();
  });

  it('explains when role assignments cannot be copied', async () => {
    setup(published, ['curriculum.view', 'curriculum.edit']);
    mocked.fetchCopyForwardPreview.mockResolvedValue({
      ...preview,
      can_copy_roles: false,
      role_assignments: [],
    });

    renderAt('/curriculum/versions/v2026');
    fireEvent.click(within(await bar()).getByRole('button', { name: 'Copy forward' }));
    const dialog = await screen.findByRole('dialog');

    expect(await within(dialog).findByText(/cannot assign roles/)).toBeInTheDocument();
  });

  it('deletes a draft and goes to the version it was copied from', async () => {
    setup(director, ['curriculum.view', 'curriculum.edit']);
    mocked.deleteVersion.mockResolvedValue();

    renderAt('/curriculum/versions/v2027');
    fireEvent.click(within(await bar()).getByRole('button', { name: 'Delete draft' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete the 2027 draft?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete draft' }));

    await waitFor(() => expect(mocked.deleteVersion).toHaveBeenCalledWith('v2027'));
  });
});

describe('comparing versions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    setup(director, ['curriculum.view']);
  });

  it('compares with the version it was copied from and lists the changes', async () => {
    mocked.fetchVersionDiff.mockResolvedValue(diff);

    renderAt('/curriculum/versions/v2027/compare');

    expect(await screen.findByRole('heading', { level: 1, name: 'Compare versions' })).toBeVisible();
    expect(await screen.findByText('The nervous system')).toBeInTheDocument();
    expect(mocked.fetchVersionDiff).toHaveBeenCalledWith('v2027', 'v2026');
    const modules = screen.getAllByText('HSC201 Cardiovascular system')[0].closest('li')!;
    expect(within(modules).getByText('Changed')).toBeInTheDocument();
    expect(within(modules).getByText('Credits')).toBeInTheDocument();
    expect(modules).toHaveTextContent(/Before\s*12/);
    expect(modules).toHaveTextContent(/After\s*15/);
    expect(screen.getByText('1 added, 0 removed, 0 changed', { selector: 'dd' })).toBeInTheDocument();
  });

  it('says when nothing differs', async () => {
    mocked.fetchVersionDiff.mockResolvedValue({ ...diff, changes: [] });

    renderAt('/curriculum/versions/v2027/compare?base=v2026');

    expect(await screen.findByText('No differences')).toBeInTheDocument();
  });

  it('shows a failed comparison with a retry', async () => {
    mocked.fetchVersionDiff.mockRejectedValue(new ApiError(500, 'boom'));

    renderAt('/curriculum/versions/v2027/compare');

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't compare the versions");
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
