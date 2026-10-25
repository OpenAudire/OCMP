import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { StructureModule, VersionStructure } from '../api/types';
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
  fetchTeachingFormats: vi.fn(),
  createPhase: vi.fn(),
  updatePhase: vi.fn(),
  deletePhase: vi.fn(),
  createModule: vi.fn(),
  updateModule: vi.fn(),
  deleteModule: vi.fn(),
  createLearningEvent: vi.fn(),
  updateLearningEvent: vi.fn(),
  deleteLearningEvent: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

/** The test structure as a programme director sees it: everything can be edited. */
function editable(base: VersionStructure = structure): VersionStructure {
  const open = (module: StructureModule): StructureModule => ({
    ...module,
    can_edit: true,
    events: module.events.map((event) => ({ ...event, can_edit: true })),
  });
  return {
    ...base,
    can_edit: true,
    phases: base.phases.map((phase) => ({ ...phase, modules: phase.modules.map(open) })),
    modules_without_phase: base.modules_without_phase.map(open),
  };
}

/** As a module coordinator of HSC201 sees it: only that module, editable. */
function coordinatorView(): VersionStructure {
  const own = { ...editable().phases[1].modules[0] };
  return {
    ...structure,
    partial: true,
    outcome_count: null,
    phases: [{ ...structure.phases[1], modules: [own] }],
    modules_without_phase: [],
  };
}

async function tree() {
  return screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
}

function dialog(name: string | RegExp) {
  return screen.findByRole('dialog', { name });
}

