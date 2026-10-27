import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Anchor, Button, Paper, Text, TextInput } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import {
  fetchFrameworkItem,
  fetchFrameworkLibrary,
  queryKeys,
  searchFramework,
} from '../api/endpoints';
import type { FrameworkItemDetail, FrameworkSearchHit } from '../api/types';
import { NoAccessPage } from '../pages/StatusPages';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import { FrameworkTree } from './FrameworkTree';
import { ItemPanel } from './ItemPanel';
import { ROOT, useFrameworkTree } from './useFrameworkTree';
import classes from './Frameworks.module.css';

const SEARCH_DELAY_MS = 300;

function Result({
  hit,
  selected,
  onPick,
}: {
  hit: FrameworkSearchHit;
  selected: boolean;
  onPick: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <li>
      <button
        type="button"
        className={classes.result}
        aria-current={selected || undefined}
        onClick={() => onPick(hit.id)}
      >
        <span>
          <span className={classes.code}>{hit.code}</span> {hit.title}
        </span>
        {hit.path.length > 0 && (
          <span className={classes.resultPath}>{hit.path.map((a) => a.code).join(' / ')}</span>
        )}
        {hit.mapped_count > 0 && (
          <span className={classes.resultPath}>
            {t('frameworks.tree.mapped', {
              count: hit.mapped_count,
              noun: t('terms.objective', { count: hit.mapped_count }).toLocaleLowerCase(),
            })}
          </span>
        )}
      </button>
    </li>
  );
}

interface SearchResultsProps {
  frameworkId: string;
  query: string;
  selectedId: string | null;
  onPick: (id: string) => void;
}

function SearchResults({ frameworkId, query, selectedId, onPick }: SearchResultsProps) {
  const { t } = useTranslation();
  const search = useInfiniteQuery({
    queryKey: queryKeys.frameworkSearch(frameworkId, query),
    queryFn: ({ pageParam }) => searchFramework(frameworkId, query, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const next = last.offset + last.hits.length;
      return next < last.total ? next : undefined;
    },
  });
  const hits = search.data?.pages.flatMap((page) => page.hits) ?? [];
  const total = search.data?.pages[0]?.total ?? 0;
  return (
    <div>
      <Text role="status" size="sm" c="dimmed" px={8} pb={6}>
        {search.isPending && t('frameworks.browser.searching')}
        {search.isError && t('frameworks.browser.searchFailed')}
        {search.data &&
          (total === 0
            ? t('frameworks.browser.noResults', { query })
            : t('frameworks.browser.resultsCount', { count: total }))}
      </Text>
      {search.isError && (
        <Button variant="default" ml={8} mb={8} onClick={() => void search.refetch()}>
          {t('frameworks.retry')}
        </Button>
      )}
      {hits.length > 0 && (
        <ul className={classes.results} aria-label={t('frameworks.browser.resultsLabel')}>
          {hits.map((hit) => (
            <Result key={hit.id} hit={hit} selected={hit.id === selectedId} onPick={onPick} />
          ))}
        </ul>
      )}
      {search.hasNextPage && (
        <Button
          variant="default"
          ml={8}
          mt={8}
          loading={search.isFetchingNextPage}
          onClick={() => void search.fetchNextPage()}
        >
          {t('frameworks.browser.moreResults')}
        </Button>
      )}
    </div>
  );
}

