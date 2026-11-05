import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type { CoverageReport, GapReport, ProgrammeSummary } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { formatMade, percent, shadeOf } from './coverageFormat';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchFrameworkLibrary: vi.fn(),
  fetchCoverage: vi.fn(),
  fetchGaps: vi.fn(),
  fetchReviewCount: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const programmes: ProgrammeSummary[] = [
  {
    id: 'p1',
    code: 'BHS',
    name: 'BSc Health Sciences',
    faculty_id: 'f',
    faculty_name: 'F',
    status: 'active',
    versions: [{ id: 'v1', academic_year: 2027, status: 'draft', published_at: null, based_on_id: null }],
  },
];

const meta = {
  framework: { id: 'fw1', name: 'Competencies', version_label: '1.0' },
  version: {
    id: 'v1',
    academic_year: 2027,
    status: 'draft' as const,
    programme_code: 'BHS',
    programme_name: 'BSc',
  },
  method: 'single' as const,
  definition: 'Covered when at least one accepted link points at the item.',
  params: {
    multiple_match_n: 3,
    subordinate_min_percent: 50,
    below_depth_percent: 50,
    weighted_low_percent: 40,
  },
  generated_at: '2026-11-04T09:42:00Z',
  partial: false,
  objectives_in_scope: 60,
};

const counts = (
  headline: number | null,
  unit: 'items' | 'groups',
  covered: number,
  partial: number,
  uncovered: number
) => ({
  headline,
  unit,
  total: covered + partial + uncovered,
  covered,
  partial,
  uncovered,
});

const report: CoverageReport = {
  ...meta,
  summary: {
    leaves: 4,
    groups: 1,
    methods: {
      single: counts(0.75, 'items', 3, 0, 1),
      multiple: counts(0.25, 'items', 1, 0, 3),
      subordinate: counts(0.6667, 'groups', 1, 0, 0),
      weighted: counts(0.55, 'items', 2, 1, 1),
    },
    links: 9,
    group_links: 2,
    bulk_links: 3,
    imported_links: 2,
    recheck_links: 1,
    waiting_links: 2,
  },
  items: [
    {
      id: 'g1',
      code: 'G1',
      title: 'Clinical',
      parent_id: null,
      depth: 0,
      is_leaf: false,
      leaves: 3,
      leaves_covered: 2,
      links: 2,
      bulk_links: 0,
      imported_links: 0,
      recheck_links: 0,
      waiting: 0,
      objectives: 2,
      value: 0.6667,
      status: 'partial',
      only_bulk: false,
      only_imported: false,
    },
    {
      id: 'i1',
      code: 'G1.1',
      title: 'Skill 1',
      parent_id: 'g1',
      depth: 1,
      is_leaf: true,
      leaves: 1,
      leaves_covered: null,
      links: 3,
      bulk_links: 3,
      imported_links: 0,
      recheck_links: 0,
      waiting: 0,
      objectives: 3,
      value: 1,
      status: 'covered',
      only_bulk: true,
      only_imported: false,
    },
    {
      id: 'i2',
      code: 'G1.2',
      title: 'Skill 2',
      parent_id: 'g1',
      depth: 1,
      is_leaf: true,
      leaves: 1,
      leaves_covered: null,
      links: 1,
      bulk_links: 0,
      imported_links: 1,
      recheck_links: 1,
      waiting: 2,
      objectives: 1,
      value: 1,
      status: 'covered',
      only_bulk: false,
      only_imported: true,
    },
  ],
  columns: [
    { key: 'ph1', kind: 'phase', label: 'Year 2' },
    { key: 'programme', kind: 'programme', label: '' },
    { key: 'none', kind: 'none', label: '' },
  ],
  heatmap: [
    { id: 'g1', code: 'G1', title: 'Clinical', cells: { all: 0.6667, ph1: 0.5, programme: 0, none: 0.1 } },
  ],
};

