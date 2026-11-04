import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type { EvalDetail, EvalRun, EvalScores, GoldSet } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { decimal, percent } from './evaluationFormat';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchGoldSets: vi.fn(),
  fetchFrameworkLibrary: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchEvaluations: vi.fn(),
  fetchEvaluation: vi.fn(),
  uploadGoldSet: vi.fn(),
  deleteGoldSet: vi.fn(),
  startEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const gold: GoldSet = {
  id: 'g1',
  name: 'Demo gold set (fictional)',
  description: '',
  framework_id: 'f1',
  framework_name: 'Demo Graduate Competencies',
  is_demo: true,
  objectives: 60,
  mappings: 70,
  without_mapping: 10,
  created_at: '2026-11-04T10:00:00Z',
};

function scores(overrides: Partial<EvalScores> = {}): EvalScores {
  return {
    counts: { tp: 40, fp: 10, fn: 20, tn: 90, total: 160 },
    precision: 0.8,
    recall: 0.6667,
    f1: 0.7273,
    kappa: 0.6123,
    shortlist_recall: 1,
    coverage_gap: 0.5,
    coverage_kappa: 0.52,
    coverage_kappa_weighted: 0.71,
    coverage_pairs: 40,
    coverage_within_one: 0.9,
    depth_agreement: 0.8,
    objectives: 60,
    failed: 0,
    suggestions: 50,
    average_shortlist: 6,
    ...overrides,
  };
}

function run(overrides: Partial<EvalRun> = {}): EvalRun {
  return {
    id: 'r1',
    gold_set_id: 'g1',
    gold_set_name: gold.name,
    version_id: 'v1',
    status: 'succeeded',
    prompt_version: 'mapping:2',
    provider: 'anthropic',
    model: 'claude-sonnet-5-5',
    top_k: 10,
    total_items: 60,
    done_items: 60,
    failed_items: 0,
    not_found: 0,
    input_tokens: 1000,
    output_tokens: 500,
    estimated_cost: '0.1234',
    error_message: null,
    created_at: '2026-11-04T10:30:00Z',
    finished_at: '2026-11-04T10:40:00Z',
    scores: scores(),
    ...overrides,
  };
}

const detail: EvalDetail = {
  ...run(),
  min_coverage: 1,
  prefer_specific: true,
  by_min_coverage: [1, 2, 3, 4, 5].map((n) => ({
    ...scores({ suggestions: 60 - n * 8, precision: 0.7 + n * 0.05 }),
    min_coverage: n,
  })),
  bulk_accept: [50, 80, 100].map((floor) => ({
    floor,
    accepted: 50 - floor / 4,
    right: 40,
    wrong: floor === 50 ? 10 : 0,
    precision: floor === 50 ? 0.8 : 1,
    left_for_review: floor / 4,
    left_right: 0,
    recall: 0.5,
  })),
  disagreements: [
    {
      case_id: 'c1',
      objective: 'Practise safely.',
      agreed: [],
      only_ai: ['HYG1'],
      only_gold: ['ETH1'],
      not_shown: ['ETH1'],
    },
  ],
};

/** Mantine's file input keeps the real <input type="file"> hidden. */
function chooseFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['x'], 'gold.xlsx')] } });
}

describe('evaluation figures as text', () => {
  it('shows a share as a percentage and a dash where it cannot be worked out', () => {
    expect(percent(0.8)).toBe('80.0%');
    expect(percent(null)).toBe('–');
    expect(decimal(0.6123)).toBe('0.61');
    expect(decimal(undefined)).toBe('–');
  });
});

