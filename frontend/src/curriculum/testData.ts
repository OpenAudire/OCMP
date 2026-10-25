import type { ProgrammeSummary, StructureModule, VersionStructure } from '../api/types';

/** Fictional curriculum data for the curriculum tests. */

export const programmes: ProgrammeSummary[] = [
  {
    id: 'p1',
    code: 'BHS',
    name: 'BSc Health Sciences (Demo)',
    faculty_id: 'f1',
    faculty_name: 'Faculty of Health Sciences',
    status: 'active',
    versions: [
      {
        id: 'v2027',
        academic_year: 2027,
        status: 'draft',
        published_at: null,
        based_on_id: 'v2026',
      },
      {
        id: 'v2026',
        academic_year: 2026,
        status: 'published',
        published_at: '2026-01-10T08:00:00Z',
        based_on_id: null,
      },
    ],
  },
  {
    id: 'p2',
    code: 'BNS',
    name: 'Bachelor of Nursing (Demo)',
    faculty_id: 'f1',
    faculty_name: 'Faculty of Health Sciences',
    status: 'active',
    versions: [
      { id: 'n2026', academic_year: 2026, status: 'draft', published_at: null, based_on_id: null },
    ],
  },
];

function module(overrides: Partial<StructureModule> & Pick<StructureModule, 'id' | 'code'>) {
  return {
    name: `Module ${overrides.code}`,
    phase_id: null,
    position: 0,
    credits: '12.0',
    nqf_level: 5,
    context_only: false,
    objective_count: 0,
    events: [],
    ...overrides,
  } satisfies StructureModule;
}

export const cardio = module({
  id: 'm2',
  code: 'HSC201',
  name: 'Cardiovascular system',
  phase_id: 'y2',
  credits: '16.0',
  objective_count: 1,
  events: [
    {
      id: 'e1',
      title: 'Cardiac cycle',
      position: 0,
      week: 4,
      format: 'Lecture',
      contact_minutes: 90,
      self_study_minutes: 120,
      objective_count: 1,
    },
    {
      id: 'e2',
      title: 'ECG interpretation workshop',
      position: 1,
      week: null,
      format: null,
      contact_minutes: 120,
      self_study_minutes: 90,
      objective_count: 0,
    },
  ],
});

export const structure: VersionStructure = {
  version: programmes[0].versions[0],
  programme: { id: 'p1', code: 'BHS', name: 'BSc Health Sciences (Demo)' },
  partial: false,
  outcome_count: 1,
  phases: [
    {
      id: 'y1',
      name: 'Year 1',
      kind: 'year',
      position: 0,
      modules: [module({ id: 'm1', code: 'HSC101', name: 'Foundations', phase_id: 'y1' })],
    },
    { id: 'y2', name: 'Year 2', kind: 'year', position: 1, modules: [cardio] },
  ],
  modules_without_phase: [module({ id: 'm3', code: 'HSC300', name: 'Research thread' })],
};