const gaps: GapReport = {
  ...meta,
  gaps: [
    {
      id: 'i3',
      code: 'G1.3',
      title: 'Skill 3',
      path: [{ id: 'g1', code: 'G1', title: 'Clinical' }],
      status: 'none',
      value: 0,
      links: 0,
      waiting: 1,
      reason: 'no accepted link',
      leaves: 1,
      leaves_covered: null,
    },
    {
      id: 'i2',
      code: 'G1.2',
      title: 'Skill 2',
      path: [{ id: 'g1', code: 'G1', title: 'Clinical' }],
      status: 'none',
      value: 0,
      links: 1,
      waiting: 0,
      reason: '1 of 3 accepted links',
      leaves: 1,
      leaves_covered: null,
    },
  ],
  group_gaps: [
    {
      id: 'g1',
      code: 'G1',
      title: 'Clinical',
      path: [],
      status: 'partial',
      value: 0.3333,
      links: 0,
      waiting: 0,
      reason: '1 of 3 items below it covered',
      leaves: 3,
      leaves_covered: 1,
    },
  ],
  unlinked: [
    {
      id: 'o1',
      text: 'Name the bones.',
      level: 'module',
      module_id: 'm2',
      module_code: 'HSC101',
      event_id: null,
      event_title: null,
      waiting: 0,
    },
  ],
  only_waiting: [
    {
      id: 'o2',
      text: 'Interpret cardiac investigations.',
      level: 'module',
      module_id: 'm1',
      module_code: 'HSC201',
      event_id: null,
      event_title: null,
      waiting: 2,
    },
  ],
  unlinked_total: 1,
  only_waiting_total: 1,
};

describe('coverage figures as text', () => {
  it('shows shares as whole percentages and shades them in steps', () => {
    expect(percent(0.6667)).toBe('67%');
    expect(percent(0)).toBe('0%');
    expect([0, 0.1, 0.39, 0.4, 0.69, 0.7, 1].map(shadeOf)).toEqual([0, 1, 1, 2, 2, 3, 3]);
  });

  it('writes when a report was made, and leaves a date it cannot read as it is', () => {
    expect(formatMade('2026-11-04T09:42:00Z', 'en')).toMatch(/2026/);
    expect(formatMade('not a date', 'en')).toBe('not a date');
  });
});

