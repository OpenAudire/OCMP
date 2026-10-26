import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type {
  Assessment,
  ModuleDetail,
  ModuleHours,
  VersionCreditCheck,
} from '../api/types';
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
  fetchTaxonomyScales: vi.fn(),
  fetchAssessmentMethods: vi.fn(),
  fetchAssessableObjectives: vi.fn(),
  fetchCreditCheck: vi.fn(),
  createAssessment: vi.fn(),
  updateAssessment: vi.fn(),
  deleteAssessment: vi.fn(),
  createAssessmentItem: vi.fn(),
  updateAssessmentItem: vi.fn(),
  deleteAssessmentItem: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const exam: Assessment = {
  id: 'a1',
  module_id: 'm2',
  name: 'Final exam',
  method_value_id: 'mcq',
  method: 'Multiple-choice questions',
  weight: '60.0',
  timing: 'Week 12',
  time_minutes: 180,
  position: 0,
  items: [
    {
      id: 'i1',
      label: 'Question 1',
      marks: '10.0',
      position: 0,
      objective_ids: ['o-m2'],
    },
    { id: 'i2', label: 'Question 2', marks: null, position: 1, objective_ids: [] },
  ],
};

const hours = (status: ModuleHours['status']): ModuleHours => ({
  module_id: 'm2',
  code: 'HSC201',
  name: 'Cardiovascular system',
  phase_id: 'y2',
  credits: '16.0',
  nqf_level: 6,
  contact_hours: '3.5',
  self_study_hours: '3.5',
  assessment_hours: '3.0',
  planned_hours: '10.0',
  expected_hours: '160.0',
  difference_percent: '-93.8',
  status,
});

const moduleDetail = (
  overrides: Partial<ModuleDetail> = {},
  status: ModuleHours['status'] = 'under'
): ModuleDetail => ({
  id: 'm2',
  version_id: 'v2027',
  phase_id: 'y2',
  code: 'HSC201',
  name: 'Cardiovascular system',
  credits: '16.0',
  nqf_level: 6,
  description: '',
  external_lms_ref: null,
  event_count: 2,
  contact_minutes: 210,
  self_study_minutes: 210,
  outcomes: [],
  can_edit_objectives: false,
  can_approve_objectives: false,
  assessments: [exam],
  can_edit_assessments: true,
  hours: hours(status),
  ...overrides,
});

async function openModule() {
  renderAt('/curriculum/versions/v2027?item=module:m2');
  await screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
  return screen.findByRole('region', { name: 'Assessments' });
}

