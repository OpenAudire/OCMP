import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Alert, Button, NativeSelect, Paper, Switch } from '@mantine/core';
import { IconSquareCheck } from '@tabler/icons-react';
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes } from 'react-router';

import {
  confirmMappingRecheck,
  fetchReviewQueue,
  queryKeys,
  reviewMappingLink,
} from '../api/endpoints';
import type {
  BulkAcceptResult,
  ReviewDecision,
  ReviewLink,
  ReviewQueue,
  ReviewQueueParams,
  ReviewSort,
  ReviewStage,
} from '../api/types';
import { editErrorMessage, nounsFor } from '../curriculum/editing';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { BulkAcceptDialog } from './BulkAcceptDialog';
import { ReviewCard } from './ReviewCard';
import { ReviewDetail, type Picks } from './ReviewDetail';
import {
  readShortcutsOn,
  saveShortcutsOn,
  SHORTCUT_KEYS,
  shortcutFor,
  type ShortcutAction,
} from './shortcuts';
import classes from './Review.module.css';

export const REVIEW_PATH = '/mapping/review';
const PAGE_SIZE = 50;
const STAGES: readonly ReviewStage[] = ['first', 'second', 'recheck'];

type ConfidenceFilter = 'all' | 'high' | 'low';

/** "90% and above" and "below 65%", the two the mockup offers to start with. */
const CONFIDENCE: Record<ConfidenceFilter, { min?: number; max?: number }> = {
  all: {},
  high: { min: 0.9 },
  low: { max: 0.65 },
};

function nextAfter(items: ReviewLink[], id: string): string | null {
  const index = items.findIndex((item) => item.id === id);
  return items[index + 1]?.id ?? items[index - 1]?.id ?? null;
}

