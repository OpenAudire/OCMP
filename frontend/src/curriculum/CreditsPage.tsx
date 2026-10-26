import { Box, Button, Paper, Text } from '@mantine/core';
import { IconArrowLeft, IconSum } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { isApiError } from '../api/client';
import { fetchCreditCheck, queryKeys } from '../api/endpoints';
import type { VersionCreditCheck, YearStatus } from '../api/types';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { HoursStatusLine, StatusLine } from './CreditAdvice';
import { findVersion, useProgrammes } from './currentVersion';
import { CURRICULUM_PATH, versionPath } from './paths';
import { useNumber } from './useNumber';
import { VersionSwitcher } from './VersionSwitcher';
import classes from './CreditsPage.module.css';

function yearTone(status: YearStatus): 'good' | 'attention' | 'neutral' {
  if (status === 'ok') return 'good';
  return status === 'not_checked' ? 'neutral' : 'attention';
}

function Summary({ check }: { check: VersionCreditCheck }) {
  const { t } = useTranslation();
  const number = useNumber();
  const { policy } = check;
  return (
    <Paper
      withBorder
      component="section"
      aria-labelledby="credits-summary"
      className={classes.card}
    >
      <h2 id="credits-summary" className={classes.sectionTitle}>
        {t('curriculum.credits.page.summary')}
      </h2>
      <dl className={classes.facts}>
        <div className={classes.fact}>
          <dt>{t('curriculum.credits.page.totalCredits')}</dt>
          <dd>{number(check.total_credits)}</dd>
        </div>
        {check.programme_total_credits !== null && (
          <div className={classes.fact}>
            <dt>{t('curriculum.details.totalCredits')}</dt>
            <dd>{number(check.programme_total_credits)}</dd>
          </div>
        )}
        {check.qualification_name && check.qualification_min_credits !== null && (
          <div className={classes.fact}>
            <dt>{check.qualification_name}</dt>
            <dd>
              {t('curriculum.credits.page.minimum', {
                value: number(check.qualification_min_credits),
              })}
            </dd>
          </div>
        )}
        {check.exit_level !== null && (
          <div className={classes.fact}>
            <dt>{t('curriculum.details.nqfExitLevel')}</dt>
            <dd>{check.exit_level}</dd>
          </div>
        )}
      </dl>
      <Text size="sm" c="dimmed">
        {t('curriculum.credits.page.policy', {
          hours: policy.hours_per_credit,
          tolerance: policy.tolerance_percent,
          year: policy.credits_per_year,
        })}
      </Text>
      {check.findings.length === 0 ? (
        <div>
          <StatusLine tone="good">{t('curriculum.credits.page.noFindings')}</StatusLine>
        </div>
      ) : (
        <ul className={classes.findings}>
          {check.findings.map((finding) => (
            <li key={finding.code}>
              <StatusLine tone="attention">
                {t(`curriculum.credits.finding.${finding.code}`, finding.params)}
              </StatusLine>
            </li>
          ))}
        </ul>
      )}
      <Text size="sm" c="dimmed">
        {t('curriculum.credits.page.verify')}
      </Text>
    </Paper>
  );
}