describe('AI evaluation page', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('platform_admin', ['settings.manage'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchGoldSets.mockResolvedValue([gold]);
    mocked.fetchFrameworkLibrary.mockResolvedValue({
      frameworks: [
        {
          id: 'f1',
          key: 'dgc',
          name: 'Demo Graduate Competencies',
          version_label: '1.0.0',
          status: 'active',
        } as never,
      ],
      can_manage: true,
    });
    mocked.fetchProgrammes.mockResolvedValue([
      {
        id: 'p1',
        code: 'BHS',
        name: 'BSc',
        faculty_id: 'x',
        faculty_name: 'x',
        status: 'active',
        versions: [
          {
            id: 'v1',
            academic_year: 2026,
            status: 'draft',
            published_at: null,
            based_on_id: null,
          },
        ],
      },
    ]);
    mocked.fetchEvaluations.mockResolvedValue([run()]);
    mocked.fetchEvaluation.mockResolvedValue(detail);
  });

  it('is linked from the admin page and refused to people without the permission', async () => {
    renderAt('/admin');
    expect(await screen.findByRole('link', { name: "Check the AI's mapping" })).toHaveAttribute(
      'href',
      '/admin/ai-evaluation'
    );

    mocked.fetchMyRoles.mockResolvedValue([role('student', [])]);
    renderAt('/admin/ai-evaluation');
    expect(await screen.findAllByText(/permission|access/i)).not.toHaveLength(0);
  });

  it('warns that the figures are only as good as the answer key', async () => {
    renderAt('/admin/ai-evaluation');

    expect(await screen.findByText('Read these figures with care')).toBeInTheDocument();
    expect(screen.getByText(/only as good as the answer key/)).toBeInTheDocument();
  });

  it('lists gold sets with the fictional demo marked, and offers the template', async () => {
    renderAt('/admin/ai-evaluation');

    const row = (await screen.findByText('Fictional demo')).closest('tr') as HTMLElement;
    expect(within(row).getByText(/Demo gold set \(fictional\)/)).toBeInTheDocument();
    expect(within(row).getByText('60 (10 map to nothing)')).toBeInTheDocument();
    expect(within(row).getByRole('link', { name: 'Download' })).toHaveAttribute(
      'href',
      '/api/v1/ai/evaluation/gold-sets/g1/export'
    );
    expect(screen.getByRole('link', { name: /Download the Excel template/ })).toHaveAttribute(
      'href',
      '/api/v1/ai/evaluation/gold-template?framework_id=f1'
    );
  });

  it('checks a file first, lists every problem with its row, and does not offer to save', async () => {
    mocked.uploadGoldSet.mockResolvedValue({
      objectives: 3,
      mappings: 2,
      without_mapping: 1,
      problems: [
        { row: 3, message: 'The coverage must be a whole number 0 to 5.' },
        { row: 7, message: 'The framework has no item with the code NOPE.' },
      ],
      saved: null,
    });
    renderAt('/admin/ai-evaluation');
    await screen.findByText('Fictional demo');

    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Mine' } });
    chooseFile();
    fireEvent.click(await screen.findByRole('button', { name: 'Check the file' }));

    expect(await screen.findByText(/Row 3: The coverage must be/)).toBeInTheDocument();
    expect(screen.getByText(/Row 7: The framework has no item/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save the gold set' })).not.toBeInTheDocument();
    expect(mocked.uploadGoldSet).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Mine', frameworkId: 'f1', dryRun: true })
    );
  });

  it('saves a sound file after it was checked', async () => {
    mocked.uploadGoldSet
      .mockResolvedValueOnce({
        objectives: 3,
        mappings: 2,
        without_mapping: 1,
        problems: [],
        saved: null,
      })
      .mockResolvedValueOnce({
        objectives: 3,
        mappings: 2,
        without_mapping: 1,
        problems: [],
        saved: { ...gold, id: 'g2', name: 'Mine', is_demo: false },
      });
    renderAt('/admin/ai-evaluation');
    await screen.findByText('Fictional demo');
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Mine' } });
    chooseFile();
    fireEvent.click(await screen.findByRole('button', { name: 'Check the file' }));

    fireEvent.click(await screen.findByRole('button', { name: 'Save the gold set' }));

    expect(await screen.findByText('Saved the gold set Mine.')).toBeInTheDocument();
    expect(mocked.uploadGoldSet).toHaveBeenLastCalledWith(
      expect.objectContaining({ dryRun: false })
    );
  });

  it('starts an evaluation on the chosen gold set and version', async () => {
    mocked.startEvaluation.mockResolvedValue(run({ status: 'queued', scores: null }));
    renderAt('/admin/ai-evaluation');
    await screen.findByText('Fictional demo');

    fireEvent.click(screen.getByRole('button', { name: 'Run the evaluation' }));

    await waitFor(() =>
      expect(mocked.startEvaluation).toHaveBeenCalledWith({ goldSetId: 'g1', versionId: 'v1' })
    );
    expect(await screen.findByText(/The evaluation has started/)).toBeInTheDocument();
  });

  it('says why an evaluation was refused', async () => {
    const { ApiError } = await import('../api/client');
    mocked.startEvaluation.mockRejectedValue(
      new ApiError(409, 'AI is turned off. An administrator can turn it on.')
    );
    renderAt('/admin/ai-evaluation');
    await screen.findByText('Fictional demo');

    fireEvent.click(screen.getByRole('button', { name: 'Run the evaluation' }));

    expect(await screen.findByText(/AI is turned off/)).toBeInTheDocument();
  });

  it('compares prompt versions and models and opens the figures of one run', async () => {
    mocked.fetchEvaluations.mockResolvedValue([
      run(),
      run({ id: 'r2', prompt_version: 'mapping:1', scores: scores({ precision: 0.5, kappa: 0.31 }) }),
    ]);
    renderAt('/admin/ai-evaluation');

    const first = await screen.findByRole('button', {
      name: 'mapping:2 · claude-sonnet-5-5 · Demo gold set (fictional)',
    });
    const table = first.closest('table') as HTMLElement;
    expect(within(table).getByText('80.0%')).toBeInTheDocument();
    expect(within(table).getByText('0.61')).toBeInTheDocument();
    expect(within(table).getByText('50.0%')).toBeInTheDocument();
    expect(within(table).getAllByText('$0.1234')).toHaveLength(2);

    fireEvent.click(first);

    expect(await screen.findByRole('heading', { name: 'By minimum coverage' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Bulk accept, with a minimum coverage of 1/ })).toBeInTheDocument();
    expect(screen.getByText('Practise safely.')).toBeInTheDocument();
    expect(screen.getByText(/never shown to the AI: ETH1/)).toBeInTheDocument();
    expect(mocked.fetchEvaluation).toHaveBeenCalledWith('r1', 1);
  });

  it('works the figures again at another minimum coverage without a new run', async () => {
    renderAt('/admin/ai-evaluation');
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'mapping:2 · claude-sonnet-5-5 · Demo gold set (fictional)',
      })
    );
    await screen.findByRole('heading', { name: 'By minimum coverage' });

    fireEvent.change(screen.getByLabelText(/Count suggestions with a coverage of/), {
      target: { value: '3' },
    });

    await waitFor(() => expect(mocked.fetchEvaluations).toHaveBeenLastCalledWith(3));
    await waitFor(() => expect(mocked.fetchEvaluation).toHaveBeenLastCalledWith('r1', 3));
    expect(mocked.startEvaluation).not.toHaveBeenCalled();
  });

  it('shows progress with a cancel button while a run is going', async () => {
    mocked.fetchEvaluations.mockResolvedValue([
      run({ status: 'running', done_items: 20, scores: null }),
    ]);
    mocked.cancelEvaluation.mockResolvedValue(run({ status: 'cancelled', scores: null }));
    renderAt('/admin/ai-evaluation');

    expect(await screen.findByRole('progressbar', { name: '20 of 60 objectives' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(mocked.cancelEvaluation).toHaveBeenCalled());
    expect(mocked.cancelEvaluation.mock.calls[0][0]).toBe('r1');
  });

  it('says so when there are no evaluations yet', async () => {
    mocked.fetchEvaluations.mockResolvedValue([]);
    renderAt('/admin/ai-evaluation');

    expect(await screen.findByText('No evaluations yet.')).toBeInTheDocument();
  });
});
