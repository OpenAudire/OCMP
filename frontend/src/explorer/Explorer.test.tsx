import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type {
  ExplorerModule,
  ExplorerWeek,
  ProgrammeSummary,
  VersionStructure,
} from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { byWeek } from './explorer';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchVersionStructure: vi.fn(),
  fetchExplorerWeek: vi.fn(),
  fetchExplorerModule: vi.fn(),
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
      { id: 'v2', academic_year: 2027, status: 'draft', published_at: null, based_on_id: 'v1' },
      { id: 'v1', academic_year: 2026, status: 'published', published_at: '2026-01-01T00:00:00Z', based_on_id: null },
    ],
  },
];

const week: ExplorerWeek = {
  version_id: 'v1',
  programme_code: 'BHS',
  academic_year: 2026,
  week: 1,
  weeks: [1, 2, 4],
  sessions: [
    {
      id: 's1',
      title: 'Cardiac cycle',
      week: 1,
      format: 'Lecture',
      contact_minutes: 60,
      self_study_minutes: 30,
      description: '',
      objectives: [{ id: 'o1', text: 'Describe the cardiac cycle.' }],
      module_id: 'm1',
      module_code: 'HSC201',
      module_name: 'Cardiovascular system',
    },
    {
      id: 's2',
      title: 'Bones',
      week: 1,
      format: null,
      contact_minutes: 0,
      self_study_minutes: 0,
      description: '',
      objectives: [],
      module_id: 'm2',
      module_code: 'HSC101',
      module_name: 'Anatomy',
    },
  ],
};

const structure = {
  version: programmes[0].versions[1],
  programme: { id: 'p1', code: 'BHS', name: 'BSc Health Sciences' },
  partial: false,
  outcome_count: 1,
  phases: [
    {
      id: 'ph1',
      name: 'Year 2',
      kind: 'year',
      position: 0,
      modules: [
        {
          id: 'm1',
          code: 'HSC201',
          name: 'Cardiovascular system',
          phase_id: 'ph1',
          position: 0,
          credits: '12.0',
          nqf_level: 6,
          context_only: false,
          objective_count: 3,
          can_edit: false,
          events: [{ id: 's1' }, { id: 's3' }],
        },
        {
          id: 'm9',
          code: 'CTX900',
          name: 'Context only',
          phase_id: 'ph1',
          position: 1,
          credits: null,
          nqf_level: null,
          context_only: true,
          objective_count: 0,
          can_edit: false,
          events: [],
        },
      ],
    },
  ],
  modules_without_phase: [],
  can_edit: false,
  can_change_status: false,
  can_copy_forward: false,
  can_edit_outcomes: false,
  can_approve_outcomes: false,
  can_unpublish: false,
} as unknown as VersionStructure;

const moduleView: ExplorerModule = {
  id: 'm1',
  version_id: 'v1',
  code: 'HSC201',
  name: 'Cardiovascular system',
  credits: 12,
  nqf_level: 6,
  description: 'How the heart and vessels work.',
  contact_minutes: 120,
  self_study_minutes: 60,
  outcomes: [{ id: 'o0', text: 'Interpret cardiac investigations.' }],
  sessions: [
    { ...week.sessions[0] },
    {
      ...week.sessions[0],
      id: 's3',
      title: 'Skills lab',
      week: null,
      objectives: [],
    },
  ],
  assessments: [
    {
      id: 'a1',
      name: 'Block test',
      method: 'MCQ',
      weight: 40,
      timing: 'Week 6',
      time_minutes: 90,
      items: [
        {
          id: 'i1',
          label: 'Question 1',
          marks: 10,
          objectives: [{ id: 'o1', text: 'Describe the cardiac cycle.' }],
        },
      ],
      covered: [
        { id: 'o0', text: 'Interpret cardiac investigations.' },
        { id: 'o1', text: 'Describe the cardiac cycle.' },
      ],
    },
  ],
  tags: [{ list_name: 'Themes', label: 'Ethics' }],
};

