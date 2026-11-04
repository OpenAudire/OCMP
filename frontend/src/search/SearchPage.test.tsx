import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type {
  ProgrammeSummary,
  SearchFilterOptions,
  SearchHit,
  SearchResponse,
  WhereTaughtResponse,
} from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { hitPath } from './hitPath';
import { filterParams, filtersFrom, hasFilters } from './searchParams';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  searchVersion: vi.fn(),
  fetchWhereTaught: vi.fn(),
  fetchSearchFilters: vi.fn(),
  fetchReviewCount: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const programmes: ProgrammeSummary[] = [
  {
    id: 'p1',
    code: 'BHS',
    name: 'BSc Health Sciences',
    faculty_id: 'f',
    faculty_name: 'F',
    status: 'active',
    versions: [
      { id: 'v1', academic_year: 2027, status: 'draft', published_at: null, based_on_id: null },
      { id: 'v0', academic_year: 2026, status: 'published', published_at: null, based_on_id: null },
    ],
  },
];

function hit(overrides: Partial<SearchHit>): SearchHit {
  return {
    kind: 'objective',
    id: 'o1',
    title: 'Describe the cardiac cycle.',
    detail: '',
    score: 0.9,
    matched_by: ['words'],
    module_id: 'm1',
    module_code: 'HSC201',
    module_name: 'Cardiology',
    phase_name: 'Year 2',
    event_id: 'e1',
    event_title: 'Cardiac cycle',
    week: 3,
    level: 'learning_event',
    domain: 'knowledge',
    framework_id: null,
    framework_name: null,
    code: null,
    ...overrides,
  };
}

function results(overrides: Partial<SearchResponse> = {}): SearchResponse {
  return {
    query: 'cardiac',
    words: 'all',
    mode: 'keyword',
    notice: 'embeddings_off',
    left_out: [],
    groups: [
      { kind: 'objective', hits: [hit({})], more: false },
      {
        kind: 'event',
        hits: [hit({ kind: 'event', id: 'e1', title: 'Cardiac cycle', matched_by: ['words', 'objective'] })],
        more: false,
      },
      { kind: 'module', hits: [], more: false },
      {
        kind: 'framework_item',
        hits: [
          hit({
            kind: 'framework_item',
            id: 'i1',
            title: 'Heart structure',
            detail: 'Describes the heart.',
            code: 'HRT1',
            framework_id: 'fw1',
            framework_name: 'Competencies',
            module_id: null,
            event_id: null,
          }),
        ],
        more: false,
      },
    ],
    ...overrides,
  };
}

const options: SearchFilterOptions = {
  phases: [{ id: 'ph1', label: 'Year 2' }],
  modules: [{ id: 'm1', label: 'HSC201 Cardiology', phase_id: 'ph1' }],
  formats: [{ id: 'fm1', label: 'Lecture' }],
  tag_lists: [{ id: 'tl1', name: 'Themes', values: [{ id: 'tv1', label: 'Ethics' }] }],
  frameworks: [{ id: 'fw1', label: 'Competencies' }],
  taxonomy_levels: [{ id: 'lv1', label: 'Bloom · Apply' }],
  domains: ['knowledge', 'skill', 'attitude'],
};

const where: WhereTaughtResponse = {
  query: 'cardiac',
  words: 'all',
  mode: 'keyword',
  notice: null,
  more: false,
  framework_items: [],
  modules: [],
  sessions: [
    {
      event_id: 'e1',
      event_title: 'Cardiac cycle',
      week: 3,
      module_id: 'm1',
      module_code: 'HSC201',
      module_name: 'Cardiology',
      phase_name: 'Year 2',
      score: 0.9,
      why: ['title', 'objective', 'framework HRT1'],
      objectives: [{ id: 'o1', text: 'Describe the cardiac cycle.', level: 'learning_event', score: 0.9, via: 'objective' }],
    },
  ],
};

describe('search addresses', () => {
  it('opens each kind of hit where it lives', () => {
    expect(hitPath('v1', hit({ kind: 'event', id: 'e9' }))).toBe('/curriculum/versions/v1?item=event%3Ae9');
    expect(hitPath('v1', hit({ kind: 'module', id: 'm9' }))).toBe('/curriculum/versions/v1?item=module%3Am9');
    expect(hitPath('v1', hit({}))).toBe('/curriculum/versions/v1?item=event%3Ae1');
    expect(hitPath('v1', hit({ event_id: null }))).toBe('/curriculum/versions/v1?item=module%3Am1');
    expect(hitPath('v1', hit({ event_id: null, module_id: null }))).toBe(
      '/curriculum/versions/v1?item=programme'
    );
    expect(hitPath('v1', hit({ kind: 'framework_item', id: 'i1', framework_id: 'fw1' }))).toBe(
      '/frameworks/fw1?item=i1'
    );
  });

  it('keeps the filters in the address and names them as the API has them', () => {
    const filters = filtersFrom(new URLSearchParams('q=x&module=m1&domain=skill&level=lv1'));

    expect(filters).toEqual({ module: 'm1', domain: 'skill', level: 'lv1' });
    expect(hasFilters(filters)).toBe(true);
    expect(hasFilters({})).toBe(false);
    expect(filterParams(filters)).toEqual({
      module_id: 'm1',
      domain: 'skill',
      taxonomy_level_id: 'lv1',
    });
  });
});

