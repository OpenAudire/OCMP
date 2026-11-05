import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type { Dashboard, DashboardTrace, ProgrammeSummary } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchDashboard: vi.fn(),
  fetchDashboardTrace: vi.fn(),
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
    versions: [
      { id: 'v1', academic_year: 2027, status: 'draft', published_at: null, based_on_id: null },
    ],
  },
];

const dashboard: Dashboard = {
  version: {
    id: 'v1',
    academic_year: 2027,
    status: 'draft',
    programme_code: 'BHS',
    programme_name: 'BSc Health Sciences',
  },
  partial: false,
  framework: { id: 'fw1', name: 'Competencies', version_label: '1.0' },
  frameworks: [{ id: 'fw1', name: 'Competencies', version_label: '1.0' }],
  kpis: [
    {
      key: 'mapped',
      unit: 'percent',
      value: 0.6,
      numerator: 12,
      denominator: 20,
      series: [
        { date: '2026-09-10', value: 0.4 },
        { date: '2026-11-05', value: 0.6 },
      ],
    },
    {
      key: 'coverage',
      unit: 'percent',
      value: 0.55,
      numerator: null,
      denominator: null,
      series: [],
    },
    {
      key: 'gaps',
      unit: 'count',
      value: 3,
      numerator: 3,
      denominator: 8,
      series: [
        { date: '2026-09-10', value: 5 },
        { date: '2026-11-05', value: 3 },
      ],
    },
    {
      key: 'credits',
      unit: 'count',
      value: 1,
      numerator: 1,
      denominator: 2,
      series: [],
    },
  ],
  snapshot_on: '2026-11-05',
  progress: [
    { module_id: 'm1', code: 'HSC201', name: 'Cardiovascular system', objectives: 4, mapped: 3, waiting: 1 },
    { module_id: 'm2', code: 'HSC101', name: 'Anatomy', objectives: 0, mapped: 0, waiting: 0 },
  ],
  low_percent: 40,
  comparison: {
    version_id: 'v0',
    academic_year: 2026,
    status: 'published',
    groups: [
      { id: 'g1', code: 'G1', title: 'Clinical', now: 0.7, before: 0.5 },
      { id: 'g2', code: 'G2', title: 'Ethics', now: 0.2, before: null },
    ],
  },
  credits: {
    hours_per_credit: 10,
    tolerance_percent: 10,
    credits_per_year: 120,
    years: [{ name: 'Year 2', credits: 24, expected_credits: 120, status: 'under' }],
    modules: [
      {
        module_id: 'm1',
        code: 'HSC201',
        name: 'Cardiovascular system',
        credits: 12,
        expected_hours: 120,
        planned_hours: 100,
        difference_percent: -16.7,
        status: 'under',
      },
      {
        module_id: 'm2',
        code: 'HSC101',
        name: 'Anatomy',
        credits: 12,
        expected_hours: 120,
        planned_hours: 121,
        difference_percent: 0.8,
        status: 'ok',
      },
    ],
  },
  generated_at: '2026-11-05T10:00:00Z',
};

const trace: DashboardTrace = {
  framework: dashboard.framework,
  partial: false,
  outcomes: [
    { id: 'po1', text: 'Practise safely.' },
    { id: 'po2', text: 'Communicate well.' },
  ],
  outcome: { id: 'po1', text: 'Practise safely.' },
  module_outcomes: [{ id: 'mo1', text: 'Interpret cardiac investigations.', module_code: 'HSC201' }],
  groups: [{ module_outcome_id: 'mo1', objectives: 2, sessions: 1 }],
  items: [
    { id: 'i1', code: 'G1.1', title: 'Skill 1', coverage: 4, objectives: 2 },
    { id: 'i2', code: 'G1.2', title: 'Skill 2', coverage: 1, objectives: 1 },
  ],
  items_total: 2,
  reaches: [
    { group: 0, item_id: 'i1' },
    { group: 0, item_id: 'i2' },
  ],
  module_count: 1,
  session_objectives: 2,
  sessions: 1,
};

