import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import { ApiError } from '../api/client';
import type { ReviewLink, ReviewQueue, ReviewStage } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { shortcutFor } from './shortcuts';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchReviewQueue: vi.fn(),
  fetchReviewCount: vi.fn(),
  reviewMappingLink: vi.fn(),
  bulkAcceptReview: vi.fn(),
  confirmMappingRecheck: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function card(overrides: Partial<ReviewLink> = {}): ReviewLink {
  return {
    id: 'l1',
    stage: 'first',
    status: 'suggested',
    source: 'ai',
    accept_method: null,
    confidence: 0.93,
    coverage: 4,
    depth_match: 'matches',
    rationale: 'Taking a history is a direct example.',
    evidence_quote: 'focused history',
    needs_recheck: false,
    needs_discussion: false,
    first_decision: null,
    version_id: 'v2027',
    academic_year: 2027,
    objective: {
      id: 'o1',
      text: 'Take a focused history from a patient.',
      level: 'module',
      module_code: 'HSC201',
      module_name: 'Cardiovascular system',
      learning_event_title: null,
    },
    item: {
      id: 'ia',
      code: 'DGC 2.1',
      title: 'Gathers information',
      group: 'DGC 2 Communication',
      framework_id: 'f1',
      framework_name: 'Demo Graduate Competencies',
      framework_version_label: '1.0',
    },
    ...overrides,
  };
}

const second = card({
  id: 'l2',
  confidence: 0.81,
  coverage: 3,
  depth_match: 'below',
  rationale: 'Explains but does not apply.',
  evidence_quote: '',
  objective: {
    id: 'o2',
    text: 'Explain the cardiac cycle.',
    level: 'module',
    module_code: 'HSC201',
    module_name: 'Cardiovascular system',
    learning_event_title: 'Lecture 4',
  },
  item: { ...card().item, id: 'ib', code: 'DGC 1.2', title: 'Applies science' },
});

function queue(items: ReviewLink[], overrides: Partial<ReviewQueue> = {}): ReviewQueue {
  return {
    stage: 'first',
    total: items.length,
    offset: 0,
    limit: 50,
    items,
    progress: { total: 12, accepted: 6, rejected: 2, second_review: 1, waiting: 3 },
    counts: { first: items.length, second: 1, recheck: 0, waiting: items.length + 1, total: items.length + 1 },
    facets: {
      versions: [{ id: 'v2027', programme_name: 'BSc Health Sciences (Demo)', academic_year: 2027 }],
      frameworks: [{ id: 'f1', name: 'Demo Graduate Competencies', version_label: '1.0' }],
      modules: [
        { id: 'm1', code: 'HSC201', name: 'Cardiovascular system' },
        { id: 'm2', code: 'HSC205', name: 'Community health' },
      ],
    },
    four_eyes: false,
    bulk_min_confidence: 0.8,
    bulk_max_links: 200,
    ...overrides,
  };
}

function signIn(permissions = ['curriculum.view', 'mapping.review']) {
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue([role('r', permissions)]);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
}

function serve(byStage: Partial<Record<ReviewStage, ReviewQueue>>) {
  mocked.fetchReviewQueue.mockImplementation(async (params) => {
    return byStage[params.stage] ?? queue([], { stage: params.stage });
  });
}

