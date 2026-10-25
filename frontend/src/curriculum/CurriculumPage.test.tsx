import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { Programme } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { cardio, programmes, structure } from './testData';

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
}));

const mocked = vi.mocked(endpoints);

const programmeDetail: Programme = {
  ...programmes[0],
  qualification_type: {
    key: 'bachelors',
    name: "Bachelor's degree",
    nqf_exit_level: 7,
    min_total_credits: 360,
  },
  nqf_exit_level: 7,
  saqa_id: '00000',
  total_credits: 360,
  minimum_duration_years: '3.0',
  che_accreditation_status: 'accredited',
  council_name: null,
  council_accreditation_status: 'not_applicable',
};

function signedIn(permissions = ['curriculum.view']) {
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([role('reader', permissions)]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
}

/** Press keys on whatever has focus, as the tree's keyboard handling expects. */
function press(...keys: string[]) {
  for (const key of keys) {
    act(() => {
      fireEvent.keyDown(document.activeElement!, { key });
    });
  }
}

function tree() {
  return screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
}

describe('curriculum builder (read-only)', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    signedIn();
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchProgramme.mockResolvedValue(programmeDetail);
    mocked.fetchVersionStructure.mockResolvedValue(structure);
    mocked.fetchProgrammeOutcomes.mockResolvedValue([
      {
        id: 'o1',
        text: 'Apply clinical reasoning.',
        domain: 'skill',
        status: 'approved',
        position: 0,
        parent_ids: [],
      },
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
      objectives: [
        {
          id: 'o3',
          text: 'Describe the phases of the cardiac cycle.',
          domain: null,
          status: 'draft',
          position: 0,
          parent_ids: ['o2'],
        },
      ],
    });
  });

  it('opens the newest version and shows the programme', async () => {
    renderAt('/curriculum');

    const structureTree = await tree();
    expect(mocked.fetchVersionStructure).toHaveBeenCalledWith('v2027');
    expect(
      screen.getAllByRole('button', { name: 'BSc Health Sciences (Demo) · 2027 · Draft' })
    ).not.toHaveLength(0);
    const rootItem = within(structureTree).getByRole('treeitem', { selected: true });
    expect(rootItem).toHaveTextContent('BSc Health Sciences (Demo)');
    expect(rootItem).toHaveAttribute('tabindex', '0');
    // Institution terminology: modules are "Courses" for this institution.
    expect(within(structureTree).getByRole('treeitem', { name: /Year 1/ })).toHaveTextContent(
      '1 course'
    );
    expect(await screen.findByText("Bachelor's degree")).toBeInTheDocument();
    expect(await screen.findByText('Apply clinical reasoning.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Programme outcomes' })).toBeVisible();
  });

  it('opens the version remembered in this browser', async () => {
    window.localStorage.setItem('cic.curriculumVersion', 'v2026');

    renderAt('/curriculum');

    await tree();
    expect(mocked.fetchVersionStructure).toHaveBeenCalledWith('v2026');
  });

  it('moves through the tree with the keyboard and shows the chosen module', async () => {
    renderAt('/curriculum/versions/v2027');
    const structureTree = await tree();

    act(() => within(structureTree).getByRole('treeitem', { selected: true }).focus());
    press('ArrowDown', 'ArrowDown', 'ArrowDown');
    const year2 = within(structureTree).getByRole('treeitem', { name: /Year 2/ });
    expect(year2).toHaveFocus();
    expect(year2).toHaveAttribute('aria-expanded', 'true');
    press('ArrowLeft');
    expect(year2).toHaveAttribute('aria-expanded', 'false');
    press('ArrowRight');
    expect(year2).toHaveAttribute('aria-expanded', 'true');
    press('ArrowRight', 'Enter');

    const module = within(structureTree).getByRole('treeitem', { name: /HSC201/ });
    expect(module).toHaveAttribute('aria-selected', 'true');
    expect(module).toHaveAttribute('aria-level', '3');
    expect(await screen.findByText('Heart and circulation.')).toBeInTheDocument();
    expect(mocked.fetchModule).toHaveBeenCalledWith('m2');
    // 210 minutes of contact time and of self-study.
    expect(screen.getAllByText('3.5 h')).toHaveLength(2);
    expect(screen.getByText('No outcomes yet.')).toBeInTheDocument();

    press('ArrowLeft');
    expect(year2).toHaveFocus();
    press('End');
    expect(within(structureTree).getByRole('treeitem', { name: /HSC300/ })).toHaveFocus();
    press('Home');
    expect(within(structureTree).getAllByRole('treeitem')[0]).toHaveFocus();
  });

  it('opens a session named in the address with the way to it expanded', async () => {
    renderAt('/curriculum/versions/v2027?item=event:e1');
    const structureTree = await tree();

    const session = within(structureTree).getByRole('treeitem', { name: /Cardiac cycle/ });
    expect(session).toHaveAttribute('aria-selected', 'true');
    expect(session).toHaveTextContent('Week 4');
    expect(screen.getByText('Year 2 › HSC201 Cardiovascular system')).toBeInTheDocument();
    expect(await screen.findByText('Describe the phases of the cardiac cycle.')).toBeVisible();
    expect(screen.getByText('Domain not set')).toBeInTheDocument();
    expect(screen.getByText('Linked to 1 broader outcome')).toBeInTheDocument();
  });

  it('sums up a phase and the modules across phases', async () => {
    renderAt('/curriculum/versions/v2027?item=phase:y2');
    await tree();

    const details = screen.getByRole('region', { name: 'Selected item' });
    expect(within(details).getByRole('heading', { level: 2, name: 'Year 2' })).toBeVisible();
    const facts = within(details)
      .getAllByRole('definition')
      .map((fact) => fact.textContent);
    // Kind, courses, sessions, credits.
    expect(facts).toEqual(['Year', '1', '2', '16']);

    fireEvent.click(screen.getByRole('treeitem', { name: 'Across phases' }));
    expect(
      await within(details).findByRole('heading', { level: 2, name: 'Across phases' })
    ).toBeVisible();
    expect(
      within(details)
        .getAllByRole('definition')
        .map((fact) => fact.textContent)
    ).toEqual(['1', '0', '12']);
  });

  it('switches version from the header', async () => {
    renderAt('/curriculum/versions/v2027');
    await tree();

    const [switcher] = screen.getAllByRole('button', {
      name: 'BSc Health Sciences (Demo) · 2027 · Draft',
    });
    fireEvent.click(switcher);
    // jsdom never finishes the menu's fade-in; the end-to-end tests check it opens visibly.
    expect(
      await screen.findByRole('menuitem', { name: '2027 · Draft', current: true, hidden: true })
    ).toBeInTheDocument();
    const nursing = screen.getByRole('group', { name: 'Bachelor of Nursing (Demo)', hidden: true });
    fireEvent.click(within(nursing).getByRole('menuitem', { name: '2026 · Draft', hidden: true }));

    await waitFor(() => expect(mocked.fetchVersionStructure).toHaveBeenCalledWith('n2026'));
    expect(window.localStorage.getItem('cic.curriculumVersion')).toBe('n2026');
  });

  it('tells people with a narrower role what they see', async () => {
    mocked.fetchVersionStructure.mockResolvedValue({
      ...structure,
      partial: true,
      outcome_count: null,
      phases: [{ ...structure.phases[1], modules: [{ ...cardio, context_only: true }] }],
      modules_without_phase: [],
    });
    renderAt('/curriculum/versions/v2027');
    const structureTree = await tree();

    expect(screen.getByText('You see the courses and sessions you work on.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Programme outcomes' })).not.toBeInTheDocument();
    expect(mocked.fetchProgrammeOutcomes).not.toHaveBeenCalled();

    fireEvent.click(within(structureTree).getByRole('treeitem', { name: /HSC201/ }));
    expect(screen.getByText('You can see only your sessions in this course.')).toBeInTheDocument();
    expect(mocked.fetchModule).not.toHaveBeenCalled();
  });

  it('says when a version has no modules yet', async () => {
    mocked.fetchVersionStructure.mockResolvedValue({
      ...structure,
      phases: [],
      modules_without_phase: [],
    });

    renderAt('/curriculum/versions/v2027');

    expect(await screen.findByRole('heading', { name: 'No courses yet' })).toBeInTheDocument();
  });

  it('says when there is no programme to show', async () => {
    mocked.fetchProgrammes.mockResolvedValue([]);

    renderAt('/curriculum');

    expect(await screen.findByRole('heading', { name: 'No programmes to show' })).toBeVisible();
    expect(screen.getByText(/Ask your curriculum office/)).toBeInTheDocument();
  });

  it('tells administrators how to load the demo programme', async () => {
    signedIn(['curriculum.view', 'settings.manage']);
    mocked.fetchProgrammes.mockResolvedValue([]);

    renderAt('/curriculum');

    expect(await screen.findByText(/app\.cli load-demo/)).toBeInTheDocument();
  });

  it('explains a version that is not available', async () => {
    mocked.fetchVersionStructure.mockRejectedValue(new ApiError(404, 'Not found.'));

    renderAt('/curriculum/versions/gone');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("This curriculum version isn't available");
    expect(within(alert).getByRole('link', { name: 'Open the latest version' })).toHaveAttribute(
      'href',
      '/curriculum'
    );
  });

  it('offers to try again when loading fails', async () => {
    mocked.fetchVersionStructure.mockRejectedValueOnce(new ApiError(500, 'Server error.'));
    renderAt('/curriculum/versions/v2027');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("Couldn't load the curriculum");
    fireEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(await tree()).toBeInTheDocument();
  });
});
