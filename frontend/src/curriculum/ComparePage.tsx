import { Box, Button, NativeSelect, Paper, Stack, Text, Title } from '@mantine/core';
import { IconArrowLeft, IconArrowsDiff } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import { fetchVersionDiff, queryKeys } from '../api/endpoints';
import type { FieldChange, ItemChange, ItemKind, VersionDiff } from '../api/types';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { findVersion, useProgrammes } from './currentVersion';
import { nounsFor } from './editing';
import { CURRICULUM_PATH, versionPath } from './paths';
import { defaultBase, versionLabel, versionName } from './versions';
import { VersionSwitcher } from './VersionSwitcher';
import classes from './ComparePage.module.css';

const KINDS: ItemKind[] = ['phase', 'module', 'learning_event', 'assessment', 'objective'];
/** Curriculum nouns come from the terms; assessments have a fixed word (ADR 035). */
const TERMS: Record<ItemKind, string | null> = {
  phase: 'phase',
  module: 'module',
  learning_event: 'learning_event',
  assessment: null,
  objective: 'objective',
};
/** Fields whose values are keys with their own translations. */
const TRANSLATED: Record<string, string> = {
  kind: 'curriculum.phaseKind',
  domain: 'curriculum.domain',
  status: 'curriculum.objectiveStatus',
};

function kindTitle(t: TFunction, kind: ItemKind): string {
  const term = TERMS[kind];
  return term ? t(`terms.${term}`, { count: 2 }) : t('curriculum.assessments.title');
}

function fieldLabel(t: TFunction, field: string): string {
  if (field === 'phase') return t('terms.phase', { count: 1 });
  return t(`curriculum.compare.fields.${field}`);
}

function fieldValue(t: TFunction, field: string, value: FieldChange['before']): string {
  if (value === null || value === '') return t('curriculum.compare.empty');
  const prefix = TRANSLATED[field];
  return prefix ? t(`${prefix}.${value}`) : String(value);
}