beforeEach(() => {
  vi.resetAllMocks();
  void i18n.changeLanguage('en');
  applyTerminology(i18n, {});
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([
    role('curriculum_office', ['reports.view', 'curriculum.view', 'curriculum.view_published']),
  ]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
  mocked.fetchProgrammes.mockResolvedValue(programmes);
  mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
  mocked.fetchDashboard.mockResolvedValue(dashboard);
  mocked.fetchDashboardTrace.mockResolvedValue(trace);
});

describe('Committee dashboard', () => {
  it('shows the four indicators with their figure, note and change in words', async () => {
    renderAt('/dashboard?version=v1');

    const section = await screen.findByRole('region', { name: 'Key indicators' });
    expect(within(section).getByText('60%')).toBeInTheDocument();
    expect(within(section).getByText('12 of 20 objectives have an accepted link')).toBeInTheDocument();
    expect(within(section).getByText('Up 20 points since 2026-09-10')).toBeInTheDocument();
    expect(within(section).getByText('55%')).toBeInTheDocument();
    expect(within(section).getByText('Down 2 since 2026-09-10')).toBeInTheDocument();
    expect(
      within(section).getByRole('img', {
        name: 'Objectives mapped: trend from 40% to 60% over the last eight weeks',
      })
    ).toBeInTheDocument();
    // An indicator with no history has no line, only its figure.
    expect(within(section).getAllByRole('img')).toHaveLength(2);
    expect(mocked.fetchDashboard).toHaveBeenCalledWith('v1', null);
  });

  it('says so when there are no snapshots yet', async () => {
    mocked.fetchDashboard.mockResolvedValue({ ...dashboard, snapshot_on: null });

    renderAt('/dashboard?version=v1');

    expect(await screen.findByText(/no daily snapshots yet/)).toBeInTheDocument();
  });

  it('draws the traceability as text nodes and changes the outcome', async () => {
    renderAt('/dashboard?version=v1');

    const section = (await screen.findByRole('heading', { name: /Traceability/ })).closest(
      'section'
    ) as HTMLElement;
    expect(await within(section).findByText('HSC201')).toBeInTheDocument();
    expect(within(section).getByText('G1.1 · 4 of 5')).toBeInTheDocument();
    expect(within(section).getByText('2 objectives')).toBeInTheDocument();
    expect(
      within(section).getByText(/reaches 2 session objectives in 1 sessions through 1 modules, and 2 framework items/)
    ).toBeInTheDocument();

    fireEvent.change(within(section).getByRole('combobox', { name: 'Programme outcome' }), {
      target: { value: 'po2' },
    });
    await waitFor(() =>
      expect(mocked.fetchDashboardTrace).toHaveBeenLastCalledWith('v1', 'fw1', 'po2')
    );
  });

  it('compares each group with the last published version and marks low ones', async () => {
    renderAt('/dashboard?version=v1');

    const section = (await screen.findByRole('heading', { name: /Weighted coverage by/ })).closest(
      'section'
    ) as HTMLElement;
    expect(within(section).getByText('70%')).toBeInTheDocument();
    expect(
      within(section).getByRole('img', { name: 'Clinical: 70% now, 50% in the 2026 version' })
    ).toBeInTheDocument();
    expect(
      within(section).getByRole('img', { name: 'Ethics: 20% now, – in the 2026 version' })
    ).toBeInTheDocument();
    expect(within(section).getByText('low')).toBeInTheDocument();
  });

  it('lists mapping progress by module with the waiting suggestions apart', async () => {
    renderAt('/dashboard?version=v1');

    const section = (await screen.findByRole('heading', { name: 'Mapping progress by module' })).closest(
      'section'
    ) as HTMLElement;
    expect(within(section).getByText('75%')).toBeInTheDocument();
    expect(within(section).getByText('1 waiting')).toBeInTheDocument();
    expect(
      within(section).getByRole('img', { name: 'Cardiovascular system: 3 of 4 objectives mapped' })
    ).toBeInTheDocument();
  });

  it('shows the credits table and can limit it to modules outside the tolerance', async () => {
    renderAt('/dashboard?version=v1');

    const section = (await screen.findByRole('heading', { name: 'Credits and notional hours' })).closest(
      'section'
    ) as HTMLElement;
    expect(within(section).getByText('Anatomy', { exact: false })).toBeInTheDocument();
    expect(within(section).getByText('-16.7%')).toBeInTheDocument();
    expect(within(section).getByText('Under')).toBeInTheDocument();

    fireEvent.click(within(section).getByLabelText('Only modules outside the tolerance'));

    expect(within(section).queryByText('Within tolerance')).not.toBeInTheDocument();
    expect(within(section).getByText('Under')).toBeInTheDocument();
  });

  it('warns a person who sees only part of the version', async () => {
    mocked.fetchDashboard.mockResolvedValue({ ...dashboard, partial: true });

    renderAt('/dashboard?version=v1');

    expect(await screen.findByText(/You see only part of this version/)).toBeInTheDocument();
  });

  it('is not shown to people without report rights', async () => {
    mocked.fetchMyRoles.mockResolvedValue([role('lecturer', ['curriculum.view'])]);

    renderAt('/dashboard?version=v1');

    expect(await screen.findByText(/do not have access|no access|permission/i)).toBeInTheDocument();
    expect(mocked.fetchDashboard).not.toHaveBeenCalled();
  });
});