describe('Coverage report', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('curriculum_office', ['curriculum.view', 'reports.view'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchFrameworkLibrary.mockResolvedValue({
      frameworks: [
        { id: 'fw1', key: 'c', name: 'Competencies', version_label: '1.0', status: 'active' } as never,
      ],
      can_manage: false,
    });
    mocked.fetchCoverage.mockResolvedValue(report);
    mocked.fetchGaps.mockResolvedValue(gaps);
  });

  it('links the two reports from the reports page', async () => {
    renderAt('/reports');

    expect(await screen.findAllByRole('link', { name: 'Open the report' })).toHaveLength(7);
  });

  it('states the method, its definition, the framework, the version and when it was made', async () => {
    renderAt('/reports/coverage?version=v1&framework=fw1');

    const panel = await screen.findByLabelText('The method and what it covers');
    expect(within(panel).getByText(/Single match\. Covered when at least one accepted link/)).toBeInTheDocument();
    expect(within(panel).getByText('Competencies (1.0)')).toBeInTheDocument();
    expect(within(panel).getByText(/BHS · 2027 · Draft/)).toBeInTheDocument();
    expect(within(panel).getByText(/2026/)).toBeInTheDocument();
    expect(mocked.fetchCoverage).toHaveBeenCalledWith('v1', 'fw1', 'single');
  });

  it('shows all four methods in the summary and marks the one shown', async () => {
    renderAt('/reports/coverage?version=v1&framework=fw1');

    const table = (await screen.findByRole('heading', { level: 2, name: 'Summary of the framework' }))
      .closest('section') as HTMLElement;
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(5);
    expect(within(rows[1]).getByText(/Single match.*\(shown below\)/)).toBeInTheDocument();
    // The headline of each method, in its own words.
    expect(within(rows[1]).getByText('75%')).toBeInTheDocument();
    expect(within(rows[1]).getByText('of items covered')).toBeInTheDocument();
    expect(within(rows[2]).getByText('25%')).toBeInTheDocument();
    expect(within(rows[3]).getByText('67%')).toBeInTheDocument();
    expect(within(rows[3]).getByText('average over groups')).toBeInTheDocument();
    expect(within(rows[3]).getByText('1 groups')).toBeInTheDocument();
    expect(within(rows[4]).getByText('55%')).toBeInTheDocument();
    expect(within(rows[4]).getByText('degree of coverage')).toBeInTheDocument();
    expect(within(table).getByText(/7 accepted links counted/)).toBeInTheDocument();
    expect(within(table).getByText(/2 links made to groups themselves, not counted/)).toBeInTheDocument();
    expect(within(table).getByText(/3 links accepted in bulk/)).toBeInTheDocument();
    expect(within(table).getByText(/2 links accepted by import/)).toBeInTheDocument();
    expect(within(table).getByText(/1 link needs a re-check/)).toBeInTheDocument();
    expect(within(table).getByText(/2 suggestions waiting for review/)).toBeInTheDocument();
  });

  it('prints the heatmap with a percentage in every cell and names the columns', async () => {
    renderAt('/reports/coverage?version=v1&framework=fw1');

    const section = (await screen.findByRole('heading', { level: 2, name: /Heatmap/ }))
      .closest('section') as HTMLElement;
    const headers = within(section).getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers).toEqual(['Group', 'All phases', 'Year 2', 'Programme outcomes', 'Modules without a phase']);
    const cells = within(section).getAllByRole('cell').map((c) => c.textContent);
    expect(cells).toEqual(['67%', '50%', '0%', '10%']);
  });

  it('flags items whose links were all accepted in bulk, need a re-check or wait', async () => {
    renderAt('/reports/coverage?version=v1&framework=fw1');

    const row = (await screen.findByText('Skill 1')).closest('tr') as HTMLElement;
    expect(within(row).getByText('All accepted in bulk')).toBeInTheDocument();
    const second = screen.getByText('Skill 2').closest('tr') as HTMLElement;
    expect(within(second).getByText('All accepted by import')).toBeInTheDocument();
    expect(within(second).getByText('1 link needs a re-check')).toBeInTheDocument();
    expect(within(second).getByText('2 suggestions waiting')).toBeInTheDocument();
    const group = screen.getByText(/Partial · 2 of 3 items covered/).closest('tr') as HTMLElement;
    expect(within(group).getByText('G1')).toBeInTheDocument();
    // Links made to the group itself are on its row but are not what its figure is made of.
    expect(within(group).getByText('2 made to the group itself, not counted')).toBeInTheDocument();
  });

  it('offers the report as Excel and PDF with the choices in the address', async () => {
    renderAt('/reports/coverage?version=v1&framework=fw1&method=weighted');

    const excel = await screen.findByRole('link', { name: /Download as Excel/ });
    const pdf = screen.getByRole('link', { name: /Download as PDF/ });
    expect(excel).toHaveAttribute(
      'href',
      '/api/v1/curriculum-versions/v1/reports/coverage/export?format=xlsx&framework_id=fw1&method=weighted'
    );
    expect(pdf).toHaveAttribute(
      'href',
      '/api/v1/curriculum-versions/v1/reports/coverage/export?format=pdf&framework_id=fw1&method=weighted'
    );
    expect(screen.getByText(/states the method and when the report was made/)).toBeInTheDocument();
  });

  it('asks again when the method changes', async () => {
    renderAt('/reports/coverage?version=v1&framework=fw1');
    await screen.findByLabelText('The method and what it covers');

    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'weighted' } });

    await waitFor(() => expect(mocked.fetchCoverage).toHaveBeenLastCalledWith('v1', 'fw1', 'weighted'));
  });

  it('says when the user sees only part of the version', async () => {
    mocked.fetchCoverage.mockResolvedValue({ ...report, partial: true });
    renderAt('/reports/coverage?version=v1&framework=fw1');

    expect(await screen.findByText(/only the part of the curriculum you can see/)).toBeInTheDocument();
  });

  it('says why a report was refused', async () => {
    const { ApiError } = await import('../api/client');
    mocked.fetchCoverage.mockRejectedValue(new ApiError(403, 'no'));
    renderAt('/reports/coverage?version=v1&framework=fw1');

    expect(await screen.findByText(/You do not have permission to see this report/)).toBeInTheDocument();
  });
});

