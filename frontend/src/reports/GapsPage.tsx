import { Badge, Group, Paper, Stack, Table, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router';

import { isApiError } from '../api/client';
import { fetchGaps, queryKeys } from '../api/endpoints';
import type { GapReport, GapRow, UnmappedObjective } from '../api/types';
import { versionPath } from '../curriculum/paths';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import { MetaPanel } from './CoveragePage';
import { CoverageControls } from './CoverageControls';
import { useChoice } from './useChoice';
import classes from './Coverage.module.css';
import { percent } from './coverageFormat';

function where(t: ReturnType<typeof useTranslation>['t'], o: UnmappedObjective): string {
  if (o.level === 'programme') return t('reports.gaps.programmeOutcome');
  return [o.module_code, o.event_title].filter(Boolean).join(' · ');
}

/** Why an item is a gap, in words, from its figures and the method. */
function reasonOf(t: ReturnType<typeof useTranslation>['t'], gap: GapRow, report: GapReport): string {
  if (gap.status === 'none') return t('reports.gaps.reasons.none');
  if (report.method === 'multiple') {
    return t('reports.gaps.reasons.multiple', {
      links: gap.links,
      n: report.params.multiple_match_n,
    });
  }
  return t('reports.gaps.reasons.weighted', { percent: percent(gap.value) });
}

function ObjectiveList({
  versionId,
  title,
  help,
  total,
  rows,
}: {
  versionId: string;
  title: string;
  help: string;
  total: number;
  rows: UnmappedObjective[];
}) {
  const { t } = useTranslation();
  const id = title.replace(/\W+/g, '-').toLowerCase();
  return (
    <section aria-labelledby={id}>
      <Title order={2} id={id} className={classes.title}>
        {title} ({total})
      </Title>
      <Text size="sm" c="dimmed">
        {help}
      </Text>
      {rows.length === 0 ? (
        <Text mt="xs">{t('reports.gaps.noneHere')}</Text>
      ) : (
        <ul className={classes.objectives}>
          {rows.map((o) => (
            <li key={o.id}>
              <Link
                to={versionPath(
                  versionId,
                  o.event_id
                    ? `event:${o.event_id}`
                    : o.module_id
                      ? `module:${o.module_id}`
                      : 'programme'
                )}
              >
                {o.text}
              </Link>
              <Text size="sm" c="dimmed">
                {where(t, o)}
                {o.waiting > 0 && ` · ${t('reports.coverage.waiting', { count: o.waiting })}`}
              </Text>
            </li>
          ))}
        </ul>
      )}
      {total > rows.length && (
        <Text size="sm" c="dimmed" mt="xs">
          {t('reports.gaps.showing', { shown: rows.length, total })}
        </Text>
      )}
    </section>
  );
}

function GapItems({ report }: { report: GapReport }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="gap-items">
      <Title order={2} id="gap-items" className={classes.title}>
        {t('reports.gaps.itemsTitle', { count: report.gaps.length })}
      </Title>
      <Text size="sm" c="dimmed">
        {t('reports.gaps.itemsHelp')}
      </Text>
      {report.gaps.length === 0 ? (
        <Text mt="xs">{t('reports.gaps.noGaps')}</Text>
      ) : (
        <Table.ScrollContainer minWidth={640}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('reports.coverage.item')}</Table.Th>
                <Table.Th>{t('reports.coverage.statusColumn')}</Table.Th>
                <Table.Th>{t('reports.gaps.why')}</Table.Th>
                <Table.Th>{t('reports.coverage.flags')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {report.gaps.map((gap) => (
                <Table.Tr key={gap.id}>
                  <Table.Th scope="row" fw={400}>
                    {gap.path.length > 0 && (
                      <Text size="xs" c="dimmed">
                        {gap.path.map((p) => `${p.code} ${p.title}`).join(' › ')}
                      </Text>
                    )}
                    <span className={classes.itemCode}>{gap.code}</span> {gap.title}
                  </Table.Th>
                  <Table.Td>
                    <span
                      className={gap.status === 'none' ? classes.statusNone : classes.statusPartial}
                    >
                      {t(`reports.status.${gap.status}`)}
                    </span>
                    {gap.status === 'partial' && ` · ${percent(gap.value)}`}
                  </Table.Td>
                  <Table.Td>{reasonOf(t, gap, report)}</Table.Td>
                  <Table.Td>
                    {gap.waiting > 0 && (
                      <Badge variant="outline" color="gray" size="sm">
                        {t('reports.coverage.waiting', { count: gap.waiting })}
                      </Badge>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </section>
  );
}

/** `/reports/gaps`: framework items with no or low coverage, and objectives with no mapping. */
export function GapsPage() {
  const { t } = useTranslation();
  const { search } = useLocation();
  const choice = useChoice();
  const ready = choice.versionId !== null && choice.frameworkId !== null;
  const report = useQuery({
    queryKey: queryKeys.gaps(choice.versionId ?? '', choice.frameworkId ?? '', choice.method),
    queryFn: () =>
      fetchGaps(choice.versionId as string, choice.frameworkId as string, choice.method),
    enabled: ready,
  });
  return (
    <Page title={t('reports.gaps.title')} description={t('reports.gaps.description')}>
      <Stack gap="lg">
        <Paper withBorder className={classes.card}>
          <CoverageControls choice={choice} definition={report.data?.definition} />
        </Paper>
        {!ready && <Text c="dimmed">{t('reports.coverage.choose')}</Text>}
        {ready && report.isLoading && <LoadingState />}
        {ready && report.isError && (
          <ErrorState
            title={t('reports.errorTitle')}
            body={
              isApiError(report.error, 403)
                ? t('reports.forbidden')
                : isApiError(report.error, 404)
                  ? t('reports.notFound')
                  : t('reports.errorBody')
            }
          />
        )}
        {report.data && (
          <>
            <MetaPanel report={report.data} method={choice.method} />
            <GapItems report={report.data} />
            <ObjectiveList
              versionId={choice.versionId as string}
              title={t('reports.gaps.unlinkedTitle')}
              help={t('reports.gaps.unlinkedHelp')}
              total={report.data.unlinked_total}
              rows={report.data.unlinked}
            />
            <ObjectiveList
              versionId={choice.versionId as string}
              title={t('reports.gaps.waitingTitle')}
              help={t('reports.gaps.waitingHelp')}
              total={report.data.only_waiting_total}
              rows={report.data.only_waiting}
            />
            <Group>
              <Link to={`/reports/coverage${search}`}>
                {t('reports.gaps.toCoverage')}
              </Link>
            </Group>
          </>
        )}
      </Stack>
    </Page>
  );
}
