import { useMemo } from 'react';
import { Box, Button, NativeSelect, Paper, Text } from '@mantine/core';
import { IconArrowLeft, IconChecklist, IconPencil } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import { fetchVersionChecks, queryKeys } from '../api/endpoints';
import type { CheckedObjective, FindingSeverity } from '../api/types';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { findVersion, useProgrammes } from './currentVersion';
import { CURRICULUM_PATH, versionPath } from './paths';
import { FindingItem } from './QualityPanel';
import { VersionSwitcher } from './VersionSwitcher';
import classes from './QualityPage.module.css';

const RULES = [
  'vague_verb',
  'multiple_verbs',
  'too_long',
  'missing_domain',
  'missing_upward_link',
  'no_action_verb',
  'too_short',
  'learner_framing',
  'ambiguous_qualifier',
  'level_differs',
  'near_duplicate',
  'possible_personal_information',
] as const;

type SeverityFilter = 'all' | FindingSeverity;
type RuleFilter = 'all' | (typeof RULES)[number];

/** The builder item that holds the objective (its Edit button is in the details panel). */
function itemOf(row: CheckedObjective): string | undefined {
  if (row.level === 'learning_event' && row.event_id) return `event:${row.event_id}`;
  if (row.level === 'module' && row.module_id) return `module:${row.module_id}`;
  return undefined;
}

function whereOf(t: TFunction, row: CheckedObjective): string {
  const programme = t('terms.programme', { count: 1 });
  if (row.level === 'programme') return t('curriculum.quality.page.programmeOutcome', { programme });
  const module = row.module_code ?? '';
  if (row.level === 'module') return t('curriculum.quality.page.moduleOutcome', { module });
  return t('curriculum.quality.page.sessionObjective', { module, session: row.event_title ?? '' });
}

function Row({ row, versionId }: { row: CheckedObjective; versionId: string }) {
  const { t } = useTranslation();
  const levels = row.suggestions.map((s) => `${s.level_name} (${s.scale_name})`).join(', ');
  return (
    <li className={classes.row}>
      <Text size="sm" c="dimmed">
        {whereOf(t, row)}
      </Text>
      <Text className={classes.objective}>{row.text}</Text>
      {row.findings.length === 0 ? (
        <Text size="sm">{t('curriculum.quality.page.noFindings')}</Text>
      ) : (
        <ul className={classes.findings}>
          {row.findings.map((finding) => (
            <FindingItem key={finding.code} finding={finding} />
          ))}
        </ul>
      )}
      {levels && (
        <Text size="sm">{t('curriculum.quality.page.levelSuggested', { levels })}</Text>
      )}
      <div>
        <Button
          component={Link}
          to={versionPath(versionId, itemOf(row))}
          variant="default"
          leftSection={<IconPencil size={18} aria-hidden />}
          aria-label={t('curriculum.quality.page.openItem', { text: row.text })}
        >
          {t('curriculum.quality.page.open_item')}
        </Button>
      </div>
    </li>
  );
}

