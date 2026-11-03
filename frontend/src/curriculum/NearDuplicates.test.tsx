import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { LearningEventDetail, NearDuplicate, NearDuplicates, Objective } from '../api/types';
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
  fetchLearningEvent: vi.fn(),
  fetchTaxonomyScales: vi.fn(),
  fetchNearDuplicates: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function objective(id: string, text: string): Objective {
  return { id, text, domain: null, taxonomy_level_id: null, status: 'draft', position: 0, parent_ids: [] };
}

const eventDetail = (objectives: Objective[], canEdit: boolean): LearningEventDetail => ({
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
  can_approve_objectives: false,
});

function match(overrides: Partial<NearDuplicate> = {}): NearDuplicate {
  return {
    objective_id: 'other',
    percent: 96,
    level: 'learning_event',
    text: 'Outline the phases of the cardiac cycle.',
    module_id: 'm2',
    module_code: 'HSC103',
    event_id: 'e9',
    event_title: 'Lecture 9',
    ...overrides,
  };
}

const found = (matches: NearDuplicate[]): NearDuplicates => ({
  version_id: 'v2027',
  enabled: true,
  threshold_percent: 95,
  objectives: matches.length > 0 ? [{ objective_id: 'o-e1', matches }] : [],
});

async function open() {
  renderAt('/curriculum/versions/v2027?item=event:e1');
  await screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
  return (await screen.findByText('Describe the cardiac cycle.')).closest('li')!;
}

describe('near-duplicates on the objective card', () => {
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
    mocked.fetchTaxonomyScales.mockResolvedValue([]);
    mocked.fetchLearningEvent.mockResolvedValue(
      eventDetail(
        [objective('o-e1', 'Describe the cardiac cycle.'), objective('o-e2', 'Name the valves.')],
        true
      )
    );
    mocked.fetchNearDuplicates.mockResolvedValue(found([match()]));
  });

  it('flags the objective with where the other one is and how similar', async () => {
    const card = await open();

    const flag = await within(card).findByRole('group', { name: 'Near-duplicate' });
    expect(flag).toHaveTextContent(
      'Near-duplicate of an objective in HSC103, Lecture 9 (96% similar). Repeat on purpose, or remove?'
    );
    // The other objective on the page is not flagged.
    const other = screen.getByText('Name the valves.').closest('li')!;
    expect(within(other).queryByRole('group', { name: 'Near-duplicate' })).not.toBeInTheDocument();
    expect(mocked.fetchNearDuplicates).toHaveBeenCalledWith('v2027');
  });

  it('says how many others when there are several', async () => {
    mocked.fetchNearDuplicates.mockResolvedValue(
      found([match(), match({ objective_id: 'x2', percent: 95 }), match({ objective_id: 'x3' })])
    );

    const card = await open();

    expect(await within(card).findByText(/and 2 others\./)).toBeInTheDocument();
  });

  it('compares the wordings in a dialog that can be closed', async () => {
    mocked.fetchNearDuplicates.mockResolvedValue(
      found([match(), match({ objective_id: 'x2', percent: 95, level: 'module', text: 'Interpret an ECG.' })])
    );
    const card = await open();

    fireEvent.click(await within(card).findByRole('button', { name: 'Compare' }));

    const dialog = await screen.findByRole('dialog', { name: 'Compare the wording' });
    const own = within(dialog).getByRole('region', { name: 'This objective' });
    expect(own).toHaveTextContent('Describe the cardiac cycle.');
    expect(
      within(dialog).getByRole('region', { name: 'HSC103, Lecture 9' })
    ).toHaveTextContent('HSC103, Lecture 9 (96% similar)Outline the phases of the cardiac cycle.');
    expect(within(dialog).getByRole('region', { name: 'HSC103 outcome' })).toHaveTextContent(
      'Interpret an ECG.'
    );

    // The corner button and the footer button both close it; use the footer one.
    const closers = within(dialog).getAllByRole('button', { name: 'Close' });
    expect(closers).toHaveLength(2);
    fireEvent.click(closers[closers.length - 1]);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows nothing while there are no near-duplicates or embeddings are off', async () => {
    mocked.fetchNearDuplicates.mockResolvedValue({ ...found([]), enabled: false });

    const card = await open();

    await waitFor(() => expect(mocked.fetchNearDuplicates).toHaveBeenCalled());
    expect(within(card).queryByRole('group', { name: 'Near-duplicate' })).not.toBeInTheDocument();
  });

  it('leaves the card as it was when the advice cannot be loaded', async () => {
    mocked.fetchNearDuplicates.mockRejectedValue(new ApiError(500, 'Broken'));

    const card = await open();

    await waitFor(() => expect(mocked.fetchNearDuplicates).toHaveBeenCalled());
    expect(card).toHaveTextContent('Describe the cardiac cycle.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not ask people who cannot edit objectives', async () => {
    mocked.fetchVersionStructure.mockResolvedValue(structure);
    mocked.fetchLearningEvent.mockResolvedValue(
      eventDetail([objective('o-e1', 'Describe the cardiac cycle.')], false)
    );

    const card = await open();

    expect(card).toHaveTextContent('Describe the cardiac cycle.');
    expect(mocked.fetchNearDuplicates).not.toHaveBeenCalled();
  });
});