function Years({ check }: { check: VersionCreditCheck }) {
  const { t } = useTranslation();
  const number = useNumber();
  if (check.years.length === 0 && check.unphased_modules === 0) return null;
  return (
    <Paper withBorder component="section" aria-labelledby="credits-years" className={classes.card}>
      <h2 id="credits-years" className={classes.sectionTitle}>
        {t('curriculum.credits.page.years', { phases: t('terms.phase', { count: 2 }) })}
      </h2>
      <div
        className={classes.scroll}
        role="group"
        aria-labelledby="credits-years"
        tabIndex={0}
      >
        <table className={classes.table}>
          <thead>
            <tr>
              <th scope="col">{t('curriculum.credits.page.name')}</th>
              <th scope="col">{t('curriculum.details.kind')}</th>
              <th scope="col" className={classes.num}>
                {t('curriculum.details.credits')}
              </th>
              <th scope="col">{t('curriculum.credits.page.check')}</th>
            </tr>
          </thead>
          <tbody>
            {check.years.map((year) => (
              <tr key={year.phase_id}>
                <th scope="row">{year.name}</th>
                <td>{t(`curriculum.phaseKind.${year.kind}`)}</td>
                <td className={classes.num}>{number(year.credits)}</td>
                <td>
                  <StatusLine tone={yearTone(year.status)}>
                    {t(`curriculum.credits.yearStatus.${year.status}`, {
                      credits: number(year.credits),
                      expected: year.expected_credits ?? 0,
                    })}
                  </StatusLine>
                  {year.modules_without_credits > 0 && (
                    <Text size="sm" c="dimmed">
                      {t('curriculum.credits.page.withoutCredits', {
                        count: year.modules_without_credits,
                      })}
                    </Text>
                  )}
                </td>
              </tr>
            ))}
            {check.unphased_modules > 0 && (
              <tr>
                <th scope="row">{t('curriculum.tree.longitudinal')}</th>
                <td>{t('curriculum.credits.page.notAPhase')}</td>
                <td className={classes.num}>{number(check.unphased_credits)}</td>
                <td>
                  <StatusLine tone="neutral">
                    {t('curriculum.credits.yearStatus.not_checked')}
                  </StatusLine>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Paper>
  );
}

function Levels({ check }: { check: VersionCreditCheck }) {
  const { t } = useTranslation();
  const number = useNumber();
  return (
    <Paper withBorder component="section" aria-labelledby="credits-levels" className={classes.card}>
      <h2 id="credits-levels" className={classes.sectionTitle}>
        {t('curriculum.credits.page.levels')}
      </h2>
      <div
        className={classes.scroll}
        role="group"
        aria-labelledby="credits-levels"
        tabIndex={0}
      >
        <table className={classes.table}>
          <thead>
            <tr>
              <th scope="col">{t('curriculum.details.nqfLevel')}</th>
              <th scope="col" className={classes.num}>
                {t('curriculum.details.credits')}
              </th>
              <th scope="col" className={classes.num}>
                {t('terms.module', { count: 2 })}
              </th>
            </tr>
          </thead>
          <tbody>
            {check.levels.map((row) => (
              <tr key={row.level ?? 'none'}>
                <th scope="row">
                  {row.level === null ? t('curriculum.credits.page.noLevel') : row.level}
                  {row.level !== null && row.level === check.exit_level && (
                    <span className={classes.note}>
                      {' '}
                      ({t('curriculum.credits.page.exitLevel')})
                    </span>
                  )}
                </th>
                <td className={classes.num}>{number(row.credits)}</td>
                <td className={classes.num}>{number(row.modules, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Paper>
  );
}

function Modules({ check, versionId }: { check: VersionCreditCheck; versionId: string }) {
  const { t } = useTranslation();
  const number = useNumber();
  return (
    <Paper
      withBorder
      component="section"
      aria-labelledby="credits-modules"
      className={classes.card}
    >
      <h2 id="credits-modules" className={classes.sectionTitle}>
        {t('curriculum.credits.page.modules', { modules: t('terms.module', { count: 2 }) })}
      </h2>
      <div
        className={classes.scroll}
        role="group"
        aria-labelledby="credits-modules"
        tabIndex={0}
      >
        <table className={classes.table}>
          <thead>
            <tr>
              <th scope="col">{t('terms.module', { count: 1 })}</th>
              <th scope="col" className={classes.num}>
                {t('curriculum.details.credits')}
              </th>
              <th scope="col" className={classes.num}>
                {t('curriculum.details.nqfLevel')}
              </th>
              <th scope="col" className={classes.num}>
                {t('curriculum.credits.page.planned')}
              </th>
              <th scope="col" className={classes.num}>
                {t('curriculum.credits.page.expected')}
              </th>
              <th scope="col">{t('curriculum.credits.page.check')}</th>
            </tr>
          </thead>
          <tbody>
            {check.modules.map((row) => (
              <tr key={row.module_id}>
                <th scope="row">
                  <Link
                    to={versionPath(versionId, `module:${row.module_id}`)}
                    className={classes.link}
                  >
                    <span className={classes.mono}>{row.code}</span> {row.name}
                  </Link>
                </th>
                <td className={classes.num}>
                  {row.credits !== null ? number(row.credits) : t('curriculum.details.notSet')}
                </td>
                <td className={classes.num}>{row.nqf_level ?? t('curriculum.details.notSet')}</td>
                <td className={classes.num}>{number(row.planned_hours)}</td>
                <td className={classes.num}>
                  {row.expected_hours !== null ? number(row.expected_hours) : '–'}
                </td>
                <td>
                  <HoursStatusLine hours={row} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Text size="sm" c="dimmed">
        {t('curriculum.credits.page.hoursNote')}
      </Text>
    </Paper>
  );
}

/** `/curriculum/versions/:versionId/credits`: credits and notional hours (advice only). */
export function CreditsPage() {
  const { t } = useTranslation();
  const { versionId = '' } = useParams();
  const programmes = useProgrammes();
  const found = programmes.data ? findVersion(programmes.data, versionId) : null;
  const check = useQuery({
    queryKey: queryKeys.creditCheck(versionId),
    queryFn: () => fetchCreditCheck(versionId),
    retry: false,
  });

  let content;
  if (programmes.isPending || check.isPending) {
    content = <LoadingState skeletons={3} />;
  } else if (programmes.isError || !found || isApiError(check.error, 404)) {
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
  } else if (check.isError || !check.data) {
    content = (
      <ErrorState
        title={t('curriculum.credits.page.loadTitle')}
        body={t('curriculum.credits.page.loadBody')}
        actions={<Button onClick={() => void check.refetch()}>{t('pages.retry')}</Button>}
      />
    );
  } else if (check.data.modules.length === 0) {
    content = (
      <EmptyState
        icon={IconSum}
        title={t('curriculum.credits.page.noModulesTitle')}
        body={t('curriculum.credits.page.noModules', {
          modules: t('terms.module', { count: 2 }).toLocaleLowerCase(),
        })}
      />
    );
  } else {
    content = (
      <>
        <Summary check={check.data} />
        <Years check={check.data} />
        <Levels check={check.data} />
        <Modules check={check.data} versionId={versionId} />
      </>
    );
  }

  return (
    <Page
      title={t('curriculum.credits.page.title')}
      description={
        found
          ? t('curriculum.credits.page.description', { programme: found.programme.name })
          : undefined
      }
    >
      <Box hiddenFrom="sm">
        <VersionSwitcher versionId={versionId} />
      </Box>
      {found && (
        <div>
          <Button
            component={Link}
            to={versionPath(versionId)}
            variant="default"
            leftSection={<IconArrowLeft size={18} aria-hidden />}
          >
            {t('curriculum.credits.page.back')}
          </Button>
        </div>
      )}
      {content}
    </Page>
  );
}