describe('Search page', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('curriculum_office', ['curriculum.view'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
    mocked.fetchProgrammes.mockResolvedValue(programmes);
    mocked.searchVersion.mockResolvedValue(results());
    mocked.fetchWhereTaught.mockResolvedValue(where);
    mocked.fetchSearchFilters.mockResolvedValue(options);
  });

  it('asks for a search before it shows anything', async () => {
    renderAt('/search');

    expect(await screen.findByRole('heading', { level: 1, name: 'Search' })).toBeInTheDocument();
    expect(screen.getByText(/Type a word or a question/)).toBeInTheDocument();
    expect(mocked.searchVersion).not.toHaveBeenCalled();
  });

  it('searches the version in the address and groups the results', async () => {
    renderAt('/search?q=cardiac&version=v1');

    expect(await screen.findByRole('heading', { level: 2, name: /Objectives/ })).toBeInTheDocument();
    expect(mocked.searchVersion).toHaveBeenCalledWith('v1', 'cardiac', {});
    const objective = screen.getByRole('link', { name: 'Describe the cardiac cycle.' });
    expect(objective).toHaveAttribute('href', '/curriculum/versions/v1?item=event%3Ae1');
    expect(screen.getByText(/Year 2 · HSC201 Cardiology · Cardiac cycle · week 3/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: /Sessions/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Heart structure' })).toHaveAttribute(
      'href',
      '/frameworks/fw1?item=i1'
    );
    // A group with no hit is not shown.
    expect(screen.queryByRole('heading', { level: 2, name: /Modules/ })).not.toBeInTheDocument();
  });

  it('says why meaning-based matching is not used', async () => {
    renderAt('/search?q=cardiac&version=v1');

    expect(
      await screen.findByText(/Meaning-based search is off/)
    ).toBeInTheDocument();
  });

  it('says when no result had every word', async () => {
    mocked.searchVersion.mockResolvedValue(results({ words: 'some', notice: null }));
    renderAt('/search?q=cardiac+bones&version=v1');

    expect(await screen.findByText(/No result had all of your words/)).toBeInTheDocument();
  });

  it('says what a filter left out', async () => {
    mocked.searchVersion.mockResolvedValue(
      results({ left_out: ['event', 'module'], notice: null })
    );
    renderAt('/search?q=cardiac&version=v1&domain=skill');

    expect(await screen.findByText(/The filters leave out: sessions, modules/)).toBeInTheDocument();
    expect(mocked.searchVersion).toHaveBeenCalledWith('v1', 'cardiac', { domain: 'skill' });
  });

  it('says so when nothing is found', async () => {
    mocked.searchVersion.mockResolvedValue(
      results({ groups: [{ kind: 'objective', hits: [], more: false }], notice: null })
    );
    renderAt('/search?q=zebra&version=v1');

    expect(await screen.findByText(/Nothing found for “cardiac”|Nothing found for/)).toBeInTheDocument();
  });

  it('puts the query in the address when searched again', async () => {
    renderAt('/search?q=cardiac&version=v1');
    await screen.findByRole('heading', { level: 2, name: /Objectives/ });

    fireEvent.change(screen.getByLabelText('Search the curriculum'), { target: { value: 'ECG' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(mocked.searchVersion).toHaveBeenLastCalledWith('v1', 'ECG', {}));
  });

  it('shows where a topic is taught, in order, with why', async () => {
    renderAt('/search?q=cardiac&version=v1&view=where');

    expect(await screen.findByRole('heading', { level: 2, name: /Sessions that teach it/ })).toBeInTheDocument();
    expect(mocked.fetchWhereTaught).toHaveBeenCalledWith('v1', 'cardiac', {});
    const session = screen.getByRole('link', { name: 'Cardiac cycle' }).closest('li') as HTMLElement;
    expect(within(session).getByText(/Year 2 · HSC201 Cardiology · week 3/)).toBeInTheDocument();
    expect(within(session).getByText('Its title')).toBeInTheDocument();
    expect(within(session).getByText('An objective’s words')).toBeInTheDocument();
    expect(within(session).getByText('Framework item HRT1')).toBeInTheDocument();
    expect(within(session).getByText('Describe the cardiac cycle.')).toBeInTheDocument();
  });

  it('opens the filters and sets them in the address', async () => {
    renderAt('/search?q=cardiac&version=v1');
    await screen.findByRole('heading', { level: 2, name: /Objectives/ });

    fireEvent.click(screen.getByRole('button', { name: 'Filters' }));
    fireEvent.change(await screen.findByLabelText('Module'), { target: { value: 'm1' } });

    await waitFor(() =>
      expect(mocked.searchVersion).toHaveBeenLastCalledWith('v1', 'cardiac', { module: 'm1' })
    );
  });

  it('offers the version to search when there is more than one', async () => {
    renderAt('/search?q=cardiac&version=v1');

    const select = (await screen.findByLabelText('Version')) as HTMLSelectElement;
    expect(within(select).getAllByRole('option')).toHaveLength(2);
  });

  it('says what went wrong, and that nothing was searched', async () => {
    mocked.searchVersion.mockRejectedValue(new Error('network'));
    renderAt('/search?q=cardiac&version=v1');

    expect(await screen.findByText(/Couldn.t search/)).toBeInTheDocument();
  });
});
