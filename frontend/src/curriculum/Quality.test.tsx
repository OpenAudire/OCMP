import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type {
  CheckedObjective,
  LearningEventDetail,
  QualityCheck,
  QualityFinding,
  VersionChecks,
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
  fetchLearningEvent: vi.fn(),
  fetchTaxonomyScales: vi.fn(),
  fetchEventLinkOptions: vi.fn(),
  createEventObjective: vi.fn(),
  checkObjectiveText: vi.fn(),
  fetchVersionChecks: vi.fn(),
  suggestForObjective: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const vague: QualityFinding = {
  code: 'vague_verb',
  severity: 'warning',
  message_key: 'curriculum.quality.vague_verb.message',
  suggestion_key: 'curriculum.quality.vague_verb.suggestion',
  params: { verbs: 'understand' },
};
const qualifier: QualityFinding = {
  code: 'ambiguous_qualifier',
  severity: 'info',
  message_key: 'curriculum.quality.ambiguous_qualifier.message',
  suggestion_key: 'curriculum.quality.ambiguous_qualifier.suggestion',
  params: { words: 'well' },
};

const event: LearningEventDetail = {
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
  can_edit_objectives: true,
  can_approve_objectives: false,
};

const eventTimeout = { timeout: 4000 };

// Each test renders the whole structure page cold and then waits for a debounce, with waits of
// up to 3 to 4 seconds inside it. Under a parallel run the sum of those waits is more than the
// 5 second default for one test, so the test itself failed before the waits could say why.
// The debounce is skipped with fake timers instead of waited for, and the test gets a budget
// that fits the waits it contains.
const COLD_RENDER_BUDGET_MS = 20_000;
const DEBOUNCE_MS = 700; // QualityPanel's CHECK_DELAY_MS (600) plus a margin

describe('live quality check in the objective dialog', { timeout: COLD_RENDER_BUDGET_MS }, () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  /** Types the wording and lets the debounce pass without waiting for it in real time. */
  async function typeWording(form: HTMLElement, value: string) {
    // Real time still passes (shouldAdvanceTime), so Testing Library's polling keeps working.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fireEvent.change(within(form).getByRole('textbox', { name: /Wording/ }), {
      target: { value },
    });
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
  }

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
    mocked.fetchVersionStructure.mockResolvedValue(structure);
    mocked.fetchLearningEvent.mockResolvedValue(event);
    mocked.fetchEventLinkOptions.mockResolvedValue([]);
    mocked.fetchTaxonomyScales.mockResolvedValue([
      {
        key: 'bloom',
        name: 'Bloom',
        description: '',
        levels: [
          { id: 'l-understand', name: 'Understand', position: 1, description: '' },
          { id: 'l-apply', name: 'Apply', position: 2, description: '' },
        ],
      },
    ]);
  });

  async function openDialog() {
    renderAt('/curriculum/versions/v2027?item=event:e1');
    await screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
    fireEvent.click(await screen.findByRole('button', { name: 'Add objective' }));
    return screen.findByRole('dialog', { name: 'Add objective' });
  }

  it('checks the wording after a pause and lists findings with words, not colour alone', async () => {
    const result: QualityCheck = {
      findings: [vague, qualifier],
      detected_verb: 'understand',
      suggestions: [],
    };
    mocked.checkObjectiveText.mockResolvedValue(result);
    const form = await openDialog();

    expect(within(form).getByText('Type the wording to see suggestions.')).toBeInTheDocument();
    await typeWording(form, 'Understand the heart well.');

    expect(await within(form).findByText('Warnings: 1. Notes: 1.', {}, eventTimeout)).toBeInTheDocument();
    expect(mocked.checkObjectiveText).toHaveBeenCalledTimes(1);
    expect(mocked.checkObjectiveText).toHaveBeenCalledWith(
      '/learning-events/e1/objective-checks',
      {
        text: 'Understand the heart well.',
        domain: null,
        taxonomy_level_id: null,
        has_parent_links: false,
      }
    );
    const items = within(form).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Warning');
    expect(items[0]).toHaveTextContent('Vague verb: understand.');
    expect(items[0]).toHaveTextContent('Use a verb you can observe');
    expect(items[1]).toHaveTextContent('Note');
    expect(within(form).getByRole('status')).toHaveTextContent('Warnings: 1. Notes: 1.');
  });

  it('shows the AI help only to people who hold the AI permission', async () => {
    mocked.checkObjectiveText.mockResolvedValue({ findings: [], detected_verb: null, suggestions: [] });
    const form = await openDialog();

    expect(within(form).queryByRole('group', { name: 'AI help with this wording' })).toBeNull();
  });

  it('puts an AI rewrite into the wording field only when the person uses it', async () => {
    mocked.fetchMyRoles.mockResolvedValue([
      role('programme_director', ['curriculum.view', 'objectives.edit', 'ai.run']),
    ]);
    mocked.checkObjectiveText.mockResolvedValue({ findings: [], detected_verb: null, suggestions: [] });
    mocked.suggestForObjective.mockResolvedValue({
      task: 'rewrite',
      run_id: 'r1',
      rewrite: { text: 'Describe the heart.', rationale: 'Measurable.', unchanged: false },
      classification: null,
    });
    const form = await openDialog();
    fireEvent.change(within(form).getByRole('textbox', { name: /Wording/ }), {
      target: { value: 'Understand the heart.' },
    });

    fireEvent.click(
      within(form).getByRole('button', { name: 'Suggest a measurable rewrite' })
    );
    await within(form).findByText('Suggested rewrite', {}, eventTimeout);
    expect(mocked.suggestForObjective).toHaveBeenCalledWith(
      '/learning-events/e1/objective-ai',
      expect.objectContaining({ task: 'rewrite', text: 'Understand the heart.' })
    );
    expect(within(form).getByRole('textbox', { name: /Wording/ })).toHaveValue(
      'Understand the heart.'
    );

    fireEvent.click(within(form).getByRole('button', { name: 'Use this wording' }));

    expect(within(form).getByRole('textbox', { name: /Wording/ })).toHaveValue(
      'Describe the heart.'
    );
  });

  it('offers a suggested level, applies it only when asked, and never blocks saving', async () => {
    mocked.checkObjectiveText.mockResolvedValue({
      findings: [vague],
      detected_verb: 'explain',
      suggestions: [
        {
          taxonomy_level_id: 'l-understand',
          level_name: 'Understand',
          scale_key: 'bloom',
          scale_name: 'Bloom',
        },
      ],
    });
    mocked.createEventObjective.mockResolvedValue({
      id: 'new',
      level: 'learning_event',
      text: 'Explain the heart.',
      domain: null,
      taxonomy_level_id: 'l-understand',
      status: 'draft',
      position: 0,
      parent_ids: [],
    });
    const form = await openDialog();
    await typeWording(form, 'Explain the heart.');

    const use = await within(form).findByRole(
      'button',
      { name: 'Use Understand (Bloom)' },
      eventTimeout
    );
    expect(within(form).getByRole('combobox', { name: 'Taxonomy level' })).toHaveValue('');
    fireEvent.click(use);
    expect(within(form).getByRole('combobox', { name: 'Taxonomy level' })).toHaveValue(
      'l-understand'
    );
    expect(
      within(form).queryByRole('button', { name: 'Use Understand (Bloom)' })
    ).not.toBeInTheDocument();

    fireEvent.click(within(form).getByRole('button', { name: 'Add objective' }));

    expect(await screen.findByText('The objective was added.')).toBeInTheDocument();
    expect(mocked.createEventObjective).toHaveBeenCalledTimes(1);
  });

  it('says when the check is unavailable and still lets the person save', async () => {
    mocked.checkObjectiveText.mockRejectedValue(new ApiError(429, 'Too many attempts.'));
    mocked.createEventObjective.mockResolvedValue({
      id: 'new',
      level: 'learning_event',
      text: 'Explain the heart.',
      domain: null,
      taxonomy_level_id: null,
      status: 'draft',
      position: 0,
      parent_ids: [],
    });
    const form = await openDialog();
    await typeWording(form, 'Explain the heart.');

    expect(
      await within(form).findByText(
        'The quality check is not available right now. You can still save.',
        {},
        eventTimeout
      )
    ).toBeInTheDocument();
    fireEvent.click(within(form).getByRole('button', { name: 'Add objective' }));
    expect(await screen.findByText('The objective was added.')).toBeInTheDocument();
  });
});

