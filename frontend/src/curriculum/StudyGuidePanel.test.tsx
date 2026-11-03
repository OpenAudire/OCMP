import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { ObjectiveProposal, StudyGuideRun } from '../api/types';
import { createQueryClient } from '../queryClient';
import { ThemeProvider } from '../theme/ThemeProvider';
import { StudyGuidePanel } from './StudyGuidePanel';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchStudyGuideRuns: vi.fn(),
  fetchProposals: vi.fn(),
  uploadStudyGuide: vi.fn(),
  cancelStudyGuideRun: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function run(overrides: Partial<StudyGuideRun> = {}): StudyGuideRun {
  return {
    id: 'r1',
    status: 'succeeded',
    module_id: 'm1',
    total_items: 3,
    done_items: 3,
    failed_items: 0,
    proposals_created: 2,
    truncated: false,
    error_message: null,
    created_at: '2026-11-04T10:00:00Z',
    finished_at: '2026-11-04T10:01:00Z',
    ...overrides,
  };
}

function proposal(overrides: Partial<ObjectiveProposal> = {}): ObjectiveProposal {
  return {
    id: 'p1',
    run_id: 'r1',
    module_id: 'm1',
    text: 'Describe the structure of the heart.',
    domain: 'knowledge',
    source_quote: 'Describe the structure of the heart.',
    status: 'pending',
    ...overrides,
  };
}

function show() {
  const onSaved = vi.fn();
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <StudyGuidePanel moduleId="m1" versionId="v1" onSaved={onSaved} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return { onSaved };
}

async function openDialog() {
  fireEvent.click(await screen.findByRole('button', { name: 'Read a study guide' }));
  return screen.findByRole('dialog', { name: 'Read a study guide' });
}