describe('curriculum builder editing', () => {
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
    mocked.fetchProgrammeOutcomes.mockResolvedValue([]);
    mocked.fetchVersionStructure.mockResolvedValue(editable());
    mocked.fetchTeachingFormats.mockResolvedValue([
      { id: 'f-lecture', label: 'Lecture', list_name: 'Teaching methods' },
      { id: 'f-pbl', label: 'PBL tutorial', list_name: 'Teaching methods' },
    ]);
    mocked.fetchModule.mockResolvedValue({
      id: 'm2',
      version_id: 'v2027',
      phase_id: 'y2',
      code: 'HSC201',
      name: 'Cardiovascular system',
      credits: '16.0',
      nqf_level: 6,
      description: 'Heart and circulation.',
      external_lms_ref: null,
      event_count: 2,
      contact_minutes: 210,
      self_study_minutes: 210,
      outcomes: [],
    });
    mocked.fetchLearningEvent.mockResolvedValue({
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
      objectives: [],
    });
  });

  it('shows no editing buttons to people who cannot edit', async () => {
    mocked.fetchVersionStructure.mockResolvedValue(structure);

    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    expect(await screen.findByText('Heart and circulation.')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Changes' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Edit/ })).not.toBeInTheDocument();
  });

  it('adds a phase and selects it', async () => {
    const added = {
      id: 'y3',
      version_id: 'v2027',
      name: 'Year 3',
      kind: 'block' as const,
      position: 2,
    };
    mocked.createPhase.mockResolvedValue(added);
    renderAt('/curriculum/versions/v2027');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add phase' }));
    const form = await dialog('Add phase');
    fireEvent.click(within(form).getByRole('button', { name: 'Add phase' }));
    expect(await within(form).findByText('Fill in this field.')).toBeInTheDocument();
    expect(mocked.createPhase).not.toHaveBeenCalled();

    // The structure the builder fetches after the change includes the new phase.
    mocked.fetchVersionStructure.mockResolvedValue(
      editable({ ...structure, phases: [...structure.phases, { ...added, modules: [] }] })
    );
    fireEvent.change(within(form).getByRole('textbox', { name: /Name/ }), {
      target: { value: ' Year 3 ' },
    });
    fireEvent.change(within(form).getByRole('combobox', { name: 'Kind' }), {
      target: { value: 'block' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add phase' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Year 3 added.');
    expect(mocked.createPhase).toHaveBeenCalledWith('v2027', { name: 'Year 3', kind: 'block' });
    const structureTree = await tree();
    // The address changes in a transition, so the selection follows a moment later.
    await waitFor(() =>
      expect(within(structureTree).getByRole('treeitem', { name: /Year 3/ })).toHaveAttribute(
        'aria-selected',
        'true'
      )
    );
  });

  it('changes a module, including its phase, in the institution wording', async () => {
    mocked.updateModule.mockResolvedValue({
      id: 'm2',
      version_id: 'v2027',
      phase_id: 'y1',
      code: 'HSC201',
      name: 'Cardiology',
      credits: '16.0',
      nqf_level: 6,
      description: 'Heart and circulation.',
      external_lms_ref: null,
      position: 1,
    });
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit course' }));
    const form = await dialog('Edit HSC201 Cardiovascular system');
    const name = await within(form).findByRole('textbox', { name: /Name/ });
    expect(name).toHaveValue('Cardiovascular system');
    fireEvent.change(name, { target: { value: 'Cardiology' } });
    fireEvent.change(within(form).getByRole('combobox', { name: 'Phase' }), {
      target: { value: 'y1' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Changes to HSC201 Cardiology saved.'
    );
    expect(mocked.updateModule).toHaveBeenCalledWith('m2', {
      code: 'HSC201',
      name: 'Cardiology',
      phase_id: 'y1',
      credits: '16',
      nqf_level: 6,
      description: 'Heart and circulation.',
      external_lms_ref: null,
    });
  });

  it('says when a module code is already used', async () => {
    mocked.createModule.mockRejectedValue(new ApiError(409, 'taken'));
    renderAt('/curriculum/versions/v2027?item=phase:y2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add course' }));
    const form = await dialog('Add course');
    expect(within(form).getByRole('combobox', { name: 'Phase' })).toHaveValue('y2');
    fireEvent.change(within(form).getByRole('textbox', { name: /Code/ }), {
      target: { value: 'HSC101' },
    });
    fireEvent.change(within(form).getByRole('textbox', { name: /Name/ }), {
      target: { value: 'Duplicate' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add course' }));

    expect(await within(form).findByRole('alert')).toHaveTextContent(
      'Another course in this version already uses this code.'
    );
    expect(mocked.createModule).toHaveBeenCalledWith(
      'v2027',
      expect.objectContaining({ code: 'HSC101', phase_id: 'y2', credits: null })
    );
  });

  it('lets a module coordinator change their module but not move or delete it', async () => {
    mocked.fetchVersionStructure.mockResolvedValue(coordinatorView());
    mocked.updateModule.mockResolvedValue({
      id: 'm2',
      version_id: 'v2027',
      phase_id: 'y2',
      code: 'HSC201',
      name: 'Cardiovascular system',
      credits: '16.0',
      nqf_level: 6,
      description: 'Heart and circulation.',
      external_lms_ref: 'LMS-201',
      position: 1,
    });
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    expect(await screen.findByRole('button', { name: 'Add session' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete course' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit course' }));
    const form = await dialog('Edit HSC201 Cardiovascular system');
    await within(form).findByRole('textbox', { name: /Name/ });
    expect(within(form).queryByRole('combobox', { name: 'Phase' })).not.toBeInTheDocument();
    fireEvent.change(within(form).getByRole('textbox', { name: /LMS reference/ }), {
      target: { value: 'LMS-201' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(mocked.updateModule).toHaveBeenCalled());
    expect(mocked.updateModule.mock.calls[0][1]).not.toHaveProperty('phase_id');
    expect(mocked.updateModule.mock.calls[0][1]).toMatchObject({ external_lms_ref: 'LMS-201' });
  });

  it('adds a session with a teaching format', async () => {
    mocked.createLearningEvent.mockResolvedValue({
      id: 'e9',
      module_id: 'm2',
      title: 'Heart sounds',
      format_value_id: 'f-pbl',
      contact_minutes: 60,
      self_study_minutes: 0,
      week: null,
      position: 2,
      description: '',
      external_lms_ref: null,
    });
    renderAt('/curriculum/versions/v2027?item=module:m2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Add session' }));
    const form = await dialog('Add session to HSC201');
    fireEvent.change(within(form).getByRole('textbox', { name: /Title/ }), {
      target: { value: 'Heart sounds' },
    });
    const format = within(form).getByRole('combobox', { name: 'Format' });
    await within(format).findByRole('option', { name: 'PBL tutorial' });
    fireEvent.change(format, { target: { value: 'f-pbl' } });
    fireEvent.change(within(form).getByRole('textbox', { name: 'Contact time (minutes)' }), {
      target: { value: '60' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add session' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Heart sounds added.');
    expect(mocked.createLearningEvent).toHaveBeenCalledWith('m2', {
      title: 'Heart sounds',
      format_value_id: 'f-pbl',
      contact_minutes: 60,
      self_study_minutes: 0,
      week: null,
      description: '',
      external_lms_ref: null,
    });
  });

  it('deletes a session after saying what goes with it', async () => {
    mocked.deleteLearningEvent.mockResolvedValue();
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Delete session' }));
    const form = await dialog('Delete Cardiac cycle?');
    expect(within(form).getByText('This also deletes its 1 objective.')).toBeInTheDocument();
    fireEvent.click(within(form).getByRole('button', { name: 'Delete session' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Cardiac cycle deleted.');
    expect(mocked.deleteLearningEvent).toHaveBeenCalledWith('e1');
    // The selection moves to the session's module.
    const structureTree = await tree();
    await waitFor(() =>
      expect(within(structureTree).getByRole('treeitem', { name: /HSC201/ })).toHaveAttribute(
        'aria-selected',
        'true'
      )
    );
  });

  it('explains that a phase with modules cannot be deleted', async () => {
    renderAt('/curriculum/versions/v2027?item=phase:y2');
    await tree();

    fireEvent.click(await screen.findByRole('button', { name: 'Delete phase' }));
    const form = await dialog('Delete Year 2?');
    expect(
      within(form).getByText(
        'This phase still holds 1 course. Move them to another phase or delete them first.'
      )
    ).toBeInTheDocument();
    expect(within(form).queryByRole('button', { name: 'Delete phase' })).not.toBeInTheDocument();
    // The dialog's own close button (top) and the one under the message.
    const [, closeButton] = within(form).getAllByRole('button', { name: 'Close' });
    fireEvent.click(closeButton);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mocked.deletePhase).not.toHaveBeenCalled();
  });

  it('shows the builder with its buttons for an empty version people may edit', async () => {
    mocked.fetchVersionStructure.mockResolvedValue({
      ...editable(),
      phases: [],
      modules_without_phase: [],
    });

    renderAt('/curriculum/versions/v2027');
    await tree();

    expect(screen.getByRole('button', { name: 'Add phase' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add course' })).toBeInTheDocument();
    expect(screen.queryByText('No courses yet')).not.toBeInTheDocument();
  });
});
