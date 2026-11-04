import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type { ProgrammeSummary } from '../api/types';
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
  fetchFrameworkLibrary: vi.fn(),
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

describe('exports of a curriculum version', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('curriculum_office', ['reports.view', 'curriculum.view'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchImportJobs.mockResolvedValue([]);
    mocked.fetchFrameworkLibrary.mockResolvedValue({
      frameworks: [
        { id: 'fw1', key: 'c', name: 'Competencies', version_label: '1.0', status: 'active' } as never,
        { id: 'fw2', key: 'd', name: 'Draft one', version_label: '0.1', status: 'draft' } as never,
      ],
      can_manage: false,
    });
  });

  it('links the three downloads of the chosen version, with the framework for the matrix', async () => {
    renderAt('/import');

    const workbook = await screen.findByRole('link', { name: /download the whole version as excel/i });
    expect(workbook).toHaveAttribute('href', '/api/v1/curriculum-versions/v2/export/workbook');
    expect(await screen.findByRole('link', { name: /objectives by framework items/i })).toHaveAttribute(
      'href',
      '/api/v1/curriculum-versions/v2/export/matrix?framework_id=fw1'
    );
    expect(screen.getByRole('link', { name: /download the version as json/i })).toHaveAttribute(
      'href',
      '/api/v1/curriculum-versions/v2/export/json'
    );
  });

  it('follows the version that is chosen and leaves draft frameworks out', async () => {
    renderAt('/import');
    await screen.findByRole('link', { name: /download the whole version as excel/i });

    const select = screen.getByLabelText('Curriculum version') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'v1' } });

    await waitFor(() =>
      expect(screen.getByRole('link', { name: /download the version as json/i })).toHaveAttribute(
        'href',
        '/api/v1/curriculum-versions/v1/export/json'
      )
    );
    const frameworks = screen.getByLabelText(/^Framework/) as HTMLSelectElement;
    expect(Array.from(frameworks.options).map((o) => o.text)).toEqual(['Competencies (1.0)']);
  });

  it('is not shown to someone who cannot see reports', async () => {
    mocked.fetchMyRoles.mockResolvedValue([
      role('external_reviewer', ['reports.view', 'curriculum.view_published', 'frameworks.manage']),
    ]);
    renderAt('/import');

    await screen.findByRole('heading', { level: 2, name: 'Import history' });
    expect(screen.queryByText('Export a curriculum version')).not.toBeInTheDocument();
  });
});
