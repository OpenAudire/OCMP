import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { LearningEventDetail, ModuleDetail, Objective, SavedObjective } from '../api/types';
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
  fetchLearningEvent: vi.fn(),
  fetchTaxonomyScales: vi.fn(),
  fetchModuleLinkOptions: vi.fn(),
  fetchEventLinkOptions: vi.fn(),
  createProgrammeOutcome: vi.fn(),
  createModuleOutcome: vi.fn(),
  createEventObjective: vi.fn(),
  updateObjective: vi.fn(),
  deleteObjective: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function objective(overrides: Partial<Objective> & Pick<Objective, 'id' | 'text'>): Objective {
  return {
    domain: null,
    taxonomy_level_id: null,
    status: 'draft',
    position: 0,
    parent_ids: [],
    ...overrides,
  };
}

function saved(base: Objective, level: SavedObjective['level']): SavedObjective {
  return { ...base, level };
}

const moduleDetail = (
  outcomes: Objective[],
  canEdit: boolean,
  canApprove = false
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
  outcomes,
  can_edit_objectives: canEdit,
  can_approve_objectives: canApprove,
});

const eventDetail = (
  objectives: Objective[],
  canEdit: boolean,
  canApprove = false
): LearningEventDetail => ({
  id: 'e1',
  module_id: 'm2',
  title: 'Cardiac cycle',
  format: 'Lecture',
  format_value_id: 'f-lecture',
  contact_minutes: 90,
  self_study_minutes: 120,
  week: 4,
  position: 0,
  description: '',
  external_lms_ref: null,
  objectives,
  can_edit_objectives: canEdit,
  can_approve_objectives: canApprove,
});

const options = [
  { id: 'p1', level: 'programme' as const, text: 'Practise safely.', module_code: null },
  { id: 'o-m2', level: 'module' as const, text: 'Interpret cardiac tests.', module_code: 'HSC201' },
];

async function tree() {
  return screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
}

