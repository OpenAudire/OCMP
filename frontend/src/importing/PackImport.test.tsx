import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { PackImportResult, PackPreview, PackTemplate } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  previewFrameworkPack: vi.fn(),
  importFrameworkPack: vi.fn(),
  fetchPackTemplates: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const templates: PackTemplate[] = [
  {
    name: 'nqf-level-descriptors',
    title: 'NQF level descriptors (template)',
    description: '',
    items: 10,
  },
  { name: 'mesh-subset', title: 'MeSH subset (template)', description: '', items: 6 },
];

const validPreview: PackPreview = {
  valid: true,
  errors: [],
  warnings: ['Other versions of "demo" are already imported: 1 (active).'],
  format_version: 2,
  metadata: {
    key: 'demo',
    name: 'Demo framework',
    version: '2',
    publisher: 'Tests',
    licence: 'CC0',
    profile: 'core',
    description: '',
    url: null,
    template: false,
  },
  counts: {
    items: 3,
    levels: 2,
    root_items: 2,
    cross_references: 2,
    external_references: 1,
    crosswalks: 1,
    crosswalk_entries: 4,
    taxonomy_scales: 0,
    tag_lists: 1,
    tag_values: 5,
  },
  sample: [
    { code: 'A', title: 'First', depth: 0 },
    { code: 'A.1', title: 'Child', depth: 1 },
    { code: 'B', title: 'Second', depth: 0 },
  ],
  sample_truncated: false,
  token: 'token-123456',
  expires_in: 1800,
};

const invalidPreview: PackPreview = {
  ...validPreview,
  valid: false,
  errors: [
    { path: 'items[1].parent_code', message: 'Item B has an unknown parent Z.' },
    { path: '', message: 'The file is not valid JSON.' },
  ],
  warnings: [],
  token: null,
  expires_in: null,
};

const imported: PackImportResult = {
  framework_id: 'f1',
  key: 'demo',
  name: 'Demo framework',
  version: '2',
  status: 'active',
  items: 3,
  cross_references: 2,
  external_references: 1,
  crosswalks: 1,
  crosswalk_entries: 4,
  scales_created: 0,
  tag_lists_created: 1,
  tag_values_added: 5,
  superseded_versions: 1,
};

function chooseFile(name = 'pack.json') {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  const file = new File(['{}'], name, { type: 'application/json' });
  fireEvent.change(input, { target: { files: [file] } });
}

async function checkFile() {
  await screen.findByRole('button', { name: 'Check file' });
  chooseFile();
  const button = screen.getByRole('button', { name: 'Check file' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

describe('framework pack import', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('curriculum_office', ['frameworks.manage'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchPackTemplates.mockResolvedValue(templates);
  });

  it('lists the blank templates with download links', async () => {
    renderAt('/import');

    const link = await screen.findByRole('link', { name: /download nqf level descriptors/i });
    expect(link).toHaveAttribute('href', '/api/v1/framework-packs/templates/nqf-level-descriptors');
    expect(screen.getByText(/placeholders, not official text/i)).toBeInTheDocument();
  });

  it('keeps the check button off until a file is chosen', async () => {
    renderAt('/import');

    const check = await screen.findByRole('button', { name: 'Check file' });
    expect(check).toBeDisabled();
    chooseFile();
    await waitFor(() => expect(check).toBeEnabled());
  });

  it('lists every problem with its place and imports nothing', async () => {
    mocked.previewFrameworkPack.mockResolvedValue(invalidPreview);
    renderAt('/import');

    await checkFile();

    expect(await screen.findByText('This file cannot be imported yet')).toBeInTheDocument();
    expect(
      screen.getByText('2 problems found. Fix them in the file and check them again.')
    ).toBeInTheDocument();
    expect(screen.getByText('items[1].parent_code')).toBeInTheDocument();
    expect(screen.getByText('Whole file')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Import framework' })).not.toBeInTheDocument();
    expect(mocked.importFrameworkPack).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Choose another file' }));
    expect(await screen.findByRole('button', { name: 'Check file' })).toBeInTheDocument();
  });

  it('shows the preview, then imports and says what happened', async () => {
    mocked.previewFrameworkPack.mockResolvedValue(validPreview);
    mocked.importFrameworkPack.mockResolvedValue(imported);
    renderAt('/import');

    await checkFile();

    expect(await screen.findByText('Check the pack before importing')).toBeInTheDocument();
    expect(screen.getByText('3 items in 2 levels')).toBeInTheDocument();
    expect(
      screen.getByText('2 cross-references, 1 of them to other frameworks')
    ).toBeInTheDocument();
    expect(
      screen.getByText('1 crosswalk from an earlier version with 4 entries')
    ).toBeInTheDocument();
    expect(screen.getByText('1 tag list with 5 tags')).toBeInTheDocument();
    expect(screen.getByText('CC0')).toBeInTheDocument();
    expect(screen.getByText(/Other versions of "demo"/)).toBeInTheDocument();
    const items = within(screen.getByRole('region', { name: 'Items in the pack, in tree order' }));
    expect(items.getByText('Child')).toBeInTheDocument();
    expect(mocked.importFrameworkPack).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('checkbox', { name: /make this the active version/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Import framework' }));

    expect(await screen.findByText(/was imported as the active version/)).toBeInTheDocument();
    expect(mocked.importFrameworkPack).toHaveBeenCalledWith('token-123456', true);
    expect(screen.getByText('1 earlier version superseded')).toBeInTheDocument();
    expect(screen.getByText('1 tag lists created and 5 tags added')).toBeInTheDocument();
  });

  it('imports as a draft unless asked to activate', async () => {
    mocked.previewFrameworkPack.mockResolvedValue(validPreview);
    mocked.importFrameworkPack.mockResolvedValue({ ...imported, status: 'draft' });
    renderAt('/import');
    await checkFile();

    fireEvent.click(await screen.findByRole('button', { name: 'Import framework' }));

    await screen.findByText(/was imported as a draft/);
    expect(mocked.importFrameworkPack).toHaveBeenCalledWith('token-123456', false);
  });

  it.each([
    [413, 'The file is larger than this installation accepts.'],
    [429, 'Too many checks in a short time.'],
    [403, 'You do not have permission to import frameworks.'],
    [500, 'Something went wrong and nothing was imported.'],
  ])('explains a failed check (%i)', async (status, text) => {
    mocked.previewFrameworkPack.mockRejectedValue(new ApiError(status, 'x'));
    renderAt('/import');

    await checkFile();

    expect(await screen.findByRole('alert')).toHaveTextContent(text);
  });

  it('explains an expired preview and keeps the preview on screen', async () => {
    mocked.previewFrameworkPack.mockResolvedValue(validPreview);
    mocked.importFrameworkPack.mockRejectedValue(new ApiError(404, 'gone'));
    renderAt('/import');
    await checkFile();

    fireEvent.click(await screen.findByRole('button', { name: 'Import framework' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('preview has expired');
    expect(screen.getByRole('button', { name: 'Import framework' })).toBeInTheDocument();
  });

  it('shows the placeholder to people who cannot manage frameworks', async () => {
    mocked.fetchMyRoles.mockResolvedValue([role('programme_director', ['curriculum.edit'])]);
    renderAt('/import');

    expect(await screen.findByText('This page is being built.')).toBeInTheDocument();
    expect(screen.queryByText('Framework pack')).not.toBeInTheDocument();
  });
});
