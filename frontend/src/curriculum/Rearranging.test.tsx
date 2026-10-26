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
  movePhase: vi.fn(),
  moveModule: vi.fn(),
  moveLearningEvent: vi.fn(),
  copyPhase: vi.fn(),
  copyModule: vi.fn(),
  copyLearningEvent: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

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

function treeItem(name: RegExp) {
  return screen.findByRole('treeitem', { name });
}

function changes() {
  return screen.findByRole('group', { name: 'Changes' });
}

describe('reordering and copying in the curriculum builder', () => {
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
    mocked.fetchModule.mockRejectedValue(new ApiError(500, 'not needed'));
    mocked.fetchLearningEvent.mockRejectedValue(new ApiError(500, 'not needed'));
    mocked.fetchVersionStructure.mockResolvedValue(editable());
  });

  it('moves a session up with the button and confirms the new place', async () => {
    mocked.moveLearningEvent.mockResolvedValue({} as never);

    renderAt('/curriculum/versions/v2027?item=event:e2');
    const group = await changes();
    const up = within(group).getByRole('button', { name: 'Move up' });
    expect(within(group).getByRole('button', { name: 'Move down' })).toBeDisabled();
    expect(screen.getByText(/drag an item in the tree/)).toBeInTheDocument();

    fireEvent.click(up);

    await waitFor(() => expect(mocked.moveLearningEvent).toHaveBeenCalledWith('e2', 0));
    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('ECG interpretation workshop moved to place 1 of 2.');
    // Move up is now unavailable, so focus goes to the confirmation.
    await waitFor(() => expect(notice.parentElement).toHaveFocus());
    expect(mocked.fetchVersionStructure).toHaveBeenCalledTimes(2);
  });

  it('keeps focus on the button while it can still be used', async () => {
    const base = editable();
    const year3 = { id: 'y3', name: 'Year 3', kind: 'year' as const, position: 2, modules: [] };
    mocked.fetchVersionStructure.mockResolvedValue({ ...base, phases: [...base.phases, year3] });
    mocked.movePhase.mockResolvedValue({} as never);

    renderAt('/curriculum/versions/v2027?item=phase:y1');
    const group = await changes();
    expect(within(group).getByRole('button', { name: 'Move up' })).toBeDisabled();
    const down = within(group).getByRole('button', { name: 'Move down' });
    down.focus();
    fireEvent.click(down);

    await waitFor(() => expect(mocked.movePhase).toHaveBeenCalledWith('y1', 1));
    expect(await screen.findByRole('status')).toHaveTextContent('Year 1 moved to place 2 of 3.');
    expect(down).toHaveFocus();
  });

  it('shows a failed move', async () => {
    mocked.moveModule.mockRejectedValue(new ApiError(409, 'read-only'));
    const base = editable();
    const second = { ...base.phases[1].modules[0], id: 'm4', code: 'HSC202', events: [] };
    mocked.fetchVersionStructure.mockResolvedValue({
      ...base,
      phases: [base.phases[0], { ...base.phases[1], modules: [...base.phases[1].modules, second] }],
    });

    renderAt('/curriculum/versions/v2027?item=module:m4');
    fireEvent.click(within(await changes()).getByRole('button', { name: 'Move up' }));

    expect(
      await screen.findByText(
        'This could not be saved because the version can no longer be changed. Only draft versions can be changed; reload the page.'
      )
    ).toBeInTheDocument();
    expect(mocked.moveModule).toHaveBeenCalledWith('m4', 0);
  });

  it('moves a session by dragging it onto a sibling', async () => {
    mocked.moveLearningEvent.mockResolvedValue({} as never);

    renderAt('/curriculum/versions/v2027?item=module:m2');
    const workshop = await treeItem(/ECG interpretation workshop/);
    const lecture = await treeItem(/Cardiac cycle/);
    const phase = await treeItem(/^Year 1/);
    expect(workshop).toHaveAttribute('draggable', 'true');
    const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' };

    fireEvent.dragStart(workshop, { dataTransfer });
    // Not a sibling: no drop allowed.
    fireEvent.dragOver(phase, { dataTransfer });
    expect(phase).not.toHaveAttribute('data-drop');
    fireEvent.dragOver(lecture, { dataTransfer });
    expect(lecture).toHaveAttribute('data-drop', 'before');
    fireEvent.drop(lecture, { dataTransfer });

    await waitFor(() => expect(mocked.moveLearningEvent).toHaveBeenCalledWith('e2', 0));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'ECG interpretation workshop moved to place 1 of 2.'
    );
  });

  it('offers no moving or copying without edit rights', async () => {
    mocked.fetchVersionStructure.mockResolvedValue(structure);

    renderAt('/curriculum/versions/v2027?item=event:e2');
    const workshop = await treeItem(/ECG interpretation workshop/);

    expect(workshop).not.toHaveAttribute('draggable');
    expect(screen.queryByRole('button', { name: 'Move up' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Copy/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/drag an item in the tree/)).not.toBeInTheDocument();
  });

  it('lets a module coordinator rearrange sessions but not the module', async () => {
    mocked.fetchVersionStructure.mockResolvedValue(coordinatorView());

    renderAt('/curriculum/versions/v2027?item=module:m2');
    const group = await changes();
    expect(within(group).queryByRole('button', { name: 'Move up' })).not.toBeInTheDocument();
    expect(within(group).queryByRole('button', { name: 'Copy course' })).not.toBeInTheDocument();
    expect(await treeItem(/^HSC201/)).not.toHaveAttribute('draggable');
    expect(await treeItem(/Cardiac cycle/)).toHaveAttribute('draggable', 'true');

    fireEvent.click(await treeItem(/Cardiac cycle/));
    expect(
      await within(await changes()).findByRole('button', { name: 'Copy session' })
    ).toBeInTheDocument();
  });

  it('copies a session after it and selects the copy', async () => {
    const copy = { ...editable().phases[1].modules[0].events[0], id: 'e9' };
    copy.title = 'Cardiac cycle (copy)';
    mocked.copyLearningEvent.mockResolvedValue({
      ...copy,
      module_id: 'm2',
      description: '',
      external_lms_ref: null,
    });

    renderAt('/curriculum/versions/v2027?item=event:e1');
    fireEvent.click(within(await changes()).getByRole('button', { name: 'Copy session' }));
    const dialog = await screen.findByRole('dialog', { name: 'Copy Cardiac cycle' });
    expect(within(dialog).getByText(/with its objectives and tags/)).toBeInTheDocument();
    const title = within(dialog).getByRole('textbox', { name: /Title/ });
    expect(title).toHaveValue('Cardiac cycle (copy)');

    const base = editable();
    const cardio = base.phases[1].modules[0];
    mocked.fetchVersionStructure.mockResolvedValue({
      ...base,
      phases: [
        base.phases[0],
        {
          ...base.phases[1],
          modules: [{ ...cardio, events: [cardio.events[0], copy, cardio.events[1]] }],
        },
      ],
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Copy session' }));

    await waitFor(() =>
      expect(mocked.copyLearningEvent).toHaveBeenCalledWith('e1', 'Cardiac cycle (copy)')
    );
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Cardiac cycle (copy) added as a copy.'
    );
    // The address changes in a transition, so the selection follows a moment later.
    const copied = await treeItem(/Cardiac cycle \(copy\)/);
    await waitFor(() => expect(copied).toHaveAttribute('aria-selected', 'true'));
  });

  it('copies a module under a new code, explaining a code that is taken', async () => {
    mocked.copyModule.mockRejectedValueOnce(new ApiError(409, 'taken'));
    mocked.copyModule.mockResolvedValueOnce({
      id: 'm9',
      version_id: 'v2027',
      phase_id: null,
      code: 'HSC209',
      name: 'Cardiovascular system (copy)',
      credits: '16.0',
      nqf_level: 5,
      description: '',
      external_lms_ref: null,
      position: 4,
    });

    renderAt('/curriculum/versions/v2027?item=module:m2');
    // The only course in its phase: nothing to move it among.
    const group = await changes();
    expect(within(group).queryByRole('button', { name: 'Move up' })).not.toBeInTheDocument();
    expect(await treeItem(/^HSC201/)).not.toHaveAttribute('draggable');
    fireEvent.click(within(group).getByRole('button', { name: 'Copy course' }));
    const dialog = await screen.findByRole('dialog', { name: 'Copy HSC201 Cardiovascular system' });
    const submit = within(dialog).getByRole('button', { name: 'Copy course' });

    fireEvent.click(submit);
    expect(await within(dialog).findByText('Fill in this field.')).toBeInTheDocument();
    expect(mocked.copyModule).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByRole('textbox', { name: /Code/ }), {
      target: { value: 'HSC101' },
    });
    expect(within(dialog).getByRole('combobox', { name: 'Phase' })).toHaveValue('y2');
    fireEvent.click(submit);
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Another course in this version already uses this code.'
    );

    fireEvent.change(within(dialog).getByRole('textbox', { name: /Code/ }), {
      target: { value: ' HSC209 ' },
    });
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Phase' }), {
      target: { value: '' },
    });
    fireEvent.click(submit);

    await waitFor(() =>
      expect(mocked.copyModule).toHaveBeenLastCalledWith('m2', {
        code: 'HSC209',
        name: 'Cardiovascular system (copy)',
        phase_id: null,
      })
    );
  });

  it('asks for a different new code for each module of a copied phase', async () => {
    const base = editable();
    const second = { ...base.phases[1].modules[0], id: 'm4', code: 'HSC202', name: 'Lungs' };
    mocked.fetchVersionStructure.mockResolvedValue({
      ...base,
      phases: [base.phases[0], { ...base.phases[1], modules: [...base.phases[1].modules, second] }],
    });
    mocked.copyPhase.mockResolvedValue({
      id: 'y9',
      version_id: 'v2027',
      name: 'Year 2 (copy)',
      kind: 'year',
      position: 2,
    });

    renderAt('/curriculum/versions/v2027?item=phase:y2');
    fireEvent.click(within(await changes()).getByRole('button', { name: 'Copy phase' }));
    const dialog = await screen.findByRole('dialog', { name: 'Copy Year 2' });
    const first = within(dialog).getByRole('textbox', {
      name: /New code for HSC201 Cardiovascular system/,
    });
    const other = within(dialog).getByRole('textbox', { name: /New code for HSC202 Lungs/ });
    fireEvent.change(first, { target: { value: 'X1' } });
    fireEvent.change(other, { target: { value: 'x1' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Copy phase' }));

    expect(await within(dialog).findByText('Use a different code for each copy.')).toBeVisible();
    expect(mocked.copyPhase).not.toHaveBeenCalled();

    fireEvent.change(other, { target: { value: 'X2' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Copy phase' }));

    await waitFor(() =>
      expect(mocked.copyPhase).toHaveBeenCalledWith('y2', {
        name: 'Year 2 (copy)',
        module_codes: { m2: 'X1', m4: 'X2' },
      })
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Year 2 (copy) added as a copy.');
  });
});
