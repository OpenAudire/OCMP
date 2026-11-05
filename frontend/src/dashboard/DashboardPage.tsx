import { useEffect, useState } from 'react';
import { Alert, Badge, Checkbox, NativeSelect, Paper, Table, Text, Title } from '@mantine/core';
import { IconLayoutDashboard } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';

import { fetchDashboard, fetchDashboardTrace, queryKeys } from '../api/endpoints';
import type { Dashboard, DashboardKpi } from '../api/types';
import { defaultVersionId, rememberedVersion, useProgrammes } from '../curriculum/currentVersion';
import { versionLabel } from '../curriculum/versions';
import { formatMade, percent } from '../reports/coverageFormat';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import classes from './Dashboard.module.css';
import { Sparkline } from './Sparkline';
import { TraceDiagram } from './TraceDiagram';

/** Whether a rise in this indicator is good news. */
const RISE_IS_GOOD: Record<DashboardKpi['key'], boolean> = {
  mapped: true,
  coverage: true,
  gaps: false,
  credits: false,
};

function figure(kpi: DashboardKpi): string {
  if (kpi.value === null) return '–';
  return kpi.unit === 'percent' ? percent(kpi.value) : String(kpi.value);
}

/** How the indicator moved over the trend, in words: "up 20 points since 2026-09-10". */
function changeOf(t: TFunction, kpi: DashboardKpi): { text: string; good: boolean | null } | null {
  if (kpi.series.length < 2) return null;
  const first = kpi.series[0];
  const last = kpi.series[kpi.series.length - 1];
  const delta = last.value - first.value;
  const size = kpi.unit === 'percent' ? Math.round(Math.abs(delta) * 100) : Math.abs(delta);
  if (size === 0) return { text: t('dashboard.kpi.same', { date: first.date }), good: null };
  const key = kpi.unit === 'percent' ? 'points' : 'count';
  const direction = delta > 0 ? 'up' : 'down';
  return {
    text: t(`dashboard.kpi.${direction}_${key}`, { count: size, date: first.date }),
    good: delta > 0 === RISE_IS_GOOD[kpi.key],
  };
}

function KpiCard({ kpi, dashboard }: { kpi: DashboardKpi; dashboard: Dashboard }) {
  const { t } = useTranslation();
  const change = changeOf(t, kpi);
  let note = '';
  if (kpi.key === 'mapped' && kpi.numerator !== null && kpi.denominator !== null) {
    note = t('dashboard.kpi.mappedNote', { mapped: kpi.numerator, total: kpi.denominator });
  } else if (kpi.key === 'coverage') {
    note = dashboard.framework
      ? t('dashboard.kpi.coverageNote', { framework: dashboard.framework.name })
      : t('dashboard.kpi.noFramework');
  } else if (kpi.key === 'gaps' && kpi.denominator !== null) {
    note = t('dashboard.kpi.gapsNote', { total: kpi.denominator });
  } else if (kpi.key === 'credits' && kpi.denominator !== null) {
    note = t('dashboard.kpi.creditsNote', {
      total: kpi.denominator,
      tolerance: dashboard.credits.tolerance_percent,
    });
  }
  const label = t(`dashboard.kpi.${kpi.key}`);
  return (
    <Paper withBorder component="article" className={`${classes.card} ${classes.kpi}`}>
      <span className={classes.kpiLabel}>{label}</span>
      <div className={classes.kpiRow}>
        <span className={classes.kpiValue}>{figure(kpi)}</span>
        <Sparkline
          points={kpi.series}
          label={t('dashboard.kpi.trendLabel', {
            kpi: label,
            from: kpi.series[0] ? figure({ ...kpi, value: kpi.series[0].value }) : '',
            to: kpi.series.length ? figure({ ...kpi, value: kpi.series[kpi.series.length - 1].value }) : '',
          })}
        />
      </div>
      <span className={classes.kpiNote}>{note}</span>
      {change && (
        <span
          className={classes.kpiChange}
          data-good={change.good === null ? undefined : String(change.good)}
        >
          {change.text}
        </span>
      )}
    </Paper>
  );
}