function choose(dialog: HTMLElement, file: File) {
  const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

describe('study guide panel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocked.fetchStudyGuideRuns.mockResolvedValue([]);
    mocked.fetchProposals.mockResolvedValue([]);
  });

  it('explains what happens and offers the upload', async () => {
    show();

    expect(await screen.findByRole('heading', { name: 'Study guide' })).toBeInTheDocument();
    expect(screen.getByText(/Nothing becomes an outcome until you accept it/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Read a study guide' })).toBeEnabled();
  });

  it('will not read a study guide until the no-patient-information box is ticked', async () => {
    show();
    const dialog = await openDialog();
    choose(dialog, new File(['x'], 'guide.docx'));
    // The button that clears the chosen file has a name (it had none in the first version).
    expect(
      await within(dialog).findByRole('button', { name: 'Remove the chosen file' }),
    ).toBeVisible();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Read it' }));

    expect(
      await within(dialog).findByText('Confirm this before the study guide is read.'),
    ).toBeVisible();
    expect(mocked.uploadStudyGuide).not.toHaveBeenCalled();
  });

  it('uploads the file with the confirmation and then follows the reading', async () => {
    mocked.uploadStudyGuide.mockResolvedValue(
      run({ status: 'queued', done_items: 0, proposals_created: 0 }),
    );
    show();
    const dialog = await openDialog();
    const file = new File(['x'], 'guide.docx');
    choose(dialog, file);
    fireEvent.click(
      within(dialog).getByRole('checkbox', { name: /contains no real patient information/ }),
    );
    mocked.fetchStudyGuideRuns.mockResolvedValue([
      run({ status: 'queued', done_items: 0, proposals_created: 0 }),
    ]);

    fireEvent.click(within(dialog).getByRole('button', { name: 'Read it' }));

    await waitFor(() =>
      expect(mocked.uploadStudyGuide).toHaveBeenCalledWith('m1', file, {
        confirmed: true,
        text_version: '1',
      }),
    );
    expect(await screen.findByText('Waiting to start')).toBeInTheDocument();
    // One reading at a time.
    expect(screen.getByRole('button', { name: 'Read a study guide' })).toBeDisabled();
  });

  it.each([
    [new ApiError(413, 'big'), /larger than 10 MB/],
    [new ApiError(409, 'AI is switched off.'), /AI is switched off/],
    [new ApiError(422, 'Almost no text could be read from this file.'), /Almost no text/],
    [new ApiError(422, 'Request failed with status code 422'), /This file could not be used\./],
    [new ApiError(403, 'no'), /do not have permission/],
    [new ApiError(500, 'boom'), /Something went wrong/],
  ])('says in words why an upload failed: %s', async (error, message) => {
    mocked.uploadStudyGuide.mockRejectedValue(error);
    show();
    const dialog = await openDialog();
    choose(dialog, new File(['x'], 'guide.pdf'));
    fireEvent.click(
      within(dialog).getByRole('checkbox', { name: /contains no real patient information/ }),
    );

    fireEvent.click(within(dialog).getByRole('button', { name: 'Read it' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(message);
  });

  it('shows progress while it reads and lets a person cancel', async () => {
    mocked.fetchStudyGuideRuns.mockResolvedValue([
      run({ status: 'running', done_items: 1, proposals_created: 2, failed_items: 1 }),
    ]);
    mocked.cancelStudyGuideRun.mockResolvedValue(run({ status: 'cancelled' }));
    show();

    expect(await screen.findByText('Reading')).toBeInTheDocument();
    expect(
      screen.getByText(/1 of 3 parts read\. 2 objectives proposed\. 1 part could not be read\./),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('progressbar', { name: 'Parts of the study guide read' }),
    ).toHaveAttribute('aria-valuenow', '33');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel reading' }));

    await waitFor(() => expect(mocked.cancelStudyGuideRun).toHaveBeenCalledWith('r1'));
  });

  it.each([
    [{ status: 'succeeded' as const }, 'Finished'],
    [{ status: 'cancelled' as const }, 'Cancelled'],
    [
      { status: 'budget_exceeded' as const, error_message: 'The monthly limit was reached.' },
      'Stopped: monthly limit reached',
    ],
    [
      { status: 'failed' as const, error_message: 'The uploaded text is no longer kept.' },
      'Stopped with a problem',
    ],
  ])('says how a reading that ended went: %j', async (change, label) => {
    mocked.fetchStudyGuideRuns.mockResolvedValue([run(change)]);
    show();

    expect(await screen.findByText(label)).toBeInTheDocument();
    if ('error_message' in change)
      expect(screen.getByText(change.error_message as string)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel reading' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Read a study guide' })).toBeEnabled();
  });

  it('says when only the start of a long guide was read', async () => {
    mocked.fetchStudyGuideRuns.mockResolvedValue([run({ truncated: true })]);
    show();

    expect(await screen.findByText(/only the first part was read/)).toBeInTheDocument();
  });

  it('lists the proposals with their source and accepts one with a correction', async () => {
    mocked.fetchProposals.mockResolvedValue([
      proposal(),
      proposal({ id: 'p2', text: 'Explain blood pressure.' }),
    ]);
    mocked.acceptProposal.mockResolvedValue({
      proposal: proposal({ status: 'accepted' }),
      objective_id: 'o1',
    });
    const { onSaved } = show();

    const list = await screen.findByRole('list', { name: 'Proposed objectives' });
    expect(screen.getByText('2 proposed objectives to decide')).toBeInTheDocument();
    const cards = within(list).getAllByRole('listitem');
    expect(cards).toHaveLength(2);
    expect(
      within(cards[0]).getByText(/From the study guide: “Describe the structure of the heart\.”/),
    ).toBeInTheDocument();
    fireEvent.change(within(cards[0]).getByRole('textbox', { name: 'Wording' }), {
      target: { value: 'Describe the heart.' },
    });
    fireEvent.change(within(cards[0]).getByRole('combobox', { name: 'Domain' }), {
      target: { value: 'skill' },
    });
    mocked.fetchProposals.mockResolvedValue([
      proposal({ id: 'p2', text: 'Explain blood pressure.' }),
    ]);

    fireEvent.click(within(cards[0]).getByRole('button', { name: 'Accept as a draft objective' }));

    await waitFor(() =>
      expect(mocked.acceptProposal).toHaveBeenCalledWith('p1', {
        text: 'Describe the heart.',
        domain: 'skill',
        set_domain: true,
      }),
    );
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith({
        message: 'The objective was added as a draft.',
        focus: true,
      }),
    );
    await waitFor(() =>
      expect(screen.getByText('1 proposed objective to decide')).toBeInTheDocument(),
    );
  });

  it('rejects a proposal', async () => {
    mocked.fetchProposals.mockResolvedValue([proposal()]);
    mocked.rejectProposal.mockResolvedValue(proposal({ status: 'rejected' }));
    const { onSaved } = show();
    const card = (await screen.findAllByRole('listitem'))[0];

    fireEvent.click(within(card).getByRole('button', { name: 'Reject' }));

    await waitFor(() => expect(mocked.rejectProposal).toHaveBeenCalledWith('p1'));
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith({ message: 'The proposal was rejected.', focus: true }),
    );
  });

  it('cannot accept an empty wording', async () => {
    mocked.fetchProposals.mockResolvedValue([proposal()]);
    show();
    const card = (await screen.findAllByRole('listitem'))[0];

    fireEvent.change(within(card).getByRole('textbox', { name: 'Wording' }), {
      target: { value: '  ' },
    });

    expect(
      within(card).getByRole('button', { name: 'Accept as a draft objective' }),
    ).toBeDisabled();
  });

  it('says so when someone else already decided a proposal', async () => {
    mocked.fetchProposals.mockResolvedValue([proposal()]);
    mocked.acceptProposal.mockRejectedValue(new ApiError(409, 'decided'));
    show();
    const card = (await screen.findAllByRole('listitem'))[0];

    fireEvent.click(within(card).getByRole('button', { name: 'Accept as a draft objective' }));

    expect(await within(card).findByRole('alert')).toHaveTextContent(/already decided/);
  });

  it('says so when the progress cannot be loaded', async () => {
    mocked.fetchStudyGuideRuns.mockRejectedValue(new ApiError(500, 'Broken'));
    show();

    expect(
      await screen.findByText('The progress of the reading could not be loaded.'),
    ).toBeInTheDocument();
  });
});
