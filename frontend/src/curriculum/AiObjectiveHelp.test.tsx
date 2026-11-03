import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { AiObjectiveResult, StructureModule } from '../api/types';
import { createQueryClient } from '../queryClient';
import { ThemeProvider } from '../theme/ThemeProvider';
import { AiObjectiveHelp } from './AiObjectiveHelp';
import type { ObjectiveOwner } from './editing';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  suggestForObjective: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const owner: ObjectiveOwner = {
  kind: 'module',
  module: { id: 'm1' } as StructureModule,
};

function result(overrides: Partial<AiObjectiveResult>): AiObjectiveResult {
  return {
    task: 'rewrite',
    run_id: 'run-1',
    rewrite: null,
    classification: null,
    ...overrides,
  };
}

function show(text = 'Understand the cardiac cycle.') {
  const onUseText = vi.fn();
  const onUseClassification = vi.fn();
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <AiObjectiveHelp
          owner={owner}
          versionId="v1"
          text={text}
          domain={null}
          taxonomyLevelId={null}
          hasLinks={false}
          onUseText={onUseText}
          onUseClassification={onUseClassification}
        />
      </ThemeProvider>
    </QueryClientProvider>
  );
  return { onUseText, onUseClassification };
}

describe('AI help under the wording field', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('says what is sent and cannot be pressed before there is wording', () => {
    show('   ');

    const group = screen.getByRole('group', { name: 'AI help with this wording' });
    expect(within(group).getByText(/Only the wording above/)).toBeInTheDocument();
    expect(within(group).getByRole('button', { name: 'Suggest a measurable rewrite' })).toBeDisabled();
    expect(within(group).getByRole('button', { name: 'Suggest domain and level' })).toBeDisabled();
  });

  it('shows a rewrite as a comparison and uses it only when asked', async () => {
    mocked.suggestForObjective.mockResolvedValue(
      result({
        rewrite: {
          text: 'Describe the cardiac cycle.',
          rationale: 'Replaced a vague verb with a measurable one.',
          unchanged: false,
        },
      })
    );
    const { onUseText } = show();

    fireEvent.click(screen.getByRole('button', { name: 'Suggest a measurable rewrite' }));

    expect(await screen.findByText('Suggested rewrite')).toBeInTheDocument();
    expect(mocked.suggestForObjective).toHaveBeenCalledWith('/modules/m1/outcome-ai', {
      task: 'rewrite',
      text: 'Understand the cardiac cycle.',
      domain: null,
      taxonomy_level_id: null,
      has_parent_links: false,
    });
    // Removed and added words are in real <del> and <ins> elements, with words for screen readers.
    const removed = document.querySelector('del');
    const added = document.querySelector('ins');
    expect(removed).toHaveTextContent('Removed: Understand');
    expect(added).toHaveTextContent('Added: Describe');
    expect(screen.getByText(/Why: Replaced a vague verb/)).toBeInTheDocument();
    expect(onUseText).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Use this wording' }));

    expect(onUseText).toHaveBeenCalledWith('Describe the cardiac cycle.');
    await waitFor(() => expect(screen.queryByText('Suggested rewrite')).not.toBeInTheDocument());
  });

  it('says so when the wording is already measurable', async () => {
    mocked.suggestForObjective.mockResolvedValue(
      result({
        rewrite: { text: 'Describe the heart.', rationale: 'Already measurable.', unchanged: true },
      })
    );
    show('Describe the heart.');

    fireEvent.click(screen.getByRole('button', { name: 'Suggest a measurable rewrite' }));

    expect(await screen.findByText(/already measurable and suggests no change/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Use this wording' })).not.toBeInTheDocument();
  });

  it('can be dismissed', async () => {
    mocked.suggestForObjective.mockResolvedValue(
      result({ rewrite: { text: 'Name the bones.', rationale: 'Shorter.', unchanged: false } })
    );
    const { onUseText } = show('Know the bones.');
    fireEvent.click(screen.getByRole('button', { name: 'Suggest a measurable rewrite' }));
    await screen.findByText('Suggested rewrite');

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    await waitFor(() => expect(screen.queryByText('Suggested rewrite')).not.toBeInTheDocument());
    expect(onUseText).not.toHaveBeenCalled();
  });

  it('suggests a domain and a level, with the reason and the confidence', async () => {
    mocked.suggestForObjective.mockResolvedValue(
      result({
        task: 'classify',
        classification: {
          domain: 'skill',
          taxonomy_level_id: 'l-apply',
          taxonomy_level_name: 'Apply',
          scale_name: 'Bloom',
          confidence: '0.8',
          rationale: 'It asks for a performance.',
        },
      })
    );
    const { onUseClassification } = show('Measure blood pressure.');

    fireEvent.click(screen.getByRole('button', { name: 'Suggest domain and level' }));

    expect(await screen.findByText('Suggested domain and level')).toBeInTheDocument();
    expect(screen.getByText('Domain: Skill')).toBeInTheDocument();
    expect(screen.getByText('Level: Apply (Bloom)')).toBeInTheDocument();
    expect(screen.getByText("The AI's confidence: 80%.")).toBeInTheDocument();
    expect(screen.getByText(/Why: It asks for a performance/)).toBeInTheDocument();
    expect(onUseClassification).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Use these' }));

    expect(onUseClassification).toHaveBeenCalledWith({ domain: 'skill', taxonomyLevelId: 'l-apply' });
  });

  it('offers nothing to use when the AI is not sure', async () => {
    mocked.suggestForObjective.mockResolvedValue(
      result({
        task: 'classify',
        classification: {
          domain: null,
          taxonomy_level_id: null,
          taxonomy_level_name: null,
          scale_name: null,
          confidence: '0.2',
          rationale: 'Unclear.',
        },
      })
    );
    show('Be a good colleague.');

    fireEvent.click(screen.getByRole('button', { name: 'Suggest domain and level' }));

    expect(await screen.findByText('Domain: not sure')).toBeInTheDocument();
    expect(screen.getByText('Level: not sure')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Use these' })).not.toBeInTheDocument();
  });

  it.each([
    [new ApiError(409, 'AI is switched off. Choose a provider in Admin > AI settings.'), /AI is switched off/],
    [new ApiError(403, 'no'), /do not have permission/],
    [new ApiError(429, 'slow'), /Too many requests/],
    [new ApiError(502, 'bad'), /did not give a usable answer/],
    [new ApiError(500, 'boom'), /Something went wrong/],
  ])('says in words why nothing came back: %s', async (error, message) => {
    mocked.suggestForObjective.mockRejectedValue(error);
    show();

    fireEvent.click(screen.getByRole('button', { name: 'Suggest a measurable rewrite' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
  });
});