function Change({ item }: { item: ItemChange }) {
  const { t } = useTranslation();
  let context = item.context;
  if (item.kind === 'objective' && item.level === 'programme') {
    context = t('curriculum.compare.programmeOutcome', {
      programme: t('terms.programme', { count: 1 }),
    });
  }
  return (
    <li className={classes.item}>
      <div className={classes.itemHead}>
        <span className={classes.chip} data-change={item.change}>
          {t(`curriculum.compare.change.${item.change}`)}
        </span>
        <Stack gap={2} className={classes.itemText}>
          <Text fw={500} className={classes.label}>
            {item.label}
          </Text>
          {context && (
            <Text size="sm" c="dimmed">
              {context}
            </Text>
          )}
        </Stack>
      </div>
      {item.fields.length > 0 && (
        <dl className={classes.fields}>
          {item.fields.map((change) => (
            <div key={change.field} className={classes.field}>
              <dt>{fieldLabel(t, change.field)}</dt>
              <dd>
                <span className={classes.before}>
                  <span className={classes.valueLabel}>{t('curriculum.compare.before')}</span>{' '}
                  {fieldValue(t, change.field, change.before)}
                </span>
                <span className={classes.after}>
                  <span className={classes.valueLabel}>{t('curriculum.compare.after')}</span>{' '}
                  {fieldValue(t, change.field, change.after)}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  );
}

function DiffView({ diff }: { diff: VersionDiff }) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const heading = t('curriculum.compare.heading', {
    base: versionName(t, diff.base),
    version: versionName(t, diff.version),
  });
  if (diff.changes.length === 0) {
    return (
      <EmptyState
        icon={IconArrowsDiff}
        title={t('curriculum.compare.noChangesTitle')}
        body={t('curriculum.compare.noChanges', nouns)}
      />
    );
  }
  return (
    <Stack gap="lg">
      <Paper withBorder component="section" aria-labelledby="diff-summary" className={classes.card}>
        <Title order={2} id="diff-summary" className={classes.sectionTitle}>
          {heading}
        </Title>
        <dl className={classes.summary}>
          {KINDS.map((kind) => (
            <div key={kind} className={classes.summaryItem}>
              <dt>{kindTitle(t, kind)}</dt>
              <dd>{t('curriculum.compare.summaryLine', diff.summary[kind])}</dd>
            </div>
          ))}
        </dl>
        <Text size="sm" c="dimmed">
          {t('curriculum.compare.notCompared')}
        </Text>
      </Paper>
      {KINDS.map((kind) => {
        const items = diff.changes.filter((change) => change.kind === kind);
        if (items.length === 0) return null;
        const id = `diff-${kind}`;
        return (
          <Paper
            key={kind}
            withBorder
            component="section"
            aria-labelledby={id}
            className={classes.card}
          >
            <Title order={2} id={id} className={classes.sectionTitle}>
              {kindTitle(t, kind)}
            </Title>
            <ul className={classes.list}>
              {items.map((item) => (
                <Change key={`${item.change}-${item.id ?? item.base_id}`} item={item} />
              ))}
            </ul>
          </Paper>
        );
      })}
    </Stack>
  );
}

/** `/curriculum/versions/:versionId/compare?base=`: what changed between two versions. */
export function ComparePage() {
  const { t } = useTranslation();
  const { versionId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const programmes = useProgrammes();
  const found = programmes.data ? findVersion(programmes.data, versionId) : null;
  const others = found ? found.programme.versions.filter((v) => v.id !== versionId) : [];
  const requested = others.find((v) => v.id === searchParams.get('base'));
  const base = requested ?? (found ? defaultBase(found.programme, found.version) : null);
  const diff = useQuery({
    queryKey: queryKeys.versionDiff(versionId, base?.id ?? ''),
    queryFn: () => fetchVersionDiff(versionId, base!.id),
    enabled: base !== null,
  });

  let content;
  if (programmes.isPending || (base !== null && diff.isPending)) {
    content = <LoadingState skeletons={3} />;
  } else if (programmes.isError || !found || isApiError(diff.error, 404)) {
    content = (
      <ErrorState
        title={t('curriculum.errors.notFoundTitle')}
        body={t('curriculum.errors.notFoundBody')}
        actions={
          <Button component={Link} to={CURRICULUM_PATH}>
            {t('curriculum.errors.openDefault')}
          </Button>
        }
      />
    );
  } else if (base === null) {
    content = (
      <EmptyState
        icon={IconArrowsDiff}
        title={t('curriculum.compare.nothingTitle')}
        body={t('curriculum.compare.nothing', {
          programme: t('terms.programme', { count: 1 }).toLocaleLowerCase(),
        })}
      />
    );
  } else if (diff.isError || !diff.data) {
    content = (
      <ErrorState
        title={t('curriculum.compare.loadTitle')}
        body={t('curriculum.compare.loadBody')}
        actions={<Button onClick={() => void diff.refetch()}>{t('pages.retry')}</Button>}
      />
    );
  } else {
    content = <DiffView diff={diff.data} />;
  }

  return (
    <Page
      title={t('curriculum.compare.title')}
      description={
        found ? t('curriculum.compare.description', { programme: found.programme.name }) : undefined
      }
    >
      <Box hiddenFrom="sm">
        <VersionSwitcher versionId={versionId} />
      </Box>
      {found && (
        <div className={classes.controls}>
          <Button
            component={Link}
            to={versionPath(versionId)}
            variant="default"
            leftSection={<IconArrowLeft size={18} aria-hidden />}
          >
            {t('curriculum.compare.back')}
          </Button>
          {base && others.length > 0 && (
            <NativeSelect
              label={t('curriculum.compare.base')}
              value={base.id}
              data={others.map((v) => ({ value: v.id, label: versionLabel(t, v) }))}
              onChange={(event) =>
                setSearchParams({ base: event.currentTarget.value }, { replace: true })
              }
              className={classes.select}
            />
          )}
        </div>
      )}
      {content}
    </Page>
  );
}
