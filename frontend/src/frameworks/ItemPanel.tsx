import { Alert, Anchor, Button, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconRefresh } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { fetchFrameworkItem, fetchWhereMapped, queryKeys } from '../api/endpoints';
import type { FrameworkItemDetail, MappedObjective } from '../api/types';
import { versionPath } from '../curriculum/paths';
import { ErrorState } from '../ui/States';
import classes from './Frameworks.module.css';

/** The curriculum item a mapped objective belongs to, as a link to it. */
function WhereLink({ mapping }: { mapping: MappedObjective }) {
  const { t } = useTranslation();
  const year = t('frameworks.item.version', {
    year: mapping.academic_year,
    status: t(`curriculum.versionStatus.${mapping.version_status}`),
  });
  let target: string;
  let text: string;
  if (mapping.learning_event_id) {
    target = `event:${mapping.learning_event_id}`;
    const module = `${mapping.module_code ?? ''} ${mapping.module_name ?? ''}`;
    text = `${module}: ${mapping.learning_event_title ?? ''}`;
  } else if (mapping.module_id) {
    target = `module:${mapping.module_id}`;
    text = `${mapping.module_code ?? ''} ${mapping.module_name ?? ''}`;
  } else {
    target = 'programme';
    text = t('frameworks.item.programmeLevel', { programme: mapping.programme_name });
  }
  return (
    <span className={classes.linkWhere}>
      <Anchor component={Link} to={versionPath(mapping.version_id, target)} size="sm">
        {text.trim()}
      </Anchor>
      {` · ${mapping.programme_name} · ${year}`}
    </span>
  );
}

function MappedChips({ mapping }: { mapping: MappedObjective }) {
  const { t } = useTranslation();
  return (
    <div className={classes.chips}>
      <span
        className={classes.chip}
        data-tone={mapping.status === 'accepted' ? 'good' : 'attention'}
      >
        {t(`frameworks.item.linkStatus.${mapping.status}`)}
      </span>
      <span className={classes.chip}>
        {mapping.coverage === null
          ? t('frameworks.item.coverageUnknown')
          : t('frameworks.item.coverage', { value: mapping.coverage })}
      </span>
      {mapping.depth_match && (
        <span className={classes.chip}>{t(`frameworks.item.depth.${mapping.depth_match}`)}</span>
      )}
      {mapping.needs_recheck && (
        <span className={classes.chip} data-tone="attention">
          <IconAlertTriangle size={14} aria-hidden="true" />
          {t('frameworks.item.recheck')}
        </span>
      )}
      {mapping.needs_discussion && (
        <span className={classes.chip} data-tone="attention">
          <IconAlertTriangle size={14} aria-hidden="true" />
          {t('frameworks.item.discussion')}
        </span>
      )}
    </div>
  );
}

/** Read-only list of the objectives linked to an item that the user may see. */
function WhereMappedList({ frameworkId, itemId }: { frameworkId: string; itemId: string }) {
  const { t } = useTranslation();
  const mapped = useQuery({
    queryKey: queryKeys.frameworkMappings(frameworkId, itemId),
    queryFn: () => fetchWhereMapped(frameworkId, itemId),
  });
  return (
    <Stack gap="sm" component="section" aria-labelledby="where-mapped-title">
      <Title order={3} id="where-mapped-title" size="h4">
        {t('frameworks.item.mappedTitle')}
      </Title>
      <Text size="sm" c="dimmed">
        {t('frameworks.item.mappedIntro')}
      </Text>
      {mapped.isPending && (
        <Text role="status" size="sm" c="dimmed">
          {t('frameworks.item.mappedLoading')}
        </Text>
      )}
      {mapped.isError && (
        <Alert color="red">
          <Stack gap="xs" align="flex-start">
            {t('frameworks.item.mappedFailed')}
            <Button
              variant="default"
              size="sm"
              leftSection={<IconRefresh size={16} aria-hidden="true" />}
              onClick={() => void mapped.refetch()}
            >
              {t('frameworks.retry')}
            </Button>
          </Stack>
        </Alert>
      )}
      {mapped.data && mapped.data.total === 0 && (
        <Text size="sm">{t('frameworks.item.mappedNone')}</Text>
      )}
      {mapped.data && mapped.data.total > 0 && (
        <>
          <Text size="sm" fw={600}>
            {t('frameworks.item.mappedCount', { count: mapped.data.total })}
            {mapped.data.total > mapped.data.limit && (
              <> {t('frameworks.item.mappedLimit', { limit: mapped.data.limit })}</>
            )}
          </Text>
          <ul className={classes.mapped} aria-label={t('frameworks.item.mappedList')}>
            {mapped.data.mappings.map((mapping) => (
              <li key={mapping.link_id} className={classes.link}>
                <Text size="sm">{mapping.objective_text}</Text>
                <WhereLink mapping={mapping} />
                <MappedChips mapping={mapping} />
              </li>
            ))}
          </ul>
        </>
      )}
    </Stack>
  );
}

interface ItemPanelProps {
  frameworkId: string;
  itemId: string;
  /** Offered when the item was found by searching and the tree is hidden. */
  onShowInTree?: (detail: FrameworkItemDetail) => void;
}

/** One framework item: where it sits, its wording, and where it is mapped. */
export function ItemPanel({ frameworkId, itemId, onShowInTree }: ItemPanelProps) {
  const { t } = useTranslation();
  const item = useQuery({
    queryKey: queryKeys.frameworkItem(frameworkId, itemId),
    queryFn: () => fetchFrameworkItem(frameworkId, itemId),
  });

  if (item.isPending) {
    return (
      <Paper withBorder className={classes.itemCard} aria-busy="true">
        <Skeleton height={14} width="40%" />
        <Skeleton height={22} width="70%" />
        <Skeleton height={14} width="90%" />
      </Paper>
    );
  }
  if (item.isError) {
    return (
      <ErrorState
        title={t('frameworks.item.loadErrorTitle')}
        body={t('frameworks.item.loadErrorBody')}
        actions={<Button onClick={() => void item.refetch()}>{t('frameworks.retry')}</Button>}
      />
    );
  }
  const detail = item.data;
  return (
    <>
      <Paper withBorder className={classes.itemCard}>
        {detail.path.length > 0 && (
          <nav aria-label={t('frameworks.item.path')}>
            <ol className={classes.crumbs}>
              {detail.path.map((ancestor) => (
                <li key={ancestor.id}>
                  <span className={classes.code}>{ancestor.code}</span> {ancestor.title}
                </li>
              ))}
            </ol>
          </nav>
        )}
        <Title order={2} size="h3">
          <span className={classes.code}>{detail.code}</span> {detail.title}
        </Title>
        <Text size="sm" c={detail.description ? undefined : 'dimmed'}>
          {detail.description || t('frameworks.item.noDescription')}
        </Text>
        {detail.child_count > 0 && (
          <Text size="sm" c="dimmed">
            {t('frameworks.item.children', { count: detail.child_count })}
          </Text>
        )}
        {onShowInTree && (
          <div>
            <Button variant="default" onClick={() => onShowInTree(detail)}>
              {t('frameworks.item.showInTree')}
            </Button>
          </div>
        )}
      </Paper>
      <Paper withBorder className={classes.itemCard}>
        <WhereMappedList frameworkId={frameworkId} itemId={itemId} />
      </Paper>
    </>
  );
}