function Queue() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [stage, setStage] = useState<ReviewStage>('first');
  const [confidence, setConfidence] = useState<ConfidenceFilter>('all');
  const [moduleId, setModuleId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [frameworkId, setFrameworkId] = useState('');
  const [sort, setSort] = useState<ReviewSort>('confidence_desc');
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, Picks>>({});
  const [announcement, setAnnouncement] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [shortcutsOn, setShortcutsOn] = useState(readShortcutsOn);
  const cardRefs = useRef(new Map<string, HTMLButtonElement>());
  const statusRef = useRef<HTMLDivElement>(null);
  const coverageRef = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef(false);

  const params: ReviewQueueParams = useMemo(
    () => ({
      stage,
      sort,
      offset,
      versionId: versionId || undefined,
      frameworkId: frameworkId || undefined,
      moduleId: moduleId || undefined,
      minConfidence: CONFIDENCE[confidence].min,
      maxConfidence: CONFIDENCE[confidence].max,
    }),
    [stage, sort, offset, versionId, frameworkId, moduleId, confidence]
  );
  const queue = useQuery({
    queryKey: queryKeys.reviewQueue(params),
    queryFn: () => fetchReviewQueue(params),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
  const data: ReviewQueue | undefined = queue.data;
  const items = useMemo(() => data?.items ?? [], [data]);
  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const picks: Picks = selected
    ? (overrides[selected.id] ?? { coverage: selected.coverage, depth: selected.depth_match })
    : { coverage: null, depth: null };

  // After a decision or a skip, focus follows the selection so the shortcuts keep working.
  useEffect(() => {
    if (!pendingFocus.current || queue.isFetching) return;
    pendingFocus.current = false;
    const card = selected ? cardRefs.current.get(selected.id) : undefined;
    (card ?? statusRef.current)?.focus();
  }, [queue.isFetching, selected, items]);

  const refresh = () => client.invalidateQueries({ queryKey: ['review-queue'] });

  const fail = (error: unknown) => {
    setProblem(editErrorMessage(t, error, t('review.errors.moved')));
    void refresh();
  };

  const decide = useMutation({
    mutationFn: ({ link, decision }: { link: ReviewLink; decision: ReviewDecision }) =>
      reviewMappingLink(link.id, {
        decision,
        expected_status: link.status,
        ...(decision === 'accept' && picks.coverage !== null && picks.depth !== null
          ? { coverage: picks.coverage, depth_match: picks.depth }
          : {}),
      }),
    onSuccess: async (result, { link, decision }) => {
      const item = `${link.item.code} ${link.item.title}`;
      let key = 'review.notice.accepted';
      if (result.status === 'rejected') key = 'review.notice.rejected';
      else if (result.status === 'needs_second_review') {
        key = decision === 'second_review' ? 'review.notice.sent' : 'review.notice.acceptedSecond';
      }
      setAnnouncement(t(key, { item }));
      setProblem(null);
      pendingFocus.current = true;
      setSelectedId(nextAfter(items, link.id));
      await refresh();
    },
    onError: fail,
  });

  const recheck = useMutation({
    mutationFn: (link: ReviewLink) => confirmMappingRecheck(link.id),
    onSuccess: async (_saved, link) => {
      setAnnouncement(t('review.notice.rechecked', { item: `${link.item.code} ${link.item.title}` }));
      setProblem(null);
      pendingFocus.current = true;
      setSelectedId(nextAfter(items, link.id));
      await refresh();
    },
    onError: fail,
  });

  const busy = decide.isPending || recheck.isPending;

  const submit = (decision: ReviewDecision) => {
    if (!selected || busy) return;
    if (decision === 'accept' && (picks.coverage === null || picks.depth === null)) {
      setProblem(t('review.errors.choose'));
      return;
    }
    setProblem(null);
    decide.mutate({ link: selected, decision });
  };

  const skip = () => {
    if (!selected || items.length < 2) return;
    const index = items.findIndex((item) => item.id === selected.id);
    pendingFocus.current = true;
    setProblem(null);
    setSelectedId(items[(index + 1) % items.length].id);
  };

  const edit = () => {
    const group = coverageRef.current;
    const radio =
      group?.querySelector<HTMLInputElement>('input[type="radio"]:checked') ??
      group?.querySelector<HTMLInputElement>('input[type="radio"]');
    radio?.focus();
  };

  const run = (action: ShortcutAction) => {
    if (!selected) return;
    const isRecheck = selected.stage === 'recheck';
    if (action === 'skip') skip();
    else if (action === 'accept') {
      if (isRecheck) {
        if (!busy) recheck.mutate(selected);
      } else submit('accept');
    } else if (isRecheck) return;
    else if (action === 'edit') edit();
    else if (action === 'reject') submit('reject');
    else if (action === 'second' && selected.stage === 'first') submit('second_review');
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!shortcutsOn || !selected) return;
    const action = shortcutFor(event.nativeEvent, event.target);
    if (!action) return;
    event.preventDefault();
    run(action);
  };

  const reset = () => {
    setOffset(0);
    setSelectedId(null);
    setProblem(null);
  };

  const onBulkDone = async (result: BulkAcceptResult, percent: number) => {
    setBulkOpen(false);
    setProblem(null);
    setSelectedId(null);
    setAnnouncement(
      t(result.status_after === 'accepted' ? 'review.notice.bulk' : 'review.notice.bulkSecond', {
        count: result.processed,
        percent,
      })
    );
    await refresh();
    statusRef.current?.focus();
  };

  if (queue.isPending) {
    return <LoadingState skeletons={3} />;
  }
  if (queue.isError || !data) {
    return (
      <ErrorState
        title={t('review.errors.loadTitle')}
        body={t('review.errors.loadBody')}
        actions={<Button onClick={() => void queue.refetch()}>{t('pages.retry')}</Button>}
      />
    );
  }

  if (data.progress.total === 0 && data.counts.total === 0) {
    return (
      <EmptyState
        icon={IconSquareCheck}
        title={t('review.empty.title')}
        body={t('review.empty.body')}
      />
    );
  }

  const nouns = nounsFor(t);
  const { progress, counts, facets } = data;
  const reviewed = progress.accepted + progress.rejected + progress.second_review;
  const percentDone = progress.total === 0 ? 0 : Math.round((reviewed / progress.total) * 100);
  const reviewedText = t('review.progress.reviewed', { reviewed, total: progress.total });
  const from = data.total === 0 ? 0 : data.offset + 1;
  const to = Math.min(data.offset + data.limit, data.total);

  return (
    <>
      {counts.first > 0 && stage === 'first' && (
        <div>
          <Button variant="default" onClick={() => setBulkOpen(true)}>
            {t('review.bulk.button', { percent: 90 })}
          </Button>
        </div>
      )}

      <Paper withBorder className={classes.progress} component="section" aria-label={t('review.progress.label')}>
        <div className={classes.progressHead}>
          <span className={classes.reviewed}>{reviewedText}</span>
          <ul className={classes.tallies}>
            <li data-tone="good">
              <strong>{progress.accepted}</strong> {t('review.progress.accepted')}
            </li>
            <li data-tone="bad">
              <strong>{progress.rejected}</strong> {t('review.progress.rejected')}
            </li>
            <li data-tone="attention">
              <strong>{progress.second_review}</strong> {t('review.progress.second')}
            </li>
            <li>
              <strong>{progress.waiting}</strong> {t('review.progress.waiting')}
            </li>
          </ul>
        </div>
        <div className={classes.bar} role="img" aria-label={reviewedText}>
          <div className={classes.barFill} style={{ width: `${percentDone}%` }} />
        </div>
        <div className={classes.filters}>
          <NativeSelect
            label={t('review.filters.stage')}
            value={stage}
            onChange={(event) => {
              setStage(event.currentTarget.value as ReviewStage);
              reset();
            }}
            data={STAGES.map((value) => ({
              value,
              label: t('review.stage.option', {
                label: t(`review.stage.names.${value}`),
                count: counts[value],
              }),
            }))}
          />
          <NativeSelect
            label={t('review.filters.confidence')}
            value={confidence}
            onChange={(event) => {
              setConfidence(event.currentTarget.value as ConfidenceFilter);
              reset();
            }}
            data={[
              { value: 'all', label: t('review.filters.confidenceAll') },
              { value: 'high', label: t('review.filters.confidenceHigh') },
              { value: 'low', label: t('review.filters.confidenceLow') },
            ]}
          />
          {facets.modules.length > 1 && (
            <NativeSelect
              label={t('terms.module', { count: 1 })}
              value={moduleId}
              onChange={(event) => {
                setModuleId(event.currentTarget.value);
                reset();
              }}
              data={[
                { value: '', label: t('review.filters.allModules', { modules: nouns.modules }) },
                ...facets.modules.map((m) => ({ value: m.id, label: `${m.code} ${m.name}` })),
              ]}
            />
          )}
          {facets.versions.length > 1 && (
            <NativeSelect
              label={t('review.filters.version')}
              value={versionId}
              onChange={(event) => {
                setVersionId(event.currentTarget.value);
                reset();
              }}
              data={[
                { value: '', label: t('review.filters.allVersions') },
                ...facets.versions.map((v) => ({
                  value: v.id,
                  label: `${v.programme_name} ${v.academic_year}`,
                })),
              ]}
            />
          )}
          {facets.frameworks.length > 1 && (
            <NativeSelect
              label={t('review.filters.framework')}
              value={frameworkId}
              onChange={(event) => {
                setFrameworkId(event.currentTarget.value);
                reset();
              }}
              data={[
                { value: '', label: t('review.filters.allFrameworks') },
                ...facets.frameworks.map((f) => ({
                  value: f.id,
                  label: t('mapping.framework.option', { name: f.name, version: f.version_label }),
                })),
              ]}
            />
          )}
          <NativeSelect
            label={t('review.filters.sort')}
            value={sort}
            onChange={(event) => {
              setSort(event.currentTarget.value as ReviewSort);
              reset();
            }}
            data={[
              { value: 'confidence_desc', label: t('review.filters.sortHigh') },
              { value: 'confidence_asc', label: t('review.filters.sortLow') },
              { value: 'module', label: t('review.filters.sortModule', { module: nouns.module }) },
            ]}
          />
        </div>
        <div className={classes.legend}>
          <Switch
            label={t('review.shortcuts.switch')}
            checked={shortcutsOn}
            onChange={(event) => {
              setShortcutsOn(event.currentTarget.checked);
              saveShortcutsOn(event.currentTarget.checked);
            }}
          />
          {shortcutsOn ? (
            <ul aria-label={t('review.shortcuts.list')}>
              {SHORTCUT_KEYS.map(({ key, action }) => (
                <li key={action}>
                  <span className={classes.kbd}>{key}</span> {t(`review.shortcuts.actions.${action}`)}
                </li>
              ))}
            </ul>
          ) : (
            <span>{t('review.shortcuts.off')}</span>
          )}
          {shortcutsOn && <span>{t('review.shortcuts.where')}</span>}
        </div>
      </Paper>

      <div
        ref={statusRef}
        className={classes.status}
        role="status"
        tabIndex={-1}
        aria-live="polite"
      >
        {announcement}
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={IconSquareCheck}
          title={t(`review.stage.empty.${stage}`)}
          body={t('review.stage.emptyBody')}
        />
      ) : (
        // Shortcuts work only while focus is in here (WCAG 2.1.4); the switch above turns them off.
        <div className={classes.work} onKeyDown={onKeyDown}>
          <section className={classes.listColumn} aria-label={t('review.list.label')}>
            <ul className={classes.list}>
              {items.map((item) => (
                <ReviewCard
                  key={item.id}
                  link={item}
                  selected={selected?.id === item.id}
                  onSelect={() => {
                    setProblem(null);
                    setSelectedId(item.id);
                  }}
                  buttonRef={(element) => {
                    if (element) cardRefs.current.set(item.id, element);
                    else cardRefs.current.delete(item.id);
                  }}
                />
              ))}
            </ul>
            <div className={classes.pager}>
              <span>{t('review.list.showing', { from, to, total: data.total })}</span>
              <span>
                <Button
                  variant="default"
                  disabled={offset === 0}
                  onClick={() => {
                    setOffset(Math.max(0, offset - PAGE_SIZE));
                    setSelectedId(null);
                  }}
                >
                  {t('review.list.previous')}
                </Button>{' '}
                <Button
                  variant="default"
                  disabled={offset + data.limit >= data.total}
                  onClick={() => {
                    setOffset(offset + PAGE_SIZE);
                    setSelectedId(null);
                  }}
                >
                  {t('review.list.next')}
                </Button>
              </span>
            </div>
          </section>
          {selected && (
            <ReviewDetail
              key={selected.id}
              link={selected}
              picks={picks}
              onPicks={(next) => setOverrides({ ...overrides, [selected.id]: next })}
              fourEyes={data.four_eyes}
              busy={busy}
              problem={problem}
              coverageRef={coverageRef}
              onDecide={submit}
              onSkip={skip}
              onRecheck={() => recheck.mutate(selected)}
            />
          )}
        </div>
      )}
      {items.length === 0 && problem && <Alert color="red">{problem}</Alert>}

      {bulkOpen && (
        <BulkAcceptDialog
          scope={{
            version_id: versionId || undefined,
            framework_id: frameworkId || undefined,
            module_id: moduleId || undefined,
          }}
          fourEyes={data.four_eyes}
          minConfidence={data.bulk_min_confidence}
          maxLinks={data.bulk_max_links}
          initial={0.9}
          onClose={() => setBulkOpen(false)}
          onDone={(result, percent) => void onBulkDone(result, percent)}
        />
      )}
    </>
  );
}

function ReviewPage() {
  const { t } = useTranslation();
  return (
    <Page title={t('nav.review')} description={t('review.intro')}>
      <Queue />
    </Page>
  );
}

/** `/mapping/review`: the links that wait for this person's decision. */
export function ReviewSection() {
  return (
    <Routes>
      <Route index element={<ReviewPage />} />
      <Route path="*" element={<Navigate to={REVIEW_PATH} replace />} />
    </Routes>
  );
}
