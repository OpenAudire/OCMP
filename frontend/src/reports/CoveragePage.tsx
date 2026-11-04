import { Alert, Badge, Group, Paper, Stack, Table, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { fetchCoverage, queryKeys } from '../api/endpoints';
import type { CoverageItem, CoverageMethod, CoverageReport, ItemStatus } from '../api/types';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import { CoverageControls } from './CoverageControls';
import { ExportLinks } from './ExportLinks';
import { METHODS, useChoice } from './useChoice';
import classes from './Coverage.module.css';
import { formatMade, percent, shadeOf } from './coverageFormat';

const STATUS_CLASS: Record<ItemStatus, string> = {
  covered: classes.statusCovered,
  partial: classes.statusPartial,
  none: classes.statusNone,
};

/** The label of an item's status; a group says how many of its items are covered. */
function StatusText({ t, item }: { t: TFunction; item: CoverageItem }) {
  return (
    <span className={STATUS_CLASS[item.status]}>
      {t(`reports.status.${item.status}`)}
      {!item.is_leaf && item.leaves_covered !== null
        ? ` · ${t('reports.coverage.ofItems', { covered: item.leaves_covered, total: item.leaves })}`
        : ''}
    </span>
  );
}

export function MetaPanel({
  report,
  method,
}: {
  report: Pick<CoverageReport, 'framework' | 'version' | 'definition' | 'generated_at' | 'partial'>;
  method: CoverageMethod;
}) {
  const { t, i18n } = useTranslation();
  return (
    <Paper
      withBorder
      component="section"
      className={classes.card}
      aria-label={t('reports.coverage.methodStated')}
    >
      <dl className={classes.meta}>
        <dt>{t('reports.coverage.method')}</dt>
        <dd>
          {t(`reports.methods.${method}`)}. {report.definition}
        </dd>
        <dt>{t('reports.coverage.framework')}</dt>
        <dd>
          {report.framework.name} ({report.framework.version_label})
        </dd>
        <dt>{t('reports.coverage.version')}</dt>
        <dd>
          {report.version.programme_code} · {report.version.academic_year} ·{' '}
          {t(`curriculum.versionStatus.${report.version.status}`)}
        </dd>
        <dt>{t('reports.coverage.madeOn')}</dt>
        <dd>{formatMade(report.generated_at, i18n.language)}</dd>
      </dl>
      <Text size="sm" c="dimmed">
        {t('reports.coverage.acceptedOnly')}
      </Text>
      {report.partial && (
        <Alert color="ochre" variant="light">
          {t('reports.coverage.partial')}
        </Alert>
      )}
    </Paper>
  );
}

function Summary({ report }: { report: CoverageReport }) {
  const { t } = useTranslation();
  const s = report.summary;
  return (
    <section aria-labelledby="coverage-summary">
      <Title order={2} id="coverage-summary" className={classes.title}>
        {t('reports.coverage.summaryTitle')}
      </Title>
      <Text size="sm" c="dimmed">
        {t('reports.coverage.summaryHelp', { items: s.leaves, groups: s.groups })}
      </Text>
      <Table.ScrollContainer minWidth={560}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('reports.coverage.method')}</Table.Th>
              <Table.Th>{t('reports.coverage.headline')}</Table.Th>
              <Table.Th>{t('reports.status.covered')}</Table.Th>
              <Table.Th>{t('reports.status.partial')}</Table.Th>
              <Table.Th>{t('reports.status.none')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {METHODS.map((m) => {
              const figure = s.methods[m];
              return (
                <Table.Tr key={m} data-current={m === report.method}>
                  <Table.Th scope="row">
                    {t(`reports.methods.${m}`)}
                    {m === report.method && ` ${t('reports.coverage.shown')}`}
                  </Table.Th>
                  <Table.Td>
                    <strong>{figure.headline === null ? '–' : percent(figure.headline)}</strong>{' '}
                    <Text span size="sm" c="dimmed">
                      {t(`reports.headline.${m}`)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {figure.covered} {t(`reports.unit.${figure.unit}`)}
                  </Table.Td>
                  <Table.Td>{figure.partial}</Table.Td>
                  <Table.Td>{figure.uncovered}</Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Group gap="md" mt="sm">
        <Text size="sm">{t('reports.coverage.linksCounted', { count: s.links - s.group_links })}</Text>
        {s.group_links > 0 && (
          <Badge variant="outline" color="gray">
            {t('reports.coverage.groupLinks', { count: s.group_links })}
          </Badge>
        )}
        {s.bulk_links > 0 && (
          <Badge variant="light" color="gray">
            {t('reports.coverage.bulkLinks', { count: s.bulk_links })}
          </Badge>
        )}
        {s.recheck_links > 0 && (
          <Badge variant="light" color="ochre">
            {t('reports.coverage.recheckLinks', { count: s.recheck_links })}
          </Badge>
        )}
        {s.waiting_links > 0 && (
          <Badge variant="outline" color="gray">
            {t('reports.coverage.waitingLinks', { count: s.waiting_links })}
          </Badge>
        )}
      </Group>
    </section>
  );
}

function Heatmap({ report }: { report: CoverageReport }) {
  const { t } = useTranslation();
  const columns = report.columns.map((c) => ({
    ...c,
    text:
      c.kind === 'phase'
        ? c.label
        : c.kind === 'programme'
          ? t('reports.coverage.programmeOutcomes')
          : t('reports.coverage.noPhase'),
  }));
  return (
    <section aria-labelledby="coverage-heatmap">
      <Title order={2} id="coverage-heatmap" className={classes.title}>
        {t('reports.coverage.heatmapTitle')}
      </Title>
      <Text size="sm" c="dimmed">
        {t('reports.coverage.heatmapHelp')}
      </Text>
      <Table.ScrollContainer minWidth={520}>
        <table className={classes.heat}>
          <thead>
            <tr>
              <th scope="col">{t('reports.coverage.group')}</th>
              <th scope="col">{t('reports.coverage.allPhases')}</th>
              {columns.map((c) => (
                <th key={c.key} scope="col">
                  {c.text}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.heatmap.map((row) => (
              <tr key={row.id}>
                <th scope="row">
                  <span className={classes.itemCode}>{row.code}</span> {row.title}
                </th>
                {['all', ...columns.map((c) => c.key)].map((key) => (
                  <td key={key} data-level={shadeOf(row.cells[key] ?? 0)}>
                    {percent(row.cells[key] ?? 0)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Table.ScrollContainer>
    </section>
  );
}

function Items({ report }: { report: CoverageReport }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="coverage-items">
      <Title order={2} id="coverage-items" className={classes.title}>
        {t('reports.coverage.itemsTitle')}
      </Title>
      <Table.ScrollContainer minWidth={720}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('reports.coverage.item')}</Table.Th>
              <Table.Th>{t('reports.coverage.statusColumn')}</Table.Th>
              <Table.Th>{t('reports.coverage.value')}</Table.Th>
              <Table.Th>{t('reports.coverage.links')}</Table.Th>
              <Table.Th>{t('reports.coverage.flags')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {report.items.map((item) => (
              <Table.Tr key={item.id}>
                <Table.Th scope="row" fw={item.is_leaf ? 400 : 600}>
                  <span className={classes[`indent${Math.min(item.depth, 3)}`]}>
                    <span className={classes.itemCode}>{item.code}</span> {item.title}
                  </span>
                </Table.Th>
                <Table.Td>
                  <StatusText t={t} item={item} />
                </Table.Td>
                <Table.Td>{percent(item.value)}</Table.Td>
                <Table.Td>
                  {item.is_leaf ? (
                    <>
                      {item.links}
                      {item.objectives !== item.links && item.links > 0
                        ? ` (${t('reports.coverage.objectivesCount', { count: item.objectives })})`
                        : ''}
                    </>
                  ) : item.links > 0 ? (
                    <Text size="sm" c="dimmed">
                      {t('reports.coverage.madeToGroup', { count: item.links })}
                    </Text>
                  ) : (
                    '–'
                  )}
                </Table.Td>
                <Table.Td>
                  <div className={classes.flags}>
                    {item.only_bulk && (
                      <Badge variant="light" color="gray" size="sm">
                        {t('reports.coverage.onlyBulk')}
                      </Badge>
                    )}
                    {!item.only_bulk && item.bulk_links > 0 && (
                      <Badge variant="light" color="gray" size="sm">
                        {t('reports.coverage.someBulk', { count: item.bulk_links })}
                      </Badge>
                    )}
                    {item.recheck_links > 0 && (
                      <Badge variant="light" color="ochre" size="sm">
                        {t('reports.coverage.recheck', { count: item.recheck_links })}
                      </Badge>
                    )}
                    {item.waiting > 0 && (
                      <Badge variant="outline" color="gray" size="sm">
                        {t('reports.coverage.waiting', { count: item.waiting })}
                      </Badge>
                    )}
                  </div>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </section>
  );
}

/** `/reports/coverage`: how well a framework is covered by the accepted links of a version,
 * by one of four labelled methods, with a heatmap of framework groups by phase. */
export function CoveragePage() {
  const { t } = useTranslation();
  const choice = useChoice();
  const ready = choice.versionId !== null && choice.frameworkId !== null;
  const report = useQuery({
    queryKey: queryKeys.coverage(choice.versionId ?? '', choice.frameworkId ?? '', choice.method),
    queryFn: () =>
      fetchCoverage(choice.versionId as string, choice.frameworkId as string, choice.method),
    enabled: ready,
  });
  return (
    <Page title={t('reports.coverage.title')} description={t('reports.coverage.description')}>
      <Stack gap="lg">
        <Paper withBorder className={classes.card}>
          <CoverageControls choice={choice} definition={report.data?.definition} />
        </Paper>
        {report.data && (
          <ExportLinks
            versionId={choice.versionId}
            frameworkId={choice.frameworkId}
            reportKey="coverage"
            method={choice.method}
          />
        )}
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
            <Summary report={report.data} />
            <Heatmap report={report.data} />
            <Items report={report.data} />
          </>
        )}
      </Stack>
    </Page>
  );
}
