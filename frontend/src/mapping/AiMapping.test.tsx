import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type {
  AiMappingRun,
  FrameworkLibrary,
  MappingWorkspace,
  WorkspaceObjective,
} from '../api/types';
import { programmes } from '../curriculum/testData';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchMappingWorkspace: vi.fn(),
  fetchReviewCount: vi.fn(),
  fetchFrameworkLibrary: vi.fn(),
  fetchFrameworkItems: vi.fn(),
  fetchAiMappingRuns: vi.fn(),
  startAiMapping: vi.fn(),
  cancelAiMappingRun: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const library: FrameworkLibrary = {
  can_manage: false,
  frameworks: [
    {
      id: 'f1',
      key: 'demo',
      name: 'Demo Graduate Competencies',
      version_label: '1.0',
      publisher: 'Demo University',
      licence_note: '',
      description: '',
      url: null,
      profile: 'core',
      status: 'active',
      item_count: 2,
      top_level_count: 2,
      level_count: 1,
    },
  ],
};

function objective(overrides: Partial<WorkspaceObjective>): WorkspaceObjective {
  return {
    id: 'o1',
    text: 'Describe the heart.',
    level: 'module',
    phase_id: null,
    phase_name: null,
    module_id: 'm1',
    module_code: 'HSC101',
    module_name: 'Anatomy',
    learning_event_id: null,
    learning_event_title: null,
    can_edit: true,
    can_review: true,
    links: [],
    ...overrides,
  };
}

function workspace(overrides: Partial<MappingWorkspace> = {}): MappingWorkspace {
  return {
    version_id: 'v2027',
    academic_year: 2027,
    version_status: 'draft',
    programme_id: 'p1',
    programme_name: 'BSc Health Sciences (Demo)',
    editable: true,
    four_eyes: false,
    objectives: [
      objective({}),
      objective({ id: 'o2', module_id: 'm2', module_code: 'HSC102', module_name: 'Physiology' }),
    ],
    ...overrides,
  };
}

function run(overrides: Partial<AiMappingRun> = {}): AiMappingRun {
  return {
    id: 'r1',
    status: 'running',
    version_id: 'v2027',
    framework_id: 'f1',
    module_id: null,
    prompt_version: 'mapping:1',
    provider: 'anthropic',
    model: 'claude-sonnet-5-5',
    top_k: 10,
    total_items: 10,
    done_items: 3,
    failed_items: 0,
    links_created: 2,
    input_tokens: 0,
    output_tokens: 0,
    estimated_cost: '0',
    error_message: null,
    created_at: '2026-11-03T10:00:00Z',
    started_at: '2026-11-03T10:00:01Z',
    finished_at: null,
    ...overrides,
  };
}