describe('review queue', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    signIn();
    mocked.fetchReviewCount.mockResolvedValue({ first: 2, second: 1, recheck: 0, waiting: 3, total: 3 });
    serve({ first: queue([card(), second]) });
  });

  it('lists the suggestions with progress, evidence, reasoning and the sidebar count', async () => {
    renderAt('/mapping/review');

    expect(await screen.findByRole('heading', { level: 1, name: 'Review queue' })).toBeInTheDocument();
    expect(await screen.findByText('9 of 12 suggestions reviewed')).toBeInTheDocument();
    const list = within(screen.getByRole('region', { name: 'Suggestions' }));
    expect(list.getAllByRole('listitem')).toHaveLength(2);
    expect(list.getByText('93%')).toBeInTheDocument();
    const detail = within(screen.getByRole('region', { name: 'Selected suggestion' }));
    expect(detail.getByText('Why the AI suggested it')).toBeInTheDocument();
    expect(detail.getByText('Taking a history is a direct example.')).toBeInTheDocument();
    expect(detail.getByText('focused history').tagName).toBe('MARK');
    expect(detail.getByText('Demo Graduate Competencies › DGC 2 Communication')).toBeInTheDocument();
    expect(detail.getByLabelText('4: 61 to 80%')).toBeChecked();
    expect(detail.getByLabelText('Matches')).toBeChecked();
    // The menu shows what waits, and says so in words too.
    await waitFor(() => expect(screen.getByText('3 suggestions waiting')).toBeInTheDocument());
  });

  it('accepts with A, sends the chosen values and moves to the next suggestion', async () => {
    mocked.reviewMappingLink.mockResolvedValue({ id: 'l1', status: 'accepted', needs_discussion: false });
    renderAt('/mapping/review');
    const first = await screen.findByRole('button', { name: /Take a focused history/ });
    first.focus();

    fireEvent.keyDown(first, { key: 'a' });

    await waitFor(() =>
      expect(mocked.reviewMappingLink).toHaveBeenCalledWith('l1', {
        decision: 'accept',
        expected_status: 'suggested',
        coverage: 4,
        depth_match: 'matches',
      })
    );
    expect(await screen.findByText(/Accepted the link to DGC 2.1 Gathers information\./)).toBeInTheDocument();
    // The next suggestion is selected, and the list was asked for again.
    expect(
      within(screen.getByRole('region', { name: 'Selected suggestion' })).getByText(
        'Explain the cardiac cycle.'
      )
    ).toBeInTheDocument();
    await waitFor(() => expect(mocked.fetchReviewQueue.mock.calls.length).toBeGreaterThan(1));
  });

  it('rejects with R and asks for a second review with 2', async () => {
    mocked.reviewMappingLink.mockResolvedValueOnce({ id: 'l1', status: 'rejected', needs_discussion: false });
    mocked.reviewMappingLink.mockResolvedValueOnce({
      id: 'l2',
      status: 'needs_second_review',
      needs_discussion: false,
    });
    renderAt('/mapping/review');
    const first = await screen.findByRole('button', { name: /Take a focused history/ });
    fireEvent.keyDown(first, { key: 'r' });
    await waitFor(() =>
      expect(mocked.reviewMappingLink).toHaveBeenCalledWith('l1', {
        decision: 'reject',
        expected_status: 'suggested',
      })
    );
    expect(await screen.findByText('Rejected the link to DGC 2.1 Gathers information.')).toBeInTheDocument();

    const next = screen.getByRole('button', { name: /Explain the cardiac cycle/ });
    fireEvent.keyDown(next, { key: '2' });
    await waitFor(() =>
      expect(mocked.reviewMappingLink).toHaveBeenLastCalledWith('l2', {
        decision: 'second_review',
        expected_status: 'suggested',
      })
    );
    expect(await screen.findByText(/Sent the link to DGC 1.2 Applies science to a second review\./)).toBeInTheDocument();
  });

  it('edits and accepts: E moves focus to the coverage, and the new values are sent', async () => {
    mocked.reviewMappingLink.mockResolvedValue({ id: 'l1', status: 'accepted', needs_discussion: false });
    renderAt('/mapping/review');
    const first = await screen.findByRole('button', { name: /Take a focused history/ });

    fireEvent.keyDown(first, { key: 'e' });
    expect(screen.getByLabelText('4: 61 to 80%')).toHaveFocus();
    fireEvent.click(screen.getByLabelText('2: 21 to 40%'));
    fireEvent.click(screen.getByLabelText('Above'));
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));

    await waitFor(() =>
      expect(mocked.reviewMappingLink).toHaveBeenCalledWith('l1', {
        decision: 'accept',
        expected_status: 'suggested',
        coverage: 2,
        depth_match: 'above',
      })
    );
  });

  it('skips with S without saving anything', async () => {
    renderAt('/mapping/review');
    const first = await screen.findByRole('button', { name: /Take a focused history/ });

    fireEvent.keyDown(first, { key: 's' });

    expect(
      within(screen.getByRole('region', { name: 'Selected suggestion' })).getByText(
        'Explain the cardiac cycle.'
      )
    ).toBeInTheDocument();
    expect(mocked.reviewMappingLink).not.toHaveBeenCalled();
  });

  it('does not treat typing, modifiers or other keys as shortcuts', async () => {
    renderAt('/mapping/review');
    const first = await screen.findByRole('button', { name: /Take a focused history/ });

    fireEvent.keyDown(first, { key: 'a', ctrlKey: true });
    fireEvent.keyDown(first, { key: 'a', altKey: true });
    fireEvent.keyDown(first, { key: 'x' });
    // A shortcut key typed into a filter (outside the list and details) does nothing.
    fireEvent.keyDown(screen.getByLabelText('Confidence'), { key: 'a' });

    expect(mocked.reviewMappingLink).not.toHaveBeenCalled();
  });

  it('can switch the shortcuts off, and remembers the choice', async () => {
    renderAt('/mapping/review');
    const first = await screen.findByRole('button', { name: /Take a focused history/ });
    expect(screen.getByRole('list', { name: 'Available shortcuts' })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Use keyboard shortcuts'));
    fireEvent.keyDown(first, { key: 'a' });

    expect(mocked.reviewMappingLink).not.toHaveBeenCalled();
    expect(screen.getByText(/Keyboard shortcuts are off\. Every action is also a button\./)).toBeInTheDocument();
    expect(window.localStorage.getItem('cic.review.shortcuts')).toBe('off');
    // The buttons still work.
    mocked.reviewMappingLink.mockResolvedValue({ id: 'l1', status: 'accepted', needs_discussion: false });
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await waitFor(() => expect(mocked.reviewMappingLink).toHaveBeenCalledTimes(1));
  });

  it('does not accept a link without coverage and depth', async () => {
    serve({ first: queue([card({ coverage: null, depth_match: null })]) });
    renderAt('/mapping/review');
    await screen.findByRole('region', { name: 'Selected suggestion' });

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));

    expect(await screen.findByText('Choose a coverage and a depth before accepting.')).toBeInTheDocument();
    expect(mocked.reviewMappingLink).not.toHaveBeenCalled();
  });

  it('shows a suggestion made by a person without a confidence score', async () => {
    serve({
      first: queue([card({ source: 'human', confidence: null, evidence_quote: '', rationale: '' })]),
    });
    renderAt('/mapping/review');

    const detail = within(await screen.findByRole('region', { name: 'Selected suggestion' }));
    expect(detail.getByText('Why this link was suggested')).toBeInTheDocument();
    expect(detail.getByText('No reason was given.')).toBeInTheDocument();
    expect(detail.getByText('Suggested by a person, no confidence score')).toBeInTheDocument();
    expect(detail.queryByText(/highlighted words/)).not.toBeInTheDocument();
  });

  it('explains the second review when this institution requires one', async () => {
    serve({ first: queue([card()], { four_eyes: true }) });
    mocked.reviewMappingLink.mockResolvedValue({
      id: 'l1',
      status: 'needs_second_review',
      needs_discussion: false,
    });
    renderAt('/mapping/review');

    expect(await screen.findByText(/accepting sends the link to a second reviewer/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(
      await screen.findByText(/Accepted the link to DGC 2.1 Gathers information\. It now waits for a second reviewer\./)
    ).toBeInTheDocument();
  });

  it('shows the second-review pile with what the first reviewer decided, and no second-review button', async () => {
    serve({
      first: queue([card()]),
      second: queue([card({ id: 'l3', stage: 'second', status: 'needs_second_review', first_decision: 'accept' })], {
        stage: 'second',
      }),
    });
    renderAt('/mapping/review');
    await screen.findByRole('region', { name: 'Selected suggestion' });

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'second' } });

    expect(await screen.findByText(/The first reviewer accepted this link\./)).toBeInTheDocument();
    expect(screen.getByText(/You are the second reviewer/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Second review' })).not.toBeInTheDocument();
    expect(mocked.fetchReviewQueue).toHaveBeenLastCalledWith(
      expect.objectContaining({ stage: 'second', offset: 0 })
    );
    mocked.reviewMappingLink.mockResolvedValue({ id: 'l3', status: 'accepted', needs_discussion: false });
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await waitFor(() =>
      expect(mocked.reviewMappingLink).toHaveBeenCalledWith(
        'l3',
        expect.objectContaining({ decision: 'accept', expected_status: 'needs_second_review' })
      )
    );
  });

  it('lists accepted links whose wording changed and confirms that they still fit', async () => {
    serve({
      first: queue([card()]),
      recheck: queue(
        [card({ id: 'l4', stage: 'recheck', status: 'accepted', needs_recheck: true, source: 'human', confidence: null })],
        { stage: 'recheck' }
      ),
    });
    mocked.confirmMappingRecheck.mockResolvedValue({} as never);
    renderAt('/mapping/review');
    await screen.findByRole('region', { name: 'Selected suggestion' });

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'recheck' } });

    expect(await screen.findByText(/The objective's wording changed after this link was accepted/)).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    const still = screen.getByRole('button', { name: 'Still fits' });
    fireEvent.keyDown(still, { key: 'a' });
    await waitFor(() => expect(mocked.confirmMappingRecheck).toHaveBeenCalledWith('l4'));
    expect(screen.getByRole('link', { name: 'Open in the mapping workspace' })).toHaveAttribute(
      'href',
      '/mapping/v2027?objective=o1&framework=f1&item=ia'
    );
  });

  it('labels a bulk-accepted link in words, in the list and in the details', async () => {
    serve({
      first: queue([card()]),
      recheck: queue(
        [
          card({
            id: 'l5',
            stage: 'recheck',
            status: 'accepted',
            needs_recheck: true,
            accept_method: 'bulk',
          }),
        ],
        { stage: 'recheck' }
      ),
    });
    renderAt('/mapping/review');
    await screen.findByRole('region', { name: 'Selected suggestion' });

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'recheck' } });

    expect(await screen.findByText('Accepted in bulk')).toBeInTheDocument();
    expect(screen.getByText(/accepted in a bulk action and no person has looked at it/)).toBeInTheDocument();
  });

  it('says so when a link moved on and refreshes the list', async () => {
    mocked.reviewMappingLink.mockRejectedValue(new ApiError(409, 'changed'));
    renderAt('/mapping/review');
    const first = await screen.findByRole('button', { name: /Take a focused history/ });

    fireEvent.keyDown(first, { key: 'a' });

    expect(await screen.findByText(/This link changed while you were looking at it/)).toBeInTheDocument();
    await waitFor(() => expect(mocked.fetchReviewQueue.mock.calls.length).toBeGreaterThan(1));
  });

  it('accepts the confident ones together after counting them', async () => {
    mocked.bulkAcceptReview.mockImplementation(async (request) =>
      request.dry_run
        ? { eligible: 7, processed: 0, remaining: 7, status_after: 'accepted', dry_run: true }
        : { eligible: 7, processed: 7, remaining: 0, status_after: 'accepted', dry_run: false }
    );
    renderAt('/mapping/review');
    fireEvent.click(await screen.findByRole('button', { name: 'Accept all 90% and above' }));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('7 suggestions at 90% and above will be accepted.')).toBeInTheDocument();
    expect(mocked.bulkAcceptReview).toHaveBeenCalledWith({ min_confidence: 0.9, dry_run: true });
    expect(within(dialog).getByText(/Second reviews and links to re-check are never accepted in bulk/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept 7 suggestions' }));

    await waitFor(() =>
      expect(mocked.bulkAcceptReview).toHaveBeenCalledWith({ min_confidence: 0.9, dry_run: false })
    );
    expect(await screen.findByText('Accepted 7 suggestions at 90% confidence and above.')).toBeInTheDocument();
  });

  it('offers the institution floor first, then the usual steps above it', async () => {
    mocked.bulkAcceptReview.mockResolvedValue({
      eligible: 3,
      processed: 0,
      remaining: 3,
      status_after: 'accepted',
      dry_run: true,
    });
    serve({ first: queue([card()], { bulk_min_confidence: 0.82, bulk_max_links: 50 }) });
    renderAt('/mapping/review');
    fireEvent.click(await screen.findByRole('button', { name: 'Accept all 90% and above' }));

    const dialog = await screen.findByRole('dialog');
    const options = within(dialog)
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(options).toEqual(['82% and above', '85% and above', '90% and above', '95% and above']);
    expect(within(dialog).getByText(/At most 50 are handled at a time/)).toBeInTheDocument();
  });

  it('starts at the floor when the floor is above 90%', async () => {
    mocked.bulkAcceptReview.mockResolvedValue({
      eligible: 0,
      processed: 0,
      remaining: 0,
      status_after: 'accepted',
      dry_run: true,
    });
    serve({ first: queue([card()], { bulk_min_confidence: 0.95 }) });
    renderAt('/mapping/review');

    fireEvent.click(await screen.findByRole('button', { name: 'Accept all 95% and above' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getAllByRole('option').map((o) => o.textContent)).toEqual(['95% and above']);
  });

  it('offers nothing to accept when no suggestion is confident enough', async () => {
    mocked.bulkAcceptReview.mockResolvedValue({
      eligible: 0,
      processed: 0,
      remaining: 0,
      status_after: 'accepted',
      dry_run: true,
    });
    renderAt('/mapping/review');
    fireEvent.click(await screen.findByRole('button', { name: 'Accept all 90% and above' }));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('No waiting suggestion is at 90% or above.')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: /^Accept \d/ })).not.toBeInTheDocument();
  });

  it('says in words that a bulk accept still needs a second reviewer in four-eyes mode', async () => {
    serve({ first: queue([card()], { four_eyes: true }) });
    mocked.bulkAcceptReview.mockResolvedValue({
      eligible: 2,
      processed: 0,
      remaining: 2,
      status_after: 'needs_second_review',
      dry_run: true,
    });
    renderAt('/mapping/review');
    fireEvent.click(await screen.findByRole('button', { name: 'Accept all 90% and above' }));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText(/sent to a second reviewer and counts only once they agree/)).toBeInTheDocument();
  });

  it('filters by confidence and module through the server', async () => {
    renderAt('/mapping/review');
    await screen.findByRole('region', { name: 'Selected suggestion' });

    fireEvent.change(screen.getByLabelText('Confidence'), { target: { value: 'high' } });
    await waitFor(() =>
      expect(mocked.fetchReviewQueue).toHaveBeenLastCalledWith(
        expect.objectContaining({ minConfidence: 0.9, maxConfidence: undefined })
      )
    );
    fireEvent.change(screen.getByLabelText('Confidence'), { target: { value: 'low' } });
    await waitFor(() =>
      expect(mocked.fetchReviewQueue).toHaveBeenLastCalledWith(
        expect.objectContaining({ minConfidence: undefined, maxConfidence: 0.65 })
      )
    );
    fireEvent.change(screen.getByLabelText('Course'), { target: { value: 'm2' } });
    await waitFor(() =>
      expect(mocked.fetchReviewQueue).toHaveBeenLastCalledWith(expect.objectContaining({ moduleId: 'm2' }))
    );
  });

  it('shows an empty state when nothing ever waited', async () => {
    serve({
      first: queue([], {
        progress: { total: 0, accepted: 0, rejected: 0, second_review: 0, waiting: 0 },
        counts: { first: 0, second: 0, recheck: 0, waiting: 0, total: 0 },
      }),
    });
    mocked.fetchReviewCount.mockResolvedValue({ first: 0, second: 0, recheck: 0, waiting: 0, total: 0 });
    renderAt('/mapping/review');

    expect(await screen.findByRole('heading', { name: 'Nothing to review' })).toBeInTheDocument();
    expect(screen.queryByText(/waiting$/)).not.toBeInTheDocument();
  });

  it('shows a plain error with a retry when the queue cannot be loaded', async () => {
    mocked.fetchReviewQueue.mockRejectedValueOnce(new ApiError(500, 'boom'));
    renderAt('/mapping/review');

    expect(await screen.findByText('The review queue could not be loaded')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('region', { name: 'Selected suggestion' })).toBeInTheDocument();
  });

  it('is not shown to people who cannot review', async () => {
    signIn(['curriculum.view']);
    renderAt('/mapping/review');

    expect(await screen.findByText('No access')).toBeInTheDocument();
    expect(mocked.fetchReviewQueue).not.toHaveBeenCalled();
    expect(mocked.fetchReviewCount).not.toHaveBeenCalled();
  });
});

