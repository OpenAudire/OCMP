import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type { CurriculumImportPreview, ImportJob, ProgrammeSummary } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchReviewCount: vi.fn(),
  fetchImportJobs: vi.fn(),
  fetchPackTemplates: vi.fn(),
  previewTagImport: vi.fn(),
  applyTagImport: vi.fn(),
  previewMappingImport: vi.fn(),
  applyMappingImport: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const programmes: ProgrammeSummary[] = [
  {
    id: 'p1',
    code: 'BHS',
    name: 'BSc',
    faculty_id: 'f',
    faculty_name: 'F',
    status: 'active',
    versions: [
      { id: 'v2', academic_year: 2027, status: 'draft', published_at: null, based_on_id: null },
    ],
  },
];

function preview(sheet: string, token = 'token-123456'): CurriculumImportPreview {
  return {
    valid: true,
    would_change: true,
    problems: [],
    more_problems: 0,
    warnings: [],
    counts: { [sheet]: { create: 2, update: 0, unchanged: 1 } },
    rows: [
      { sheet, row: 2, external_id: 'k1', action: 'create', label: 'First', changes: [] },
    ],
    more_rows: 0,
    token,
  };
}

const jobs: ImportJob[] = [
  {
    id: 'j1',
    kind: 'tags',
    status: 'applied',
    created_at: '2026-11-04T09:00:00Z',
    by: 'Dr Admin',
    programme_code: null,
    academic_year: null,
    counts: { tag_lists: { create: 1, update: 0 }, tag_values: { create: 4, update: 2 } },
  },
  {
    id: 'j2',
    kind: 'mappings',
    status: 'applied',
    created_at: '2026-11-03T09:00:00Z',
    by: null,
    programme_code: 'BHS',
    academic_year: 2027,
    counts: { mappings: { create: 7 } },
  },
];

function chooseFile() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  fireEvent.change(input, {
    target: { files: [new File(['x'], 'c.xlsx', { type: 'application/octet-stream' })] },
  });
}

async function check(buttonName: string) {
  const button = await screen.findByRole('button', { name: buttonName });
  chooseFile();
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

function givenRoles(...permissions: string[]) {
  mocked.fetchMyRoles.mockResolvedValue([role('r', permissions)]);
}

describe('Excel imports of tags and mappings, and the history', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchImportJobs.mockResolvedValue([]);
    mocked.fetchPackTemplates.mockResolvedValue([]);
  });

  it('imports tags without choosing a version, then asks the history again', async () => {
    givenRoles('taglists.manage');
    mocked.previewTagImport.mockResolvedValue(preview('tag_lists'));
    mocked.applyTagImport.mockResolvedValue({
      counts: { tag_lists: { create: 2, update: 0 } },
      job_id: 'j9',
    });
    renderAt('/import');

    expect(await screen.findByRole('heading', { level: 2, name: 'Tags from Excel' })).toBeVisible();
    expect(screen.queryByLabelText('Curriculum version')).not.toBeInTheDocument();
    await check('Check the file');
    expect(await screen.findByText('What importing this file would do')).toBeInTheDocument();
    mocked.fetchImportJobs.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Import the tags' }));

    await waitFor(() => expect(mocked.applyTagImport).toHaveBeenCalledWith('token-123456'));
    expect(await screen.findByText('Imported: 2 new and 0 updated rows.')).toBeInTheDocument();
    await waitFor(() => expect(mocked.fetchImportJobs).toHaveBeenCalled());
  });

  it('offers the mappings import with a draft version and suggests the links by default', async () => {
    givenRoles('mapping.edit');
    mocked.previewMappingImport.mockResolvedValue(preview('mappings'));
    mocked.applyMappingImport.mockResolvedValue({
      counts: { mappings: { create: 2, update: 0 } },
      job_id: 'j9',
    });
    renderAt('/import');

    expect(
      await screen.findByRole('link', { name: /download the excel template for mappings/i })
    ).toHaveAttribute('href', '/api/v1/curriculum-versions/v2/import/mappings/template');
    await check('Check the file');
    await screen.findByText('What importing this file would do');
    expect(screen.queryByLabelText(/already reviewed elsewhere/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Import the mappings' }));

    await waitFor(() =>
      expect(mocked.applyMappingImport).toHaveBeenCalledWith('v2', 'token-123456', false)
    );
  });

  it('lets someone who may review record the links as already decided', async () => {
    givenRoles('mapping.edit', 'mapping.review');
    mocked.previewMappingImport.mockResolvedValue(preview('mappings'));
    mocked.applyMappingImport.mockResolvedValue({
      counts: { mappings: { create: 2, update: 0 } },
      job_id: 'j9',
    });
    renderAt('/import');

    await check('Check the file');
    fireEvent.click(await screen.findByLabelText(/already reviewed elsewhere/i));
    fireEvent.click(screen.getByRole('button', { name: 'Import the mappings' }));

    await waitFor(() =>
      expect(mocked.applyMappingImport).toHaveBeenCalledWith('v2', 'token-123456', true)
    );
  });

  it('lists the applied imports with their counts, and says so when there are none', async () => {
    givenRoles('taglists.manage');
    mocked.fetchImportJobs.mockResolvedValue(jobs);
    renderAt('/import');

    expect(await screen.findByRole('heading', { level: 2, name: 'Import history' })).toBeVisible();
    expect(await screen.findByText('Dr Admin')).toBeInTheDocument();
    expect(screen.getByText('5 new, 2 updated').closest('tr')).toHaveTextContent('Tags');
    expect(screen.getByText('BHS 2027').closest('tr')).toHaveTextContent('Mappings');
    expect(screen.getByText('7 new, 0 updated')).toBeInTheDocument();
  });

  it('says so when no import has been applied yet', async () => {
    givenRoles('taglists.manage');
    renderAt('/import');

    expect(await screen.findByText('No import has been applied yet.')).toBeInTheDocument();
  });
});
