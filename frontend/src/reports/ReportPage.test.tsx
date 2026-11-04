import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { ProgrammeSummary, ReportDocument } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchFrameworkLibrary: vi.fn(),
  fetchReport: vi.fn(),
  fetchReviewCount: vi.fn(),
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
    versions: [{ id: 'v1', academic_year: 2027, status: 'draft', published_at: null, based_on_id: null }],
  },
];

const document: ReportDocument = {
  key: 'redundancy',
  title: 'Redundancy report',
  method: 'Sessions per framework item and near-duplicate objectives',
  made_on: '2026-11-04T09:42:00Z',
  about: [
    { label: 'Report', value: 'Redundancy report' },
    { label: 'Method', value: 'Sessions per framework item, from accepted mapping links.' },
    { label: 'Framework', value: 'Competencies (1.0)' },
  ],
  sections: [
    {
      title: 'Items taught in many sessions',
      note: 'Items tied to at least 4.0 sessions.',
      columns: [
        { label: 'Code', kind: 'text' },
        { label: 'Sessions', kind: 'integer' },
        { label: 'Share', kind: 'percent' },
        { label: 'Score', kind: 'number' },
      ],
      rows: [['G1.1', 5, 0.4286, 0.5], ['G1.2', 4, null, 1.25]],
    },
    {
      title: 'Near-duplicate objectives in different modules',
      note: '',
      columns: [{ label: 'Objective', kind: 'text' }],
      rows: [],
    },
  ],
};

describe('Report page', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([
      role('curriculum_office', ['curriculum.view', 'reports.view']),
    ]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchFrameworkLibrary.mockResolvedValue({
      frameworks: [
        { id: 'fw1', key: 'c', name: 'Competencies', version_label: '1.0', status: 'active' } as never,
      ],
      can_manage: false,
    });
    mocked.fetchReport.mockResolvedValue(document);
  });

  it('lists every report on the reports page', async () => {
    renderAt('/reports');

    expect(await screen.findAllByRole('link', { name: 'Open the report' })).toHaveLength(4);
    expect(screen.getByRole('heading', { level: 2, name: 'Redundancy report' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Traceability report' })).toBeInTheDocument();
  });

  it('shows how the report was made and its tables with the figures formatted', async () => {
    renderAt('/reports/redundancy?version=v1&framework=fw1');

    const panel = await screen.findByLabelText('The method and what it covers');
    expect(within(panel).getByText('Sessions per framework item, from accepted mapping links.')).toBeInTheDocument();
    expect(within(panel).getByText('Competencies (1.0)')).toBeInTheDocument();
    expect(mocked.fetchReport).toHaveBeenCalledWith('v1', 'redundancy', { framework_id: 'fw1' });
    const section = (await screen.findByRole('heading', { level: 2, name: 'Items taught in many sessions' }))
      .closest('section') as HTMLElement;
    expect(within(section).getByText('Items tied to at least 4.0 sessions.')).toBeInTheDocument();
    const rows = within(section).getAllByRole('row');
    expect(within(rows[1]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['G1.1', '5', '43%', '0.50']);
    expect(within(rows[2]).getAllByRole('cell').map((c) => c.textContent)).toEqual(['G1.2', '4', '–', '1.25']);
  });

  it('says so when a table is empty', async () => {
    renderAt('/reports/redundancy?version=v1&framework=fw1');

    const section = (
      await screen.findByRole('heading', { level: 2, name: 'Near-duplicate objectives in different modules' })
    ).closest('section') as HTMLElement;
    expect(within(section).getByText('None.')).toBeInTheDocument();
  });

  it('offers the report as Excel and PDF with the framework chosen', async () => {
    renderAt('/reports/redundancy?version=v1&framework=fw1');

    expect(await screen.findByRole('link', { name: /Download as Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/curriculum-versions/v1/reports/redundancy/export?format=xlsx&framework_id=fw1'
    );
    expect(screen.getByRole('link', { name: /Download as PDF/ })).toHaveAttribute(
      'href',
      '/api/v1/curriculum-versions/v1/reports/redundancy/export?format=pdf&framework_id=fw1'
    );
  });

  it('asks again when the framework changes', async () => {
    mocked.fetchFrameworkLibrary.mockResolvedValue({
      frameworks: [
        { id: 'fw1', key: 'c', name: 'Competencies', version_label: '1.0', status: 'active' } as never,
        { id: 'fw2', key: 'd', name: 'Other', version_label: '2.0', status: 'active' } as never,
      ],
      can_manage: false,
    });
    renderAt('/reports/redundancy?version=v1&framework=fw1');
    await screen.findByLabelText('The method and what it covers');

    fireEvent.change(screen.getByLabelText('Framework'), { target: { value: 'fw2' } });

    await waitFor(() =>
      expect(mocked.fetchReport).toHaveBeenLastCalledWith('v1', 'redundancy', { framework_id: 'fw2' })
    );
  });

  it('works without a framework where the report allows it', async () => {
    renderAt('/reports/traceability?version=v1');

    await screen.findByLabelText('The method and what it covers');
    expect(mocked.fetchReport).toHaveBeenCalledWith('v1', 'traceability', {});
    expect(screen.getByRole('option', { name: 'All frameworks' })).toBeInTheDocument();
  });

  it('says that the reader sees only part of the curriculum', async () => {
    mocked.fetchReport.mockResolvedValue({
      ...document,
      about: [...document.about, { label: 'Only part of the curriculum', value: 'x' }],
    });
    renderAt('/reports/redundancy?version=v1&framework=fw1');

    expect(await screen.findByText(/only the part of the curriculum you can see/)).toBeInTheDocument();
  });

  it('says why a report was refused', async () => {
    mocked.fetchReport.mockRejectedValue(new ApiError(403, 'no'));
    renderAt('/reports/redundancy?version=v1&framework=fw1');

    expect(await screen.findByText(/You do not have permission to see this report/)).toBeInTheDocument();
  });

  it('goes back to the reports page for a report that does not exist', async () => {
    renderAt('/reports/nonsense');

    expect(await screen.findAllByRole('link', { name: 'Open the report' })).not.toHaveLength(0);
    expect(mocked.fetchReport).not.toHaveBeenCalled();
  });
});