function checked(overrides: Partial<CheckedObjective> & Pick<CheckedObjective, 'objective_id'>) {
  return {
    level: 'learning_event',
    text: 'Explain the heart.',
    status: 'draft',
    domain: 'knowledge',
    module_id: 'm2',
    module_code: 'HSC201',
    event_id: 'e1',
    event_title: 'Cardiac cycle',
    can_edit: true,
    findings: [],
    detected_verb: 'explain',
    suggestions: [],
    near_duplicates: [],
    ...overrides,
  } satisfies CheckedObjective;
}

const checks: VersionChecks = {
  version_id: 'v2027',
  rules_language: 'en',
  rules_version: 1,
  near_duplicates_checked: true,
  objectives: [
    checked({ objective_id: 'a', text: 'Understand the heart.', findings: [vague] }),
    checked({
      objective_id: 'b',
      level: 'module',
      event_id: null,
      event_title: null,
      text: 'Interpret tests well.',
      findings: [qualifier],
    }),
    checked({
      objective_id: 'c',
      level: 'programme',
      module_id: null,
      module_code: null,
      event_id: null,
      event_title: null,
      text: 'Practise safely.',
    }),
  ],
};

describe('objective quality page', () => {
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
    mocked.fetchVersionStructure.mockResolvedValue(structure);
  });

  it('is reached from the version bar by people who edit objectives', async () => {
    renderAt('/curriculum/versions/v2027');

    const link = await screen.findByRole('link', { name: 'Check wording' });
    expect(link).toHaveAttribute('href', '/curriculum/versions/v2027/quality');
  });

  it('is not offered to people who cannot edit objectives', async () => {
    mocked.fetchMyRoles.mockResolvedValue([role('student', ['curriculum.view'])]);
    renderAt('/curriculum/versions/v2027');

    await screen.findByRole('tree', { name: 'Structure of BSc Health Sciences (Demo)' });
    expect(screen.queryByRole('link', { name: 'Check wording' })).not.toBeInTheDocument();
  });

  it('lists findings per objective and filters by severity and rule', async () => {
    mocked.fetchVersionChecks.mockResolvedValue(checks);
    renderAt('/curriculum/versions/v2027/quality');

    expect(await screen.findByRole('heading', { level: 1, name: 'Objective quality' })).toBeVisible();
    expect(await screen.findByText('Showing 3 of 3 objectives checked.')).toBeInTheDocument();
    expect(screen.getByText('Rules: en, version 1.')).toBeInTheDocument();
    expect(screen.getByText('No findings')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: 'Severity' }), {
      target: { value: 'warning' },
    });
    expect(screen.getByText('Showing 1 of 3 objectives checked.')).toBeInTheDocument();
    expect(screen.getByText('Understand the heart.')).toBeInTheDocument();
    expect(screen.queryByText('Interpret tests well.')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: 'Severity' }), {
      target: { value: 'all' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'Rule' }), {
      target: { value: 'ambiguous_qualifier' },
    });
    expect(screen.getByText('Showing 1 of 3 objectives checked.')).toBeInTheDocument();
    expect(screen.getByText('Interpret tests well.')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: 'Rule' }), {
      target: { value: 'too_long' },
    });
    expect(await screen.findByRole('heading', { name: 'Nothing matches' })).toBeInTheDocument();
  });

  it('lists near-duplicates and personal information as findings that can be filtered', async () => {
    mocked.fetchVersionChecks.mockResolvedValue({
      ...checks,
      objectives: [
        checked({
          objective_id: 'd',
          text: 'Describe the cardiac cycle.',
          findings: [
            {
              code: 'near_duplicate',
              severity: 'info',
              message_key: 'curriculum.quality.near_duplicate.message',
              suggestion_key: 'curriculum.quality.near_duplicate.suggestion',
              params: { percent: '97', where: 'HSC103 Lecture 9' },
            },
          ],
        }),
        checked({
          objective_id: 'e',
          text: 'Phone the patient after the lab.',
          findings: [
            {
              code: 'possible_personal_information',
              severity: 'warning',
              message_key: 'curriculum.quality.possible_personal_information.message',
              suggestion_key: 'curriculum.quality.possible_personal_information.suggestion',
              params: { kinds: 'phone, email' },
            },
          ],
        }),
        checked({ objective_id: 'f', text: 'Name the valves.' }),
      ],
    });
    renderAt('/curriculum/versions/v2027/quality');

    expect(
      await screen.findByText(
        'Near-duplicate of an objective in HSC103 Lecture 9 (97% similar). Repeat on purpose, or remove?'
      )
    ).toBeInTheDocument();
    // The kinds are put into words; no value from the objective is repeated.
    expect(
      screen.getByText(
        'The wording may hold personal information: a phone number, an email address.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/Near-duplicate checking is off/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('combobox', { name: 'Rule' }), {
      target: { value: 'possible_personal_information' },
    });
    expect(screen.getByText('Showing 1 of 3 objectives checked.')).toBeInTheDocument();
    expect(screen.getByText('Phone the patient after the lab.')).toBeInTheDocument();
  });

  it('says so when near-duplicate checking is off', async () => {
    mocked.fetchVersionChecks.mockResolvedValue({ ...checks, near_duplicates_checked: false });
    renderAt('/curriculum/versions/v2027/quality');

    expect(
      await screen.findByText(
        'Near-duplicate checking is off on this installation, so none are listed. An administrator can turn it on (see the operations guide).'
      )
    ).toBeInTheDocument();
  });

  it('links each objective to the item that holds it', async () => {
    mocked.fetchVersionChecks.mockResolvedValue(checks);
    renderAt('/curriculum/versions/v2027/quality');

    const links = await screen.findAllByRole('link', { name: /Open in the curriculum/ });
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/curriculum/versions/v2027?item=event%3Ae1',
      '/curriculum/versions/v2027?item=module%3Am2',
      '/curriculum/versions/v2027',
    ]);
  });

  it('has empty, forbidden and error states', async () => {
    mocked.fetchVersionChecks.mockResolvedValue({ ...checks, objectives: [] });
    const { unmount } = renderAt('/curriculum/versions/v2027/quality');
    expect(await screen.findByRole('heading', { name: 'Nothing to check yet' })).toBeVisible();
    unmount();

    mocked.fetchVersionChecks.mockRejectedValue(new ApiError(403, 'No'));
    const second = renderAt('/curriculum/versions/v2027/quality');
    expect(await screen.findByRole('heading', { name: 'No access to the checker' })).toBeVisible();
    second.unmount();

    mocked.fetchVersionChecks.mockRejectedValue(new ApiError(500, 'Broken'));
    renderAt('/curriculum/versions/v2027/quality');
    expect(
      await screen.findByRole('heading', { name: 'The checks could not be loaded' })
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