describe('assessments of a module', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([
      role('programme_director', ['curriculum.view', 'curriculum.edit']),
    ]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchProgramme.mockRejectedValue(new ApiError(500, 'not needed'));
    mocked.fetchVersionStructure.mockResolvedValue(structure);
    mocked.fetchProgrammeOutcomes.mockResolvedValue([]);
    mocked.fetchModule.mockResolvedValue(moduleDetail());
    mocked.fetchTaxonomyScales.mockResolvedValue([]);
    mocked.fetchAssessmentMethods.mockResolvedValue([
      { id: 'mcq', label: 'Multiple-choice questions', list_name: 'Assessment methods' },
      { id: 'osce', label: 'OSCE', list_name: 'Assessment methods' },
    ]);
    mocked.fetchAssessableObjectives.mockResolvedValue([
      { id: 'o-m2', level: 'module', text: 'Interpret cardiac tests.', event_title: null },
      {
        id: 'o-e1',
        level: 'learning_event',
        text: 'Describe the cardiac cycle.',
        event_title: 'Cardiac cycle',
      },
    ]);
  });

  it('shows the assessments, their items and what each item assesses', async () => {
    const section = await openModule();

    expect(await within(section).findByText('Final exam')).toBeInTheDocument();
    expect(within(section).getByText('Multiple-choice questions')).toBeInTheDocument();
    expect(within(section).getByText('60%')).toBeInTheDocument();
    expect(within(section).getByText('Week 12')).toBeInTheDocument();
    expect(within(section).getByText('10 marks')).toBeInTheDocument();
    expect(await within(section).findByText('Interpret cardiac tests.')).toBeInTheDocument();
    expect(within(section).getByText('Assesses 1 objective:')).toBeInTheDocument();
    expect(within(section).getByText('Not linked to any objective yet.')).toBeInTheDocument();
    // Weights that do not add up to 100 are pointed out, as advice.
    expect(within(section).getByText('The weights add up to 60%, not 100%.')).toBeInTheDocument();
  });

  it('shows no buttons to people who may not change assessments', async () => {
    mocked.fetchModule.mockResolvedValue(moduleDetail({ can_edit_assessments: false }));
    const section = await openModule();

    await within(section).findByText('Final exam');
    expect(within(section).queryByRole('button')).not.toBeInTheDocument();
  });

  it('says what the planned hours mean for the credits, in words', async () => {
    await openModule();

    expect(
      await screen.findByText(/Planned 10 h against 160 h expected: 94% under/)
    ).toBeInTheDocument();
    expect(screen.getByText('This is advice only. It never stops you saving.')).toBeInTheDocument();
  });

  it('says so when the planned hours fit', async () => {
    mocked.fetchModule.mockResolvedValue(moduleDetail({}, 'ok'));
    await openModule();

    expect(await screen.findByText('The planned hours fit the credits.')).toBeInTheDocument();
  });

  it('says so when a module has no credits to compare with', async () => {
    mocked.fetchModule.mockResolvedValue(
      moduleDetail({ hours: { ...hours('no_credits'), credits: null, expected_hours: null } })
    );
    await openModule();

    expect(
      await screen.findByText('No credits are set, so the planned hours cannot be compared.')
    ).toBeInTheDocument();
  });

  it('adds an assessment', async () => {
    mocked.createAssessment.mockResolvedValue({ ...exam, id: 'a2', name: 'OSCE station' });
    const section = await openModule();

    fireEvent.click(await within(section).findByRole('button', { name: 'Add assessment' }));
    const form = await screen.findByRole('dialog', { name: 'Add assessment' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Name/ }), {
      target: { value: '  OSCE station ' },
    });
    fireEvent.change(await within(form).findByRole('combobox', { name: 'Method' }), {
      target: { value: 'osce' },
    });
    fireEvent.change(within(form).getByRole('textbox', { name: /Weight/ }), {
      target: { value: '40' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add assessment' }));

    expect(await screen.findByText('Assessment OSCE station added.')).toBeInTheDocument();
    expect(mocked.createAssessment).toHaveBeenCalledWith('m2', {
      name: 'OSCE station',
      method_value_id: 'osce',
      weight: 40,
      timing: '',
      time_minutes: 0,
    });
  });

  it('asks for a name and a sensible weight before saving', async () => {
    const section = await openModule();

    fireEvent.click(await within(section).findByRole('button', { name: 'Add assessment' }));
    const form = await screen.findByRole('dialog', { name: 'Add assessment' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Weight/ }), {
      target: { value: '150' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add assessment' }));

    expect(await within(form).findByText('Fill in this field.')).toBeInTheDocument();
    expect(await within(form).findByText('Enter a number from 0 to 100.')).toBeInTheDocument();
    expect(mocked.createAssessment).not.toHaveBeenCalled();
  });

  it('adds an item linked to objectives of the module and its sessions', async () => {
    mocked.createAssessmentItem.mockResolvedValue(exam);
    const section = await openModule();

    fireEvent.click(
      await within(section).findByRole('button', { name: 'Add item to Final exam' })
    );
    const form = await screen.findByRole('dialog', { name: 'Add an item to Final exam' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Item/ }), {
      target: { value: 'Question 3' },
    });
    fireEvent.click(
      await within(form).findByRole('checkbox', { name: /Describe the cardiac cycle/ })
    );
    expect(within(form).getByText(/Cardiac cycle:/)).toBeInTheDocument();
    expect(within(form).getByText(/Module outcome:/)).toBeInTheDocument();
    fireEvent.click(within(form).getByRole('button', { name: 'Add item' }));

    expect(await screen.findByText('Item Question 3 added.')).toBeInTheDocument();
    expect(mocked.createAssessmentItem).toHaveBeenCalledWith('a1', {
      label: 'Question 3',
      marks: null,
      objective_ids: ['o-e1'],
    });
  });

  it('changes the objectives an item assesses', async () => {
    mocked.updateAssessmentItem.mockResolvedValue(exam);
    const section = await openModule();

    fireEvent.click(
      await within(section).findByRole('button', { name: 'Edit item Question 1' })
    );
    const form = await screen.findByRole('dialog', { name: 'Edit Question 1' });
    const linked = await within(form).findByRole('checkbox', { name: /Interpret cardiac tests/ });
    expect(linked).toBeChecked();
    fireEvent.click(linked);
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByText('Changes to item Question 1 saved.')).toBeInTheDocument();
    expect(mocked.updateAssessmentItem).toHaveBeenCalledWith('i1', {
      label: 'Question 1',
      marks: 10,
      objective_ids: [],
    });
  });

  it('deletes an assessment after confirmation', async () => {
    mocked.deleteAssessment.mockResolvedValue();
    const section = await openModule();

    fireEvent.click(
      await within(section).findByRole('button', { name: 'Delete assessment Final exam' })
    );
    const form = await screen.findByRole('dialog', { name: 'Delete Final exam?' });
    expect(within(form).getByText('This also deletes its items.')).toBeInTheDocument();
    fireEvent.click(within(form).getByRole('button', { name: 'Delete assessment' }));

    expect(await screen.findByText('Final exam deleted.')).toBeInTheDocument();
    expect(mocked.deleteAssessment).toHaveBeenCalledWith('a1');
  });

  it('says in plain words when a save is refused', async () => {
    mocked.createAssessment.mockRejectedValue(new ApiError(409, 'read only'));
    const section = await openModule();

    fireEvent.click(await within(section).findByRole('button', { name: 'Add assessment' }));
    const form = await screen.findByRole('dialog', { name: 'Add assessment' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Name/ }), {
      target: { value: 'Quiz' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add assessment' }));

    expect(await within(form).findByRole('alert')).toHaveTextContent(/can no longer be changed/);
  });
});

const creditCheck: VersionCreditCheck = {
  policy: {
    hours_per_credit: 10,
    tolerance_percent: 10,
    credits_per_year: 120,
    min_exit_level_credits: null,
  },
  modules: [
    hours('under'),
    {
      ...hours('ok'),
      module_id: 'm1',
      code: 'HSC101',
      name: 'Foundations',
      planned_hours: '120.0',
      expected_hours: '120.0',
      credits: '12.0',
      difference_percent: '0.0',
    },
    {
      ...hours('no_credits'),
      module_id: 'm3',
      code: 'HSC300',
      name: 'Research thread',
      credits: null,
      expected_hours: null,
      difference_percent: null,
      phase_id: null,
    },
  ],
  years: [
    {
      phase_id: 'y1',
      name: 'Year 1',
      kind: 'year',
      credits: '12.0',
      modules: 1,
      modules_without_credits: 0,
      expected_credits: 120,
      status: 'under',
    },
    {
      phase_id: 'y2',
      name: 'Year 2',
      kind: 'year',
      credits: '120.0',
      modules: 1,
      modules_without_credits: 1,
      expected_credits: 120,
      status: 'ok',
    },
  ],
  unphased_credits: '0.0',
  unphased_modules: 1,
  levels: [
    { level: 5, credits: '12.0', modules: 1 },
    { level: 6, credits: '16.0', modules: 1 },
    { level: null, credits: '0.0', modules: 1 },
  ],
  total_credits: '28.0',
  programme_total_credits: 360,
  qualification_name: "Bachelor's degree",
  qualification_min_credits: 360,
  exit_level_minimum: 120,
  exit_level: 7,
  findings: [
    { code: 'total_differs_from_programme', params: { total: '28', programme: 360 } },
    { code: 'above_exit_level', params: { level: 7, modules: 'HSC999' } },
  ],
};

describe('credits page', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('programme_director', ['curriculum.view'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchVersionStructure.mockResolvedValue(structure);
    mocked.fetchProgrammeOutcomes.mockResolvedValue([]);
    mocked.fetchCreditCheck.mockResolvedValue(creditCheck);
  });

  it('is offered from the version bar', async () => {
    renderAt('/curriculum/versions/v2027');

    const link = await screen.findByRole('link', { name: 'Check credits' });

    expect(link).toHaveAttribute('href', '/curriculum/versions/v2027/credits');
  });

  it('shows the totals, the findings, years, levels and every module', async () => {
    renderAt('/curriculum/versions/v2027/credits');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Credits and hours' })
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        'The modules add up to 28 credits, but the programme’s total is 360.'
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText('Modules above the programme’s exit level (NQF 7): HSC999.')
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /One credit is 10 notional hours\. Planned hours may differ from this by 10%/
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Check the qualification rules against the current CHE/)
    ).toBeInTheDocument();

    const years = screen.getByRole('region', { name: /Credits per year/ });
    expect(within(years).getByText('12 credits, below the typical 120.')).toBeInTheDocument();
    expect(within(years).getByText('120 credits, as expected.')).toBeInTheDocument();
    expect(within(years).getByText('1 module has no credits set.')).toBeInTheDocument();

    const levels = screen.getByRole('region', { name: 'Credits per NQF level' });
    expect(within(levels).getByText('No level set')).toBeInTheDocument();

    const modules = screen.getByRole('region', { name: /Planned hours per/ });
    expect(within(modules).getByText(/Planned 10 h against 160 h expected/)).toBeInTheDocument();
    expect(
      within(modules).getByText('No credits are set, so the planned hours cannot be compared.')
    ).toBeInTheDocument();
    expect(within(modules).getByRole('link', { name: /HSC101 Foundations/ })).toHaveAttribute(
      'href',
      '/curriculum/versions/v2027?item=module%3Am1'
    );
  });

  it('says when everything fits', async () => {
    mocked.fetchCreditCheck.mockResolvedValue({ ...creditCheck, findings: [] });
    renderAt('/curriculum/versions/v2027/credits');

    expect(
      await screen.findByText('The credits fit the programme and its qualification type.')
    ).toBeInTheDocument();
  });

  it('says so when the version has no modules', async () => {
    mocked.fetchCreditCheck.mockResolvedValue({ ...creditCheck, modules: [], years: [] });
    renderAt('/curriculum/versions/v2027/credits');

    expect(await screen.findByText('Nothing to check yet')).toBeInTheDocument();
  });

  it('shows not found for a version the user cannot see', async () => {
    mocked.fetchCreditCheck.mockRejectedValue(new ApiError(404, 'gone'));
    renderAt('/curriculum/versions/v2027/credits');

    expect(await screen.findByText("This curriculum version isn't available")).toBeInTheDocument();
  });

  it('offers a retry when the check cannot be loaded', async () => {
    mocked.fetchCreditCheck.mockRejectedValueOnce(new ApiError(500, 'oops'));
    mocked.fetchCreditCheck.mockResolvedValue(creditCheck);
    renderAt('/curriculum/versions/v2027/credits');

    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('Summary')).toBeInTheDocument();
  });
});
