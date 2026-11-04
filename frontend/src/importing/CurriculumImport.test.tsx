import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { CurriculumImportPreview, ProgrammeSummary } from '../api/types';
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
  previewCurriculumImport: vi.fn(),
  applyCurriculumImport: vi.fn(),
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
      {
        id: 'v1',
        academic_year: 2026,
        status: 'published',
        published_at: '2026-01-01T00:00:00Z',
        based_on_id: null,
      },
    ],
  },
];

const counts = {
  phases: { create: 1, update: 0, unchanged: 0 },
  modules: { create: 0, update: 1, unchanged: 1 },
};

const valid: CurriculumImportPreview = {
  valid: true,
  would_change: true,
  problems: [],
  more_problems: 0,
  warnings: ['Modules: the column "Foo" is not used.'],
  counts,
  rows: [
    { sheet: 'phases', row: 2, external_id: 'P1', action: 'create', label: 'Year 1', changes: [] },
    {
      sheet: 'modules',
      row: 2,
      external_id: 'M1',
      action: 'update',
      label: 'Renamed',
      changes: ['Name'],
    },
  ],
  more_rows: 0,
  token: 'token-123456',
};

const invalid: CurriculumImportPreview = {
  ...valid,
  valid: false,
  would_change: false,
  token: null,
  problems: [
    { sheet: 'Sessions', row: 3, column: 'Contact minutes', message: 'Contact minutes must be a whole number.' },
    { sheet: null, row: null, column: null, message: 'The file is empty.' },
  ],
  rows: [],
  warnings: [],
};

function chooseFile() {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  fireEvent.change(input, {
    target: { files: [new File(['x'], 'c.xlsx', { type: 'application/octet-stream' })] },
  });
}

async function check() {
  const button = await screen.findByRole('button', { name: 'Check the file' });
  chooseFile();
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

describe('curriculum import from Excel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([
      role('programme_director', ['curriculum.edit', 'objectives.edit']),
    ]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
  });

  it('offers only draft versions and links the template of the chosen one', async () => {
    renderAt('/import');

    const link = await screen.findByRole('link', { name: /download the excel template/i });
    expect(link).toHaveAttribute('href', '/api/v1/curriculum-versions/v2/import/template');
    const select = screen.getByLabelText('Curriculum version') as HTMLSelectElement;
    expect(Array.from(select.options)).toHaveLength(1);
  });

  it('keeps the check button off until a file is chosen', async () => {
    renderAt('/import');

    const button = await screen.findByRole('button', { name: 'Check the file' });
    expect(button).toBeDisabled();
    chooseFile();
    await waitFor(() => expect(button).toBeEnabled());
  });

  it('lists every problem with its sheet, row and column and offers no import', async () => {
    mocked.previewCurriculumImport.mockResolvedValue(invalid);
    renderAt('/import');

    await check();

    expect(await screen.findByText('The file cannot be imported yet')).toBeInTheDocument();
    expect(screen.getByText('Contact minutes must be a whole number.')).toBeInTheDocument();
    expect(screen.getByText('The file is empty.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Import into the curriculum' })).not.toBeInTheDocument();
    expect(mocked.previewCurriculumImport).toHaveBeenCalledWith('v2', expect.any(File));
  });

  it('shows what would happen, with the notes, and imports only after confirming', async () => {
    mocked.previewCurriculumImport.mockResolvedValue(valid);
    mocked.applyCurriculumImport.mockResolvedValue({ counts, job_id: 'j1' });
    renderAt('/import');

    await check();

    expect(await screen.findByText('What importing this file would do')).toBeInTheDocument();
    expect(screen.getByText('Year 1')).toBeInTheDocument();
    expect(screen.getByText(/Updated \(Name\)/)).toBeInTheDocument();
    expect(screen.getByText('Modules: the column "Foo" is not used.')).toBeInTheDocument();
    expect(mocked.applyCurriculumImport).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Import into the curriculum' }));

    await waitFor(() =>
      expect(mocked.applyCurriculumImport).toHaveBeenCalledWith('v2', 'token-123456')
    );
    expect(await screen.findByText('Imported: 1 new and 1 updated rows.')).toBeInTheDocument();
  });

  it('says so when there is nothing to change and does not offer the import', async () => {
    mocked.previewCurriculumImport.mockResolvedValue({ ...valid, would_change: false });
    renderAt('/import');

    await check();

    expect(await screen.findByText(/there is nothing to import/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import into the curriculum' })).toBeDisabled();
  });

  it('explains an expired check', async () => {
    mocked.previewCurriculumImport.mockResolvedValue(valid);
    mocked.applyCurriculumImport.mockRejectedValue(new ApiError(422, 'expired'));
    renderAt('/import');
    await check();

    fireEvent.click(await screen.findByRole('button', { name: 'Import into the curriculum' }));

    expect(await screen.findByText(/check has expired/i)).toBeInTheDocument();
  });

  it('is not shown to someone who cannot edit the curriculum or manage frameworks', async () => {
    mocked.fetchMyRoles.mockResolvedValue([role('student', ['curriculum.view_published'])]);
    renderAt('/import');

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Check the file' })).not.toBeInTheDocument()
    );
  });
});