describe('Gap report', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('curriculum_office', ['curriculum.view', 'reports.view'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchFrameworkLibrary.mockResolvedValue({
      frameworks: [
        { id: 'fw1', key: 'c', name: 'Competencies', version_label: '1.0', status: 'active' } as never,
      ],
      can_manage: false,
    });
    mocked.fetchGaps.mockResolvedValue(gaps);
  });

  it('lists the items that are not covered, with the group above and why', async () => {
    mocked.fetchGaps.mockResolvedValue({ ...gaps, method: 'multiple' });
    renderAt('/reports/gaps?version=v1&framework=fw1&method=multiple');

    const section = (await screen.findByRole('heading', { level: 2, name: /Items not covered \(2\)/ }))
      .closest('section') as HTMLElement;
    const rows = within(section).getAllByRole('row');
    expect(within(rows[1]).getByText('G1 Clinical')).toBeInTheDocument();
    expect(within(rows[1]).getByText('No accepted link')).toBeInTheDocument();
    expect(within(rows[1]).getByText('1 suggestion waiting')).toBeInTheDocument();
    expect(within(rows[2]).getByText('1 of 3 accepted links')).toBeInTheDocument();
    expect(mocked.fetchGaps).toHaveBeenCalledWith('v1', 'fw1', 'multiple');
  });

  it('offers the gap report as Excel and PDF', async () => {
    renderAt('/reports/gaps?version=v1&framework=fw1');

    expect(await screen.findByRole('link', { name: /Download as Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/curriculum-versions/v1/reports/gaps/export?format=xlsx&framework_id=fw1&method=single'
    );
    expect(screen.getByRole('link', { name: /Download as PDF/ })).toBeInTheDocument();
  });

  it('lists the groups under the share set for subordinate match', async () => {
    mocked.fetchGaps.mockResolvedValue({ ...gaps, method: 'subordinate' });
    renderAt('/reports/gaps?version=v1&framework=fw1&method=subordinate');

    const section = (await screen.findByRole('heading', { level: 2, name: /Groups under 50% \(1\)/ }))
      .closest('section') as HTMLElement;
    expect(within(section).getByText('G1')).toBeInTheDocument();
    expect(within(section).getByText(/1 of 3 items below it covered · 33%/)).toBeInTheDocument();
  });

  it('lists objectives with no accepted mapping apart from those with suggestions waiting', async () => {
    renderAt('/reports/gaps?version=v1&framework=fw1');

    const none = (await screen.findByRole('heading', { level: 2, name: /Objectives with no mapping \(1\)/ }))
      .closest('section') as HTMLElement;
    expect(within(none).getByRole('link', { name: 'Name the bones.' })).toHaveAttribute(
      'href',
      '/curriculum/versions/v1?item=module%3Am2'
    );
    const waiting = screen.getByRole('heading', { level: 2, name: /Objectives with suggestions waiting \(1\)/ })
      .closest('section') as HTMLElement;
    expect(within(waiting).getByText(/HSC201 · 2 suggestions waiting/)).toBeInTheDocument();
  });

  it('says so when there is no gap', async () => {
    mocked.fetchGaps.mockResolvedValue({ ...gaps, gaps: [], unlinked: [], only_waiting: [], unlinked_total: 0, only_waiting_total: 0 });
    renderAt('/reports/gaps?version=v1&framework=fw1');

    expect(await screen.findByText('Every item is covered by this method.')).toBeInTheDocument();
  });
});