beforeEach(() => {
  vi.resetAllMocks();
  window.localStorage.clear();
  void i18n.changeLanguage('en');
  applyTerminology(i18n, {});
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([role('student', ['curriculum.view_published'])]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
  mocked.fetchProgrammes.mockResolvedValue(programmes);
  mocked.fetchVersionStructure.mockResolvedValue(structure);
  mocked.fetchExplorerWeek.mockResolvedValue(week);
  mocked.fetchExplorerModule.mockResolvedValue(moduleView);
  mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
});

describe('Explorer: by week', () => {
  it('lists the sessions of a week with their module, format, time and objectives', async () => {
    renderAt('/explorer');

    expect(await screen.findByRole('heading', { level: 1, name: 'Explorer' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: 'Week 1' })).toBeInTheDocument();
    const card = (await screen.findByText('Cardiac cycle')).closest('article') as HTMLElement;
    expect(within(card).getByText('Lecture')).toBeInTheDocument();
    expect(within(card).getByText('60 minutes with the teacher · 30 minutes of self-study')).toBeInTheDocument();
    expect(within(card).getByText('Describe the cardiac cycle.')).toBeInTheDocument();
    expect(within(card).getByRole('link', { name: /HSC201 Cardiovascular system/ })).toHaveAttribute(
      'href',
      '/explorer/modules/m1'
    );
    const bones = screen.getByText('Bones').closest('article') as HTMLElement;
    expect(within(bones).getByText('No objectives are written for this session yet.')).toBeInTheDocument();
    // Only published versions are offered: the draft is not.
    expect(mocked.fetchExplorerWeek).toHaveBeenCalledWith('v1', 1);
    expect(screen.queryByLabelText('Curriculum version')).not.toBeInTheDocument();
  });

  it('steps to the earlier and later weeks that have sessions and remembers the week', async () => {
    renderAt('/explorer');
    await screen.findByText('Cardiac cycle');

    fireEvent.click(screen.getByRole('button', { name: /Later/ }));

    await waitFor(() => expect(mocked.fetchExplorerWeek).toHaveBeenLastCalledWith('v1', 2));
    expect(window.localStorage.getItem('cic.explorerWeek')).toBe('2');
    expect(screen.getByRole('button', { name: /Earlier/ })).toBeEnabled();
  });

  it('says what to do about a week with nothing in it', async () => {
    mocked.fetchExplorerWeek.mockResolvedValue({ ...week, week: 3, sessions: [] });

    renderAt('/explorer?week=3');

    expect(await screen.findByText('Nothing is planned for week 3')).toBeInTheDocument();
    expect(screen.getByText('Weeks with sessions: 1, 2, 4.')).toBeInTheDocument();
  });

  it('says so when no version is published', async () => {
    mocked.fetchProgrammes.mockResolvedValue([
      { ...programmes[0], versions: [programmes[0].versions[0]] },
    ]);

    renderAt('/explorer');

    expect(await screen.findByText('No published curriculum yet')).toBeInTheDocument();
    expect(mocked.fetchExplorerWeek).not.toHaveBeenCalled();
  });
});

describe('Explorer: modules', () => {
  it('lists the modules by phase, leaving out modules shown only for context', async () => {
    renderAt('/explorer?view=browse');

    const link = await screen.findByRole('link', { name: /HSC201 Cardiovascular system/ });
    expect(link).toHaveAttribute('href', '/explorer/modules/m1');
    expect(screen.getByRole('heading', { level: 2, name: 'Year 2' })).toBeInTheDocument();
    expect(screen.getByText('12 credits')).toBeInTheDocument();
    expect(screen.getByText('2 sessions')).toBeInTheDocument();
    expect(screen.queryByText('Context only')).not.toBeInTheDocument();
  });

  it('switches between the two views and keeps the choice in the address', async () => {
    renderAt('/explorer');
    await screen.findByText('Cardiac cycle');

    fireEvent.click(screen.getByLabelText('Modules'));

    expect(await screen.findByRole('link', { name: /HSC201/ })).toBeInTheDocument();
  });
});

describe('Explorer: a module', () => {
  it('shows what it covers, the sessions week by week and what each assessment covers', async () => {
    renderAt('/explorer/modules/m1');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'HSC201 Cardiovascular system' })
    ).toBeInTheDocument();
    expect(screen.getByText('12 credits · NQF level 6 · 120 minutes with the teacher · 60 minutes of self-study')).toBeInTheDocument();
    const covers = screen.getByRole('heading', { name: 'What this module covers' }).closest('section') as HTMLElement;
    expect(within(covers).getByText('Interpret cardiac investigations.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Week 1' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'No week set' })).toBeInTheDocument();
    const test = screen.getByRole('heading', { name: 'Block test' }).closest('article') as HTMLElement;
    expect(within(test).getByText('MCQ · 40% of the module mark · Week 6 · 90 minutes')).toBeInTheDocument();
    expect(within(test).getByText('What it covers')).toBeInTheDocument();
    expect(within(test).getAllByText('Describe the cardiac cycle.').length).toBeGreaterThan(0);
    expect(screen.getByText('Ethics')).toBeInTheDocument();
  });

  it('marks the session a search hit pointed at', async () => {
    renderAt('/explorer/modules/m1?session=s3');

    const card = (await screen.findByText('Skills lab')).closest('article') as HTMLElement;
    expect(card).toHaveAttribute('aria-current', 'true');
  });

  it('says a module that is not available is not available', async () => {
    mocked.fetchExplorerModule.mockRejectedValue(
      Object.assign(new Error('nope'), { isAxiosError: true, response: { status: 404 } })
    );

    renderAt('/explorer/modules/missing');

    expect(await screen.findByRole('heading', { name: /Explorer|This module is not available/ })).toBeInTheDocument();
  });
});

describe('byWeek', () => {
  it('groups by week in order and puts sessions without a week last', () => {
    const groups = byWeek([
      { week: null, id: 'a' },
      { week: 3, id: 'b' },
      { week: 1, id: 'c' },
      { week: 3, id: 'd' },
    ]);

    expect(groups.map(([w, list]) => [w, list.map((s) => s.id)])).toEqual([
      [1, ['c']],
      [3, ['b', 'd']],
      [null, ['a']],
    ]);
  });
});