function Browser({ frameworkId, name }: { frameworkId: string; name: string }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const selectedId = params.get('item');
  const tree = useFrameworkTree(frameworkId);
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [focusId, setFocusId] = useState<string | null>(null);
  const revealed = useRef<string | null>(null);

  // Search as the person types, a moment after they stop.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(text.trim()), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [text]);
  const searching = query.length > 0 && text.trim().length > 0;

  const select = useCallback(
    (id: string) => {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.set('item', id);
          return next;
        },
        { replace: true }
      );
    },
    [setParams]
  );

  // An item named in the address (a shared link, or picked from a search) opens in the tree.
  const rootReady = tree.windows[ROOT] !== undefined;
  const selected = useQuery({
    queryKey: queryKeys.frameworkItem(frameworkId, selectedId ?? ''),
    queryFn: () => fetchFrameworkItem(frameworkId, selectedId!),
    enabled: selectedId !== null,
  });
  const { reveal, has } = tree;
  useEffect(() => {
    const detail = selected.data;
    if (!detail || !rootReady || searching) return;
    if (has(detail.id) || revealed.current === detail.id) return;
    revealed.current = detail.id;
    void reveal(detail);
  }, [selected.data, rootReady, searching, has, reveal]);

  const showInTree = (detail: FrameworkItemDetail) => {
    revealed.current = null;
    setText('');
    setQuery('');
    void reveal(detail).then(() => setFocusId(detail.id));
  };

  const rootWindow = tree.windows[ROOT];
  return (
    <div className={classes.browser}>
      <Paper withBorder className={classes.side}>
        <div className={classes.sideHeading}>{t('frameworks.browser.treeTitle')}</div>
        <div className={classes.searchBox}>
          <TextInput
            type="search"
            label={t('frameworks.browser.searchLabel')}
            description={t('frameworks.browser.searchHint')}
            placeholder={t('frameworks.browser.searchPlaceholder')}
            value={text}
            onChange={(event) => setText(event.currentTarget.value)}
          />
          {text !== '' && (
            <div>
              <Button
                variant="default"
                onClick={() => {
                  setText('');
                  setQuery('');
                }}
              >
                {t('frameworks.browser.clearSearch')}
              </Button>
            </div>
          )}
        </div>
        {searching ? (
          <SearchResults
            frameworkId={frameworkId}
            query={query}
            selectedId={selectedId}
            onPick={select}
          />
        ) : (
          <>
            {tree.failed && <Alert color="red">{t('frameworks.browser.treeFailed')}</Alert>}
            {tree.loading && (
              <Text role="status" size="sm" c="dimmed" px={8}>
                {t('frameworks.browser.loadingItems')}
              </Text>
            )}
            {rootWindow && rootWindow.total === 0 && (
              <Text size="sm" px={8}>
                {t('frameworks.browser.empty')}
              </Text>
            )}
            {tree.rows.length > 0 && (
              <FrameworkTree
                label={t('frameworks.browser.treeLabel', { name })}
                rows={tree.rows}
                selectedId={selectedId}
                expanded={tree.expanded}
                busy={tree.loading}
                onSelect={select}
                onOpen={tree.open}
                onClose={tree.close}
                onShowMore={tree.showMore}
                onShowEarlier={tree.showEarlier}
                focusId={focusId}
                onFocused={() => setFocusId(null)}
              />
            )}
          </>
        )}
      </Paper>
      <div className={classes.panel}>
        {selectedId ? (
          <ItemPanel
            key={selectedId}
            frameworkId={frameworkId}
            itemId={selectedId}
            onShowInTree={searching ? showInTree : undefined}
          />
        ) : (
          <Paper withBorder className={classes.itemCard}>
            <Text c="dimmed">{t('frameworks.browser.selectPrompt')}</Text>
          </Paper>
        )}
      </div>
    </div>
  );
}

/** `/frameworks/:frameworkId`: one framework version as a tree, with search and where items are mapped. */
export function FrameworkBrowser() {
  const { t } = useTranslation();
  const { frameworkId } = useParams();
  const library = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });

  if (!frameworkId) return null;
  if (library.isPending) {
    return (
      <Page title={t('nav.frameworks')}>
        <LoadingState skeletons={3} />
      </Page>
    );
  }
  if (library.isError) {
    if (isApiError(library.error, 403)) return <NoAccessPage />;
    return (
      <Page title={t('nav.frameworks')}>
        <ErrorState
          title={t('frameworks.library.loadErrorTitle')}
          body={t('frameworks.library.loadErrorBody')}
          actions={<Button onClick={() => void library.refetch()}>{t('frameworks.retry')}</Button>}
        />
      </Page>
    );
  }
  const framework = library.data.frameworks.find((f) => f.id === frameworkId);
  if (!framework) {
    return (
      <Page title={t('nav.frameworks')}>
        <ErrorState
          title={t('frameworks.browser.loadErrorTitle')}
          body={t('frameworks.browser.loadErrorBody')}
          actions={
            <Button component={Link} to="/frameworks">
              {t('frameworks.browser.back')}
            </Button>
          }
        />
      </Page>
    );
  }
  return (
    <Page
      title={framework.name}
      description={`${t('frameworks.browser.meta', {
        version: framework.version_label,
        status: t(`frameworks.status.${framework.status}`).toLocaleLowerCase(),
      })}. ${t('frameworks.browser.source', { publisher: framework.publisher })}`}
    >
      <div>
        <Anchor component={Link} to="/frameworks" size="sm">
          <IconArrowLeft size={16} aria-hidden="true" className={classes.inlineIcon} />{' '}
          {t('frameworks.browser.back')}
        </Anchor>
      </div>
      <Browser key={framework.id} frameworkId={framework.id} name={framework.name} />
    </Page>
  );
}
