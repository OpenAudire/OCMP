import { Alert, NativeSelect, Paper, Stack, Table, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import { fetchFrameworkLibrary, fetchReport, queryKeys, reportExportUrl } from '../api/endpoints';
import type { ReportColumn, ReportDocument } from '../api/types';
import { defaultVersionId, rememberedVersion, useProgrammes } from '../curriculum/currentVersion';
import { versionLabel } from '../curriculum/versions';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import { REPORT_PAGES } from './reportPages';
import classes from './Coverage.module.css';
import { formatMade, percent } from './coverageFormat';
import { ExportLinksFor } from './ExportLinks';
import { IntendedRepeatsPanel } from './IntendedRepeatsPanel';

function cell(value: string | number | null, column: ReportColumn): string {
  if (value === null || value === '') return '–';
  if (typeof value === 'number') {
    if (column.kind === 'percent') return percent(value);
    if (column.kind === 'number') return value.toFixed(2);
  }
  return String(value);
}

function Sections({ report }: { report: ReportDocument }) {
  const { t } = useTranslation();
  return (
    <>
      {report.sections.map((section) => {
        const id = `section-${section.title.replace(/\W+/g, '-').toLowerCase()}`;
        return (
          <section key={section.title} aria-labelledby={id}>
            <Title order={2} id={id} className={classes.title}>
              {section.title}
            </Title>
            {section.note && (
              <Text size="sm" c="dimmed">
                {section.note}
              </Text>
            )}
            {section.rows.length === 0 ? (
              <Text mt="xs">{t('reports.generic.none')}</Text>
            ) : (
              <Table.ScrollContainer minWidth={Math.max(520, section.columns.length * 130)}>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      {section.columns.map((column) => (
                        <Table.Th key={column.label}>{column.label}</Table.Th>
                      ))}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {section.rows.map((row, index) => (
                      <Table.Tr key={index}>
                        {section.columns.map((column, c) => (
                          <Table.Td key={column.label}>{cell(row[c] ?? null, column)}</Table.Td>
                        ))}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </section>
        );
      })}
    </>
  );
}

/** `/reports/:key`: a report built on the server as tables (redundancy, traceability and the
 * teaching reports), with how it was made and the Excel and PDF downloads. */
export function ReportPage() {
  const { t, i18n } = useTranslation();
  const { key = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const config = REPORT_PAGES[key];
  const programmes = useProgrammes();
  const library = useQuery({
    queryKey: queryKeys.frameworks,
    queryFn: fetchFrameworkLibrary,
    enabled: config?.framework !== 'none',
  });
  const versions = (programmes.data ?? []).flatMap((p) =>
    p.versions.map((v) => ({ value: v.id, label: `${p.code} · ${versionLabel(t, v)}` }))
  );
  const versionId =
    params.get('version') ??
    (programmes.data ? defaultVersionId(programmes.data, rememberedVersion()) : null);
  const usable = (library.data?.frameworks ?? []).filter((f) => f.status !== 'draft');
  const needsFramework = config?.framework === 'required';
  const frameworkId =
    params.get('framework') ?? (needsFramework ? (usable[0]?.id ?? null) : null);
  const ready = versionId !== null && (!needsFramework || frameworkId !== null);
  const query: Record<string, string> = frameworkId ? { framework_id: frameworkId } : {};
  const report = useQuery({
    queryKey: queryKeys.report(versionId ?? '', key, query),
    queryFn: () => fetchReport(versionId as string, key, query),
    enabled: ready && config !== undefined,
  });
  if (!config) return <Navigate to="/reports" replace />;

  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [name, value] of Object.entries(changes)) {
      if (value) next.set(name, value);
      else next.delete(name);
    }
    setParams(next, { replace: true });
  };
  return (
    <Page title={t(`reports.pages.${key}.title`)} description={t(`reports.pages.${key}.description`)}>
      <Stack gap="lg">
        <Paper withBorder className={classes.card}>
          <div className={classes.controls}>
            <NativeSelect
              label={t('reports.coverage.version')}
              value={versionId ?? ''}
              onChange={(event) => set({ version: event.currentTarget.value })}
              data={versions}
            />
            {config.framework !== 'none' && (
              <NativeSelect
                label={t('reports.coverage.framework')}
                value={frameworkId ?? ''}
                onChange={(event) => set({ framework: event.currentTarget.value })}
                data={[
                  ...(config.framework === 'optional'
                    ? [{ value: '', label: t('reports.generic.allFrameworks') }]
                    : []),
                  ...usable.map((f) => ({ value: f.id, label: `${f.name} (${f.version_label})` })),
                ]}
              />
            )}
          </div>
        </Paper>
        {!ready && <Text c="dimmed">{t('reports.generic.choose')}</Text>}
        {ready && report.isLoading && <LoadingState />}
        {ready && report.isError && (
          <ErrorState
            title={t('reports.errorTitle')}
            body={
              isApiError(report.error, 403)
                ? t('reports.forbidden')
                : isApiError(report.error, 404)
                  ? t('reports.notFound')
                  : isApiError(report.error, 422) && report.error.message
                    ? report.error.message
                    : t('reports.errorBody')
            }
          />
        )}
        {report.data && versionId && (
          <>
            <ExportLinksFor
              href={(format) => reportExportUrl(versionId, key, { format, ...query })}
            />
            <Paper
              withBorder
              component="section"
              className={classes.card}
              aria-label={t('reports.coverage.methodStated')}
            >
              <dl className={classes.meta}>
                {report.data.about.map((line) => (
                  <div key={line.label} className={classes.metaRow}>
                    <dt>{line.label}</dt>
                    <dd>{line.value}</dd>
                  </div>
                ))}
              </dl>
              <Text size="sm" c="dimmed">
                {t('reports.generic.madeNote', {
                  made: formatMade(report.data.made_on, i18n.language),
                })}
              </Text>
              {report.data.about.some((l) => l.label === 'Only part of the curriculum') && (
                <Alert color="ochre" variant="light">
                  {t('reports.coverage.partial')}
                </Alert>
              )}
            </Paper>
            <Sections report={report.data} />
            {key === 'redundancy' && frameworkId && (
              <IntendedRepeatsPanel
                versionId={versionId}
                frameworkId={frameworkId}
                report={report.data}
              />
            )}
          </>
        )}
      </Stack>
    </Page>
  );
}