function Comparison({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useTranslation();
  const compare = dashboard.comparison;
  return (
    <Paper withBorder component="section" className={classes.card} aria-labelledby="dash-compare">
      <Title order={2} id="dash-compare" className={classes.title}>
        {t('dashboard.compare.title')}
      </Title>
      {!compare || !dashboard.framework ? (
        <Text c="dimmed">{t(dashboard.framework ? 'dashboard.compare.none' : 'dashboard.kpi.noFramework')}</Text>
      ) : (
        <>
          <Text size="sm" c="dimmed">
            {t('dashboard.compare.help', {
              framework: dashboard.framework.name,
              year: compare.academic_year,
              low: dashboard.low_percent,
            })}
          </Text>
          <div className={classes.bars}>
            {compare.groups.map((g) => {
              const low = g.now * 100 < dashboard.low_percent;
              return (
                <div key={g.id} className={classes.barRow}>
                  <div className={classes.barRowHead}>
                    <span className={classes.code}>{g.code}</span>
                    <span>{g.title}</span>
                  </div>
                  <div
                    className={classes.barTrack}
                    role="img"
                    aria-label={t('dashboard.compare.aria', {
                      group: g.title,
                      now: percent(g.now),
                      before: g.before === null ? '–' : percent(g.before),
                      year: compare.academic_year,
                    })}
                  >
                    {g.before !== null && (
                      <div className={classes.barBefore} style={{ width: `${g.before * 100}%` }} />
                    )}
                    <div
                      className={classes.barNow}
                      data-low={low ? 'true' : undefined}
                      style={{ width: `${g.now * 100}%` }}
                    />
                  </div>
                  <span className={classes.barValue}>
                    {percent(g.now)}
                    {low && (
                      <Badge ml={6} size="xs" variant="light" color="ochre">
                        {t('dashboard.compare.low')}
                      </Badge>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
          <div className={classes.legend}>
            <span>
              <span className={classes.swatch} style={{ background: 'var(--cic-brand)' }} />
              {t('dashboard.compare.thisVersion')}
            </span>
            <span>
              <span className={classes.swatch} style={{ background: 'var(--cic-line)' }} />
              {t('dashboard.compare.before', { year: compare.academic_year })}
            </span>
            <span>
              <span className={classes.swatch} style={{ background: 'var(--cic-warm)' }} />
              {t('dashboard.compare.belowLow', { low: dashboard.low_percent })}
            </span>
          </div>
        </>
      )}
    </Paper>
  );
}

function Progress({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useTranslation();
  return (
    <Paper withBorder component="section" className={classes.card} aria-labelledby="dash-progress">
      <Title order={2} id="dash-progress" className={classes.title}>
        {t('dashboard.progress.title')}
      </Title>
      <Text size="sm" c="dimmed">
        {t('dashboard.progress.help')}
      </Text>
      {dashboard.progress.length === 0 ? (
        <Text c="dimmed">{t('dashboard.progress.none')}</Text>
      ) : (
        <div className={classes.bars}>
          {dashboard.progress.map((p) => {
            const share = p.objectives ? p.mapped / p.objectives : 0;
            return (
              <div key={p.module_id} className={classes.barRow}>
                <div className={classes.barRowHead}>
                  <span className={classes.code}>{p.code}</span>
                  <span>{p.name}</span>
                </div>
                <div
                  className={classes.barTrack}
                  role="img"
                  aria-label={t('dashboard.progress.aria', {
                    module: p.name,
                    mapped: p.mapped,
                    total: p.objectives,
                  })}
                >
                  <div className={classes.barBefore} style={{ width: `${share * 100}%` }} />
                </div>
                <span className={classes.barValue}>
                  {p.objectives ? percent(share) : '–'}
                  {p.waiting > 0 && (
                    <Badge ml={6} size="xs" variant="outline" color="gray">
                      {t('dashboard.progress.waiting', { count: p.waiting })}
                    </Badge>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Paper>
  );
}

function Credits({ dashboard }: { dashboard: Dashboard }) {
  const { t } = useTranslation();
  const [onlyIssues, setOnlyIssues] = useState(false);
  const c = dashboard.credits;
  const rows = c.modules.filter((m) => !onlyIssues || m.status === 'under' || m.status === 'over');
  const total = c.years.map((y) => `${y.name}: ${y.credits}`).join(' · ');
  return (
    <Paper withBorder component="section" className={classes.card} aria-labelledby="dash-credits">
      <Title order={2} id="dash-credits" className={classes.title}>
        {t('dashboard.credits.title')}
      </Title>
      <Text size="sm" c="dimmed">
        {t('dashboard.credits.help', { hours: c.hours_per_credit, tolerance: c.tolerance_percent })}
        {total ? ` ${total}.` : ''}
      </Text>
      <Checkbox
        mt="sm"
        mb="sm"
        checked={onlyIssues}
        onChange={(event) => setOnlyIssues(event.currentTarget.checked)}
        label={t('dashboard.credits.onlyIssues')}
      />
      <Table.ScrollContainer minWidth={560}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('dashboard.credits.module')}</Table.Th>
              <Table.Th className={classes.num}>{t('dashboard.credits.credits')}</Table.Th>
              <Table.Th className={classes.num}>{t('dashboard.credits.expected')}</Table.Th>
              <Table.Th className={classes.num}>{t('dashboard.credits.planned')}</Table.Th>
              <Table.Th className={classes.num}>{t('dashboard.credits.difference')}</Table.Th>
              <Table.Th>{t('dashboard.credits.status')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((m) => (
              <Table.Tr key={m.module_id}>
                <Table.Td>
                  <span className={classes.code}>{m.code}</span> {m.name}
                </Table.Td>
                <Table.Td className={classes.num}>{m.credits ?? '–'}</Table.Td>
                <Table.Td className={classes.num}>
                  {m.expected_hours === null ? '–' : `${m.expected_hours} h`}
                </Table.Td>
                <Table.Td className={classes.num}>{m.planned_hours} h</Table.Td>
                <Table.Td className={classes.num}>
                  {m.difference_percent === null
                    ? '–'
                    : `${m.difference_percent > 0 ? '+' : ''}${m.difference_percent}%`}
                </Table.Td>
                <Table.Td>
                  <span
                    className={
                      m.status === 'ok' || m.status === 'no_credits'
                        ? classes.statusOk
                        : classes.statusIssue
                    }
                  >
                    {t(`dashboard.credits.statuses.${m.status}`)}
                  </span>
                </Table.Td>
              </Table.Tr>
            ))}
            {rows.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={6}>
                  <Text c="dimmed">{t('dashboard.credits.noRows')}</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}

function Traceability({
  versionId,
  frameworkId,
}: {
  versionId: string;
  frameworkId: string | null;
}) {
  const { t } = useTranslation();
  const [outcomeId, setOutcomeId] = useState<string | null>(null);
  const trace = useQuery({
    queryKey: queryKeys.dashboardTrace(versionId, frameworkId, outcomeId),
    queryFn: () => fetchDashboardTrace(versionId, frameworkId, outcomeId),
  });
  const data = trace.data;
  return (
    <Paper withBorder component="section" className={classes.card} aria-labelledby="dash-trace">
      <Title order={2} id="dash-trace" className={classes.title}>
        {t('dashboard.trace.title')}
      </Title>
      <Text size="sm" c="dimmed">
        {t('dashboard.trace.help')}
      </Text>
      {trace.isPending && <LoadingState title={t('dashboard.loading')} skeletons={1} />}
      {trace.isError && (
        <ErrorState title={t('dashboard.trace.error')} body={t('dashboard.trace.errorBody')} />
      )}
      {data && !data.outcome && <Text c="dimmed">{t('dashboard.trace.none')}</Text>}
      {data?.outcome && (
        <>
          <NativeSelect
            mt="sm"
            label={t('dashboard.trace.choose')}
            value={data.outcome.id}
            onChange={(event) => setOutcomeId(event.currentTarget.value)}
            data={data.outcomes.map((o) => ({ value: o.id, label: o.text.slice(0, 90) }))}
          />
          <TraceDiagram trace={data} />
          <Text mt="sm">
            {t('dashboard.trace.summary', {
              objectives: data.session_objectives,
              modules: data.module_count,
              sessions: data.sessions,
              items: data.items_total,
            })}
            {data.items_total > data.items.length
              ? ` ${t('dashboard.trace.moreItems', { shown: data.items.length })}`
              : ''}
            {!data.framework ? ` ${t('dashboard.trace.noFramework')}` : ''}
          </Text>
        </>
      )}
    </Paper>
  );
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const programmes = useProgrammes();
  const versionId =
    params.get('version') ??
    (programmes.data ? defaultVersionId(programmes.data, rememberedVersion()) : null);
  const frameworkId = params.get('framework');
  const dashboard = useQuery({
    queryKey: queryKeys.dashboard(versionId ?? '', frameworkId),
    queryFn: () => fetchDashboard(versionId as string, frameworkId),
    enabled: !!versionId,
  });
  const data = dashboard.data;

  useEffect(() => {
    if (versionId && !params.get('version')) {
      const next = new URLSearchParams(params);
      next.set('version', versionId);
      setParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId]);

  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  };

  const versions = (programmes.data ?? []).flatMap((p) =>
    p.versions.map((v) => ({ value: v.id, label: `${p.code} · ${versionLabel(t, v)}` }))
  );

  if (programmes.isPending || (!!versionId && dashboard.isPending)) {
    return (
      <Page title={t('dashboard.title')}>
        <LoadingState title={t('dashboard.loading')} />
      </Page>
    );
  }
  if (programmes.isError || dashboard.isError) {
    return (
      <Page title={t('dashboard.title')}>
        <ErrorState title={t('dashboard.error')} body={t('dashboard.errorBody')} />
      </Page>
    );
  }
  if (!versionId || !data) {
    return (
      <Page title={t('dashboard.title')}>
        <EmptyState
          icon={IconLayoutDashboard}
          title={t('dashboard.empty.title')}
          body={t('dashboard.empty.body')}
        />
      </Page>
    );
  }

  return (
    <Page
      title={t('dashboard.title')}
      description={t('dashboard.description', {
        programme: data.version.programme_name,
        year: data.version.academic_year,
        status: t(`curriculum.versionStatus.${data.version.status}`).toLocaleLowerCase(),
      })}
    >
      <div className={classes.controls}>
        <NativeSelect
          label={t('reports.coverage.version')}
          value={versionId}
          onChange={(event) => set({ version: event.currentTarget.value, framework: '' })}
          data={versions}
        />
        {data.frameworks.length > 1 && (
          <NativeSelect
            label={t('reports.coverage.framework')}
            value={data.framework?.id ?? ''}
            onChange={(event) => set({ framework: event.currentTarget.value })}
            data={data.frameworks.map((f) => ({ value: f.id, label: `${f.name} (${f.version_label})` }))}
          />
        )}
      </div>
      {data.partial && (
        <Alert color="ochre" variant="light">
          {t('dashboard.partial')}
        </Alert>
      )}
      <section aria-label={t('dashboard.kpi.section')} className={classes.kpis}>
        {data.kpis.map((kpi) => (
          <KpiCard key={kpi.key} kpi={kpi} dashboard={data} />
        ))}
      </section>
      <Text size="sm" c="dimmed">
        {data.snapshot_on
          ? t('dashboard.snapshotOn', { date: data.snapshot_on })
          : t('dashboard.noSnapshots')}{' '}
        {t('dashboard.madeOn', { when: formatMade(data.generated_at, i18n.language) })}
      </Text>
      <Traceability key={versionId} versionId={versionId} frameworkId={data.framework?.id ?? null} />
      <div className={classes.two}>
        <Comparison dashboard={data} />
        <Progress dashboard={data} />
      </div>
      <Credits dashboard={data} />
    </Page>
  );
}