describe('objective editor', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([
      role('programme_director', ['curriculum.view', 'objectives.edit']),
    ]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchProgramme.mockRejectedValue(new ApiError(500, 'not needed'));
    mocked.fetchVersionStructure.mockResolvedValue({ ...structure, can_edit_outcomes: true });
    mocked.fetchProgrammeOutcomes.mockResolvedValue([
      objective({ id: 'p1', text: 'Practise safely.' }),
    ]);
    mocked.fetchModule.mockResolvedValue(
      moduleDetail([objective({ id: 'o-m2', text: 'Interpret cardiac tests.' })], true)
    );
    mocked.fetchLearningEvent.mockResolvedValue(
      eventDetail(
        [
          objective({
            id: 'o-e1',
            text: 'Describe the cardiac cycle.',
            domain: 'knowledge',
            taxonomy_level_id: 'l-remember',
            parent_ids: ['o-m2', 'hidden'],
          }),
        ],
        true
      )
    );
    mocked.fetchTaxonomyScales.mockResolvedValue([
      {
        key: 'bloom',
        name: 'Bloom',
        description: '',
        levels: [
          { id: 'l-remember', name: 'Remember', position: 0, description: '' },
          { id: 'l-apply', name: 'Apply', position: 1, description: '' },
        ],
      },
    ]);
    mocked.fetchModuleLinkOptions.mockResolvedValue([options[0]]);
    mocked.fetchEventLinkOptions.mockResolvedValue(options);
  });

  it('shows no buttons to people who cannot edit objectives', async () => {
    mocked.fetchVersionStructure.mockResolvedValue(structure);
    mocked.fetchLearningEvent.mockResolvedValue(
      eventDetail([objective({ id: 'o-e1', text: 'Describe the cardiac cycle.' })], false)
    );

    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    expect(await screen.findByText('Describe the cardiac cycle.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /objective/i })).not.toBeInTheDocument();
  });

  it('shows the domain, taxonomy level and links of an objective', async () => {
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    const row = (await screen.findByText('Describe the cardiac cycle.')).closest('li')!;
    const list = within(row);
    expect(await list.findByText('Bloom: Remember')).toBeInTheDocument();
    expect(list.getByText('Knowledge')).toBeInTheDocument();
    expect(list.getByText('Linked to 2 broader outcomes')).toBeInTheDocument();
  });

  it('adds a session objective with domain, taxonomy level and upward links', async () => {
    mocked.createEventObjective.mockResolvedValue(
      saved(objective({ id: 'new', text: 'Draw the cycle.' }), 'learning_event')
    );
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add objective' }));
    const form = await screen.findByRole('dialog', { name: 'Add objective' });
    fireEvent.click(within(form).getByRole('button', { name: 'Add objective' }));
    expect(await within(form).findByText('Fill in this field.')).toBeInTheDocument();
    expect(mocked.createEventObjective).not.toHaveBeenCalled();

    fireEvent.change(within(form).getByRole('textbox', { name: /Wording/ }), {
      target: { value: '  Draw the cycle. ' },
    });
    fireEvent.change(within(form).getByRole('combobox', { name: 'Domain' }), {
      target: { value: 'skill' },
    });
    fireEvent.change(await within(form).findByRole('combobox', { name: 'Taxonomy level' }), {
      target: { value: 'l-apply' },
    });
    fireEvent.click(await within(form).findByRole('checkbox', { name: /Interpret cardiac tests/ }));
    fireEvent.click(within(form).getByRole('checkbox', { name: /Practise safely/ }));
    fireEvent.click(within(form).getByRole('button', { name: 'Add objective' }));

    expect(await screen.findByRole('status')).toHaveTextContent('The objective was added.');
    expect(mocked.createEventObjective).toHaveBeenCalledWith('e1', {
      text: 'Draw the cycle.',
      domain: 'skill',
      taxonomy_level_id: 'l-apply',
      status: 'draft',
      parent_ids: ['o-m2', 'p1'],
    });
  });

  it('changes an objective and leaves links the user cannot see alone', async () => {
    mocked.updateObjective.mockResolvedValue(
      saved(objective({ id: 'o-e1', text: 'Explain the cardiac cycle.' }), 'learning_event')
    );
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit objective: Describe the cardiac cycle.' })
    );
    const form = await screen.findByRole('dialog', { name: 'Edit objective' });
    const text = within(form).getByRole('textbox', { name: /Wording/ });
    expect(text).toHaveValue('Describe the cardiac cycle.');
    expect(within(form).getByRole('combobox', { name: 'Domain' })).toHaveValue('knowledge');
    expect(
      await within(form).findByRole('checkbox', { name: /Interpret cardiac tests/ })
    ).toBeChecked();
    expect(within(form).getByText(/also contributes to 1 outcome you cannot see/)).toBeInTheDocument();

    fireEvent.change(text, { target: { value: 'Explain the cardiac cycle.' } });
    fireEvent.change(within(form).getByRole('combobox', { name: 'Status' }), {
      target: { value: 'ready_for_review' },
    });
    fireEvent.click(within(form).getByRole('checkbox', { name: /Interpret cardiac tests/ }));
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Changes to the objective saved.'
    );
    // The link on offer was unticked; the hidden one was not sent, so it stays.
    expect(mocked.updateObjective).toHaveBeenCalledWith('o-e1', {
      text: 'Explain the cardiac cycle.',
      domain: 'knowledge',
      taxonomy_level_id: 'l-remember',
      status: 'ready_for_review',
      parent_ids: [],
    });
  });

  it('says why nothing can be linked when no broader outcome is visible', async () => {
    mocked.fetchEventLinkOptions.mockResolvedValue([]);
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add objective' }));
    const form = await screen.findByRole('dialog', { name: 'Add objective' });

    expect(
      await within(form).findByText('There are no broader outcomes you can link to.')
    ).toBeInTheDocument();
    expect(within(form).queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('shows a failed save and keeps the dialog open', async () => {
    mocked.createEventObjective.mockRejectedValue(new ApiError(409, 'read-only'));
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add objective' }));
    const form = await screen.findByRole('dialog', { name: 'Add objective' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Wording/ }), {
      target: { value: 'Something.' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add objective' }));

    expect(await within(form).findByText(/can no longer be changed/)).toBeInTheDocument();
  });

  it('adds a module outcome that links only to the programme outcomes on offer', async () => {
    mocked.createModuleOutcome.mockResolvedValue(
      saved(objective({ id: 'new', text: 'Explain haemodynamics.' }), 'module')
    );
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add outcome' }));
    const form = await screen.findByRole('dialog', { name: 'Add outcome' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Wording/ }), {
      target: { value: 'Explain haemodynamics.' },
    });
    expect(await within(form).findAllByRole('checkbox')).toHaveLength(1);
    fireEvent.click(within(form).getByRole('checkbox', { name: /Practise safely/ }));
    fireEvent.click(within(form).getByRole('button', { name: 'Add outcome' }));

    expect(await screen.findByRole('status')).toHaveTextContent('The outcome was added.');
    expect(mocked.createModuleOutcome).toHaveBeenCalledWith('m2', {
      text: 'Explain haemodynamics.',
      domain: null,
      taxonomy_level_id: null,
      status: 'draft',
      parent_ids: ['p1'],
    });
  });

  it('adds a programme outcome without upward links', async () => {
    mocked.createProgrammeOutcome.mockResolvedValue(
      saved(objective({ id: 'new', text: 'Communicate.' }), 'programme')
    );
    renderAt('/curriculum/versions/v2027');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add outcome' }));
    const form = await screen.findByRole('dialog', { name: 'Add outcome' });
    fireEvent.change(within(form).getByRole('textbox', { name: /Wording/ }), {
      target: { value: 'Communicate.' },
    });
    expect(within(form).queryByRole('checkbox')).not.toBeInTheDocument();
    fireEvent.click(within(form).getByRole('button', { name: 'Add outcome' }));

    expect(await screen.findByRole('status')).toHaveTextContent('The outcome was added.');
    expect(mocked.createProgrammeOutcome).toHaveBeenCalledWith('v2027', {
      text: 'Communicate.',
      domain: null,
      taxonomy_level_id: null,
      status: 'draft',
      parent_ids: [],
    });
  });

  it('offers draft and ready for review to people who cannot approve', async () => {
    mocked.createEventObjective.mockResolvedValue(
      saved(objective({ id: 'new', text: 'Draw the cycle.' }), 'learning_event')
    );
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add objective' }));
    const form = await screen.findByRole('dialog', { name: 'Add objective' });
    const status = within(form).getByRole('combobox', { name: 'Status' });
    expect(within(status).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Draft',
      'Ready for review',
    ]);
    fireEvent.change(within(form).getByRole('textbox', { name: /Wording/ }), {
      target: { value: 'Draw the cycle.' },
    });
    fireEvent.change(status, { target: { value: 'ready_for_review' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Add objective' }));

    expect(await screen.findByRole('status')).toHaveTextContent('The objective was added.');
    expect(mocked.createEventObjective).toHaveBeenCalledWith(
      'e1',
      expect.objectContaining({ status: 'ready_for_review' })
    );
  });

  it('offers every status to people who can approve', async () => {
    mocked.fetchLearningEvent.mockResolvedValue(
      eventDetail([objective({ id: 'o-e1', text: 'Describe the cardiac cycle.' })], true, true)
    );
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add objective' }));
    const form = await screen.findByRole('dialog', { name: 'Add objective' });
    const status = within(form).getByRole('combobox', { name: 'Status' });

    expect(within(status).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Draft',
      'Ready for review',
      'Approved',
      'Retired',
    ]);
  });

  it('locks the status of an approved objective for people who cannot approve', async () => {
    mocked.fetchLearningEvent.mockResolvedValue(
      eventDetail(
        [objective({ id: 'o-e1', text: 'Describe the cardiac cycle.', status: 'approved' })],
        true
      )
    );
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: /Edit objective: Describe/ }));
    const form = await screen.findByRole('dialog', { name: 'Edit objective' });
    const status = within(form).getByRole('combobox', { name: 'Status' });

    expect(status).toBeDisabled();
    expect(status).toHaveValue('approved');
    expect(form).toHaveTextContent('goes back to ready for review');
  });

  it('flags objectives whose accepted mappings need a re-check', async () => {
    mocked.fetchLearningEvent.mockResolvedValue(
      eventDetail(
        [objective({ id: 'o-e1', text: 'Describe the cardiac cycle.', mappings_to_recheck: 2 })],
        false
      )
    );
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    const row = (await screen.findByText('Describe the cardiac cycle.')).closest('li')!;

    expect(within(row).getByText('2 mappings need re-check')).toBeInTheDocument();
  });

  it('deletes an objective after confirming and moves focus to the confirmation', async () => {
    mocked.deleteObjective.mockResolvedValue(undefined);
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete objective: Describe the cardiac cycle.' })
    );
    const form = await screen.findByRole('dialog', { name: 'Delete this objective?' });
    expect(within(form).getByText('Describe the cardiac cycle.')).toBeInTheDocument();
    mocked.fetchLearningEvent.mockResolvedValue(eventDetail([], true));
    fireEvent.click(within(form).getByRole('button', { name: 'Delete objective' }));

    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('The objective was deleted.');
    expect(mocked.deleteObjective).toHaveBeenCalledWith('o-e1');
    expect(await screen.findByText('No learning objectives yet.')).toBeInTheDocument();
  });

  it('uses the institution wording for objectives', async () => {
    mocked.fetchInstitution.mockResolvedValue({
      ...testInstitution,
      terminology: {
        ...testInstitution.terminology,
        objective: { singular: 'Learning outcome', plural: 'Learning outcomes' },
      },
    });
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    expect(
      await screen.findByRole('button', { name: 'Add learning outcome' })
    ).toBeInTheDocument();
  });
});
