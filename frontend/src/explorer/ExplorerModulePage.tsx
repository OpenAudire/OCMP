import { useEffect } from 'react';
import { Accordion, Badge, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconChevronLeft, IconFileOff } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import { fetchExplorerModule, queryKeys } from '../api/endpoints';
import type { ExplorerAssessment } from '../api/types';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import classes from './Explorer.module.css';
import { byWeek, minutesText } from './explorer';
import { SessionCard } from './SessionCard';

function Assessment({ assessment }: { assessment: ExplorerAssessment }) {
  const { t } = useTranslation();
  const facts = [
    assessment.method,
    assessment.weight !== null ? t('explorer.weight', { n: assessment.weight }) : null,
    assessment.timing || null,
    assessment.time_minutes > 0 ? t('explorer.timeMinutes', { count: assessment.time_minutes }) : null,
  ].filter(Boolean);
  return (
    <Paper withBorder component="article" className={classes.session}>
      <Title order={3} className={classes.sessionTitle}>
        {assessment.name}
      </Title>
      {facts.length > 0 && (
        <Text size="sm" c="dimmed">
          {facts.join(' · ')}
        </Text>
      )}
      <Text size="sm" fw={600} className={classes.listLabel}>
        {t('explorer.assessmentCovers')}
      </Text>
      {assessment.covered.length === 0 ? (
        <Text size="sm" c="dimmed">
          {t('explorer.assessmentNothing')}
        </Text>
      ) : (
        <ul className={classes.objectives}>
          {assessment.covered.map((o) => (
            <li key={o.id}>{o.text}</li>
          ))}
        </ul>
      )}
      {assessment.items.length > 0 && (
        <Accordion variant="contained" chevronPosition="right" className={classes.items}>
          <Accordion.Item value="items">
            <Accordion.Control>
              {t('explorer.itemsOf', { count: assessment.items.length })}
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="sm">
                {assessment.items.map((item) => (
                  <div key={item.id}>
                    <Text fw={600} size="sm">
                      {item.label}
                      {item.marks !== null ? ` · ${t('explorer.marks', { count: item.marks })}` : ''}
                    </Text>
                    {item.objectives.length > 0 && (
                      <ul className={classes.objectives}>
                        {item.objectives.map((o) => (
                          <li key={o.id}>{o.text}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      )}
    </Paper>
  );
}

export function ExplorerModulePage() {
  const { t } = useTranslation();
  const { moduleId = '' } = useParams();
  const [params] = useSearchParams();
  const highlight = params.get('session');
  const module = useQuery({
    queryKey: queryKeys.explorerModule(moduleId),
    queryFn: () => fetchExplorerModule(moduleId),
    retry: (count, error) => !(isApiError(error) && error.status === 404) && count < 1,
  });
  const data = module.data;

  // A session opened from a search hit scrolls into view.
  useEffect(() => {
    if (data && highlight) {
      document.getElementById(`session-${highlight}`)?.scrollIntoView?.({ block: 'center' });
    }
  }, [data, highlight]);

  if (module.isPending) {
    return (
      <Page title={t('explorer.title')}>
        <LoadingState title={t('explorer.loading')} />
      </Page>
    );
  }
  if (module.isError || !data) {
    const missing = isApiError(module.error) && module.error.status === 404;
    return (
      <Page title={t('explorer.title')}>
        {missing ? (
          <EmptyState
            icon={IconFileOff}
            title={t('explorer.moduleMissing.title')}
            body={t('explorer.moduleMissing.body')}
            actions={<Link to="/explorer">{t('explorer.backToExplorer')}</Link>}
          />
        ) : (
          <ErrorState title={t('explorer.error')} body={t('explorer.errorBody')} />
        )}
      </Page>
    );
  }

  const time = minutesText(t, data);
  return (
    <Page
      title={`${data.code} ${data.name}`}
      description={
        [
          data.credits !== null ? t('explorer.credits', { count: data.credits }) : null,
          data.nqf_level !== null ? t('explorer.nqf', { n: data.nqf_level }) : null,
          time || null,
        ]
          .filter(Boolean)
          .join(' · ') || undefined
      }
    >
      <Link to={`/explorer?view=browse&version=${data.version_id}`} className={classes.back}>
        <IconChevronLeft size={16} aria-hidden="true" /> {t('explorer.backToModules')}
      </Link>
      {data.description && <Text>{data.description}</Text>}
      {data.tags.length > 0 && (
        <Group gap="xs" aria-label={t('explorer.tags')}>
          {data.tags.map((tag) => (
            <Badge key={`${tag.list_name}-${tag.label}`} variant="light" color="gray">
              {tag.label}
            </Badge>
          ))}
        </Group>
      )}
      <section aria-labelledby="mod-outcomes">
        <Title order={2} id="mod-outcomes" className={classes.phaseTitle}>
          {t('explorer.moduleCovers')}
        </Title>
        {data.outcomes.length === 0 ? (
          <Text c="dimmed">{t('explorer.noOutcomes')}</Text>
        ) : (
          <ul className={classes.objectives}>
            {data.outcomes.map((o) => (
              <li key={o.id}>{o.text}</li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="mod-sessions">
        <Title order={2} id="mod-sessions" className={classes.phaseTitle}>
          {t('explorer.sessionsByWeek')}
        </Title>
        {data.sessions.length === 0 && <Text c="dimmed">{t('explorer.noSessions')}</Text>}
        <Stack gap="lg">
          {byWeek(data.sessions).map(([week, sessions]) => (
            <div key={week ?? 'none'}>
              <Title order={3} className={classes.weekHeading}>
                {week === null ? t('explorer.noWeek') : t('explorer.week', { n: week })}
              </Title>
              <Stack gap="sm">
                {sessions.map((s) => (
                  <SessionCard key={s.id} session={s} highlighted={s.id === highlight} />
                ))}
              </Stack>
            </div>
          ))}
        </Stack>
      </section>
      <section aria-labelledby="mod-assessments">
        <Title order={2} id="mod-assessments" className={classes.phaseTitle}>
          {t('explorer.assessments')}
        </Title>
        {data.assessments.length === 0 && <Text c="dimmed">{t('explorer.noAssessments')}</Text>}
        <Stack gap="sm">
          {data.assessments.map((a) => (
            <Assessment key={a.id} assessment={a} />
          ))}
        </Stack>
      </section>
    </Page>
  );
}