function signIn(permissions = ['curriculum.view', 'mapping.edit', 'mapping.review', 'ai.run']) {
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([role('r', permissions)]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
}

async function open() {
  renderAt('/mapping/v2027');
  return screen.findByRole('region', { name: 'Suggest links with AI' });
}

describe('AI mapping panel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    signIn();
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.fetchMappingWorkspace.mockResolvedValue(workspace());
    mocked.fetchReviewCount.mockResolvedValue({ first: 0, second: 0, recheck: 0, waiting: 0, total: 0 });
    mocked.fetchFrameworkLibrary.mockResolvedValue(library);
    mocked.fetchFrameworkItems.mockResolvedValue({ parent_id: null, offset: 0, total: 0, items: [] });
    mocked.fetchAiMappingRuns.mockResolvedValue([]);
  });

  it('is not offered to people who may not run AI mapping', async () => {
    signIn(['curriculum.view', 'mapping.edit', 'mapping.review']);
    renderAt('/mapping/v2027');

    await screen.findByRole('heading', { level: 1, name: 'Mapping' });
    await waitFor(() => expect(mocked.fetchMappingWorkspace).toHaveBeenCalled());
    expect(screen.queryByRole('region', { name: 'Suggest links with AI' })).not.toBeInTheDocument();
    expect(mocked.fetchAiMappingRuns).not.toHaveBeenCalled();
  });

  it('is not offered on a version that cannot be changed', async () => {
    mocked.fetchMappingWorkspace.mockResolvedValue(
      workspace({ editable: false, version_status: 'published' })
    );
    renderAt('/mapping/v2027');

    await screen.findByRole('heading', { level: 1, name: 'Mapping' });
    await waitFor(() => expect(mocked.fetchMappingWorkspace).toHaveBeenCalled());
    expect(screen.queryByRole('region', { name: 'Suggest links with AI' })).not.toBeInTheDocument();
  });

  it('starts a run for one module and a framework, then shows that it is waiting', async () => {
    mocked.startAiMapping.mockResolvedValue(run({ status: 'queued', done_items: 0, links_created: 0 }));
    const panel = await open();

    fireEvent.click(within(panel).getByRole('button', { name: 'Suggest links with AI' }));
    const dialog = await screen.findByRole('dialog', { name: 'Suggest links with AI' });
    fireEvent.change(await within(dialog).findByRole('combobox', { name: 'Objectives to map' }), {
      target: { value: 'm2' },
    });
    expect(within(dialog).getByRole('option', { name: 'Only HSC102 Physiology' })).toBeInTheDocument();
    mocked.fetchAiMappingRuns.mockResolvedValue([
      run({ status: 'queued', done_items: 0, links_created: 0 }),
    ]);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Start' }));

    await waitFor(() =>
      expect(mocked.startAiMapping).toHaveBeenCalledWith('v2027', {
        framework_id: 'f1',
        module_id: 'm2',
      })
    );
    expect(await within(panel).findByText('Waiting to start')).toBeInTheDocument();
    // A run in progress cannot be started a second time.
    expect(within(panel).getByRole('button', { name: 'Suggest links with AI' })).toBeDisabled();
  });

  it('shows progress while it runs and lets a person cancel', async () => {
    mocked.fetchAiMappingRuns.mockResolvedValue([run({ failed_items: 1 })]);
    mocked.cancelAiMappingRun.mockResolvedValue(run({ status: 'cancelled' }));
    const panel = await open();

    expect(await within(panel).findByText('Running')).toBeInTheDocument();
    expect(within(panel).getByText(/3 of 10 objectives/)).toBeInTheDocument();
    expect(within(panel).getByText(/2 suggestions made/)).toBeInTheDocument();
    expect(within(panel).getByText(/1 objectives could not be mapped/)).toBeInTheDocument();
    expect(within(panel).getByRole('progressbar', { name: 'Objectives looked at' })).toHaveAttribute(
      'aria-valuenow',
      '30'
    );

    fireEvent.click(within(panel).getByRole('button', { name: 'Cancel run' }));

    await waitFor(() => expect(mocked.cancelAiMappingRun).toHaveBeenCalledWith('r1'));
  });

  it('reads the run again until it ends, then refreshes the suggestions and offers the queue', async () => {
    mocked.fetchAiMappingRuns
      .mockResolvedValueOnce([run()])
      .mockResolvedValue([run({ status: 'succeeded', done_items: 10, finished_at: '2026-11-03T10:05:00Z' })]);
    const panel = await open();

    expect(await within(panel).findByText('Running')).toBeInTheDocument();
    expect(mocked.fetchMappingWorkspace).toHaveBeenCalledTimes(1);

    expect(await within(panel).findByText('Finished', {}, { timeout: 6000 })).toBeInTheDocument();
    const queue = within(panel).getByRole('link', { name: 'Open the review queue' });
    expect(queue).toHaveAttribute('href', '/mapping/review');
    await waitFor(() => expect(mocked.fetchMappingWorkspace).toHaveBeenCalledTimes(2));
    expect(within(panel).queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument();
  }, 15000);

  it.each([
    [
      { status: 'budget_exceeded', error_message: 'The monthly limit was reached.' },
      'Stopped: monthly limit reached',
      /monthly AI limit was reached/,
    ],
    [{ status: 'cancelled' }, 'Cancelled', /The run was cancelled/],
    [
      { status: 'failed', error_message: 'The AI provider failed several times in a row.' },
      'Stopped with a problem',
      /The AI provider failed several times in a row\./,
    ],
  ] as const)('says how a run that did not finish ended: %s', async (change, label, reason) => {
    mocked.fetchAiMappingRuns.mockResolvedValue([run({ ...change, finished_at: '2026-11-03T10:05:00Z' })]);
    const panel = await open();

    expect(await within(panel).findByText(label)).toBeInTheDocument();
    expect(within(panel).getByText(reason)).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument();
  });

  it('keeps what a finished run made visible in the queue link', async () => {
    mocked.fetchAiMappingRuns.mockResolvedValue([
      run({ status: 'cancelled', links_created: 4, done_items: 5 }),
    ]);
    const panel = await open();

    expect(await within(panel).findByRole('link', { name: 'Open the review queue' })).toBeVisible();
  });

  it('says why a run could not start', async () => {
    mocked.startAiMapping.mockRejectedValue(new ApiError(409, 'AI is turned off.'));
    const panel = await open();

    fireEvent.click(within(panel).getByRole('button', { name: 'Suggest links with AI' }));
    const dialog = await screen.findByRole('dialog', { name: 'Suggest links with AI' });
    await within(dialog).findByRole('combobox', { name: 'Framework' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Start' }));

    expect(
      await within(dialog).findByText(/This could not be started\. AI may be switched off/)
    ).toBeInTheDocument();
  });

  it('tells the person when there is no framework to map to', async () => {
    mocked.fetchFrameworkLibrary.mockResolvedValue({ ...library, frameworks: [] });
    const panel = await open();

    fireEvent.click(within(panel).getByRole('button', { name: 'Suggest links with AI' }));
    const dialog = await screen.findByRole('dialog', { name: 'Suggest links with AI' });

    expect(
      await within(dialog).findByText('There is no framework in use to map to yet.')
    ).toBeInTheDocument();
  });

  it('says so when the progress cannot be loaded', async () => {
    mocked.fetchAiMappingRuns.mockRejectedValue(new ApiError(500, 'Broken'));
    const panel = await open();

    expect(
      await within(panel).findByText('The progress of the run could not be loaded.')
    ).toBeInTheDocument();
  });
});