describe('shortcutFor', () => {
  const press = (key: string, extra: Partial<KeyboardEvent> = {}) => ({
    key,
    ctrlKey: false,
    altKey: false,
    metaKey: false,
    shiftKey: false,
    repeat: false,
    ...extra,
  });

  it('maps the five keys', () => {
    expect(shortcutFor(press('a'), null)).toBe('accept');
    expect(shortcutFor(press('R'), null)).toBe('reject');
    expect(shortcutFor(press('e'), null)).toBe('edit');
    expect(shortcutFor(press('s'), null)).toBe('skip');
    expect(shortcutFor(press('2'), null)).toBe('second');
    expect(shortcutFor(press('x'), null)).toBeNull();
  });

  it('ignores modifiers, repeats and text fields', () => {
    expect(shortcutFor(press('a', { ctrlKey: true }), null)).toBeNull();
    expect(shortcutFor(press('a', { metaKey: true }), null)).toBeNull();
    expect(shortcutFor(press('a', { repeat: true }), null)).toBeNull();
    expect(shortcutFor(press('a'), document.createElement('textarea'))).toBeNull();
    expect(shortcutFor(press('a'), document.createElement('select'))).toBeNull();
    const text = document.createElement('input');
    expect(shortcutFor(press('a'), text)).toBeNull();
    const radio = document.createElement('input');
    radio.type = 'radio';
    expect(shortcutFor(press('a'), radio)).toBe('accept');
    expect(shortcutFor(press('a'), document.createElement('button'))).toBe('accept');
  });
});