/** `/curriculum/versions/:versionId/quality`: findings for every visible objective. */
export function QualityPage() {
  const { t } = useTranslation();
  const { versionId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const programmes = useProgrammes();
  const found = programmes.data ? findVersion(programmes.data, versionId) : null;
  const checks = useQuery({
    queryKey: queryKeys.versionChecks(versionId),
    queryFn: () => fetchVersionChecks(versionId),
    retry: false,
  });
  const severity = (searchParams.get('severity') ?? 'all') as SeverityFilter;
  const rule = (searchParams.get('rule') ?? 'all') as RuleFilter;
  const onlyFindings = searchParams.get('findings') === '1';

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === 'all' || value === '') next.delete(key);
    else next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  const rows = useMemo(() => {
    const all = checks.data?.objectives ?? [];
    return all.filter((row) => {
      const matching = row.findings.filter(
        (f) => (severity === 'all' || f.severity === severity) && (rule === 'all' || f.code === rule)
      );
      const filtering = severity !== 'all' || rule !== 'all' || onlyFindings;
      return filtering ? matching.length > 0 : true;
    });
  }, [checks.data, severity, rule, onlyFindings]);

  let content;
  if (programmes.isPending || checks.isPending) {
    content = <LoadingState skeletons={3} />;
  } else if (programmes.isError || !found || isApiError(checks.error, 404)) {
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
  } else if (isApiError(checks.error, 403)) {
    content = (
      <ErrorState
        title={t('curriculum.quality.page.forbiddenTitle')}
        body={t('curriculum.quality.page.forbiddenBody')}
      />
    );
  } else if (checks.isError || !checks.data) {
    content = (
      <ErrorState
        title={t('curriculum.quality.page.loadTitle')}
        body={t('curriculum.quality.page.loadBody')}
        actions={<Button onClick={() => void checks.refetch()}>{t('pages.retry')}</Button>}
      />
    );
  } else if (checks.data.objectives.length === 0) {
    content = (
      <EmptyState
        icon={IconChecklist}
        title={t('curriculum.quality.page.noObjectivesTitle')}
        body={t('curriculum.quality.page.noObjectives')}
      />
    );
  } else {
    const data = checks.data;
    content = (
      <Paper withBorder component="section" aria-labelledby="quality-list" className={classes.card}>
        <h2 id="quality-list" className={classes.sectionTitle}>
          {t('curriculum.quality.page.list')}
        </h2>
        <div className={classes.filters}>
          <NativeSelect
            label={t('curriculum.quality.page.severity')}
            value={severity}
            data={[
              { value: 'all', label: t('curriculum.quality.page.all') },
              { value: 'warning', label: t('curriculum.quality.page.onlyWarnings') },
              { value: 'info', label: t('curriculum.quality.page.onlyInfo') },
            ]}
            onChange={(event) => setFilter('severity', event.currentTarget.value)}
          />
          <NativeSelect
            label={t('curriculum.quality.page.rule')}
            value={rule}
            data={[
              { value: 'all', label: t('curriculum.quality.page.allRules') },
              ...RULES.map((code) => ({ value: code, label: t(`curriculum.quality.${code}.name`) })),
            ]}
            onChange={(event) => setFilter('rule', event.currentTarget.value)}
          />
          <NativeSelect
            label={t('curriculum.quality.page.findingsOnly')}
            value={onlyFindings ? '1' : 'all'}
            data={[
              { value: 'all', label: t('curriculum.quality.page.all') },
              { value: '1', label: t('curriculum.quality.page.withFindings') },
            ]}
            onChange={(event) => setFilter('findings', event.currentTarget.value)}
          />
        </div>
        {!data.near_duplicates_checked && (
          <Text size="sm" c="dimmed">
            {t('curriculum.quality.page.nearDuplicatesOff')}
          </Text>
        )}
        <Text size="sm" role="status">
          {t('curriculum.quality.page.showing', {
            shown: rows.length,
            total: data.objectives.length,
          })}
        </Text>
        {rows.length === 0 ? (
          <EmptyState
            icon={IconChecklist}
            title={t('curriculum.quality.page.nothingMatchesTitle')}
            body={t('curriculum.quality.page.nothingMatches')}
          />
        ) : (
          <ul className={classes.list}>
            {rows.map((row) => (
              <Row key={row.objective_id} row={row} versionId={versionId} />
            ))}
          </ul>
        )}
        <Text size="sm" c="dimmed">
          {t('curriculum.quality.page.rulesLine', {
            language: data.rules_language,
            version: data.rules_version,
          })}
        </Text>
      </Paper>
    );
  }

  return (
    <Page
      title={t('curriculum.quality.page.title')}
      description={
        found
          ? t('curriculum.quality.page.description', { programme: found.programme.name })
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
            {t('curriculum.quality.page.back')}
          </Button>
        </div>
      )}
      {content}
    </Page>
  );
}
