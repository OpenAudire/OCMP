import { useEffect } from 'react';
import { Alert, Badge, Button, Group, NativeSelect, Paper, SegmentedControl, Stack, Text, Title } from '@mantine/core';
import { IconCalendarOff, IconChevronLeft, IconChevronRight, IconSearch } from '@tabler/icons-react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';

import { fetchExplorerCompetencies, fetchExplorerWeek, fetchVersionStructure, queryKeys } from '../api/endpoints';
import type { StructureModule } from '../api/types';
import { defaultVersionId, rememberedVersion, useProgrammes } from '../curriculum/currentVersion';
import { useInstitution } from '../institution/useInstitution';
import { versionLabel } from '../curriculum/versions';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import classes from './Explorer.module.css';
import { rememberedWeek, rememberWeek } from './explorer';
import { SessionCard } from './SessionCard';

type View = 'week' | 'browse' | 'built';

function WeekView({ versionId }: { versionId: string }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const asked = Number(params.get('week'));
  const week = Number.isInteger(asked) && asked > 0 ? asked : (rememberedWeek() ?? 1);
  const data = useQuery({
    queryKey: queryKeys.explorerWeek(versionId, week),
    queryFn: () => fetchExplorerWeek(versionId, week),
    placeholderData: keepPreviousData,
  });
  const weeks = data.data?.weeks ?? [];
  // While the next week loads the last one stays on screen for the stepper, but not its sessions.
  const current = data.data && data.data.week === week ? data.data : undefined;

  const go = (next: number) => {
    rememberWeek(next);
    const copy = new URLSearchParams(params);
    copy.set('week', String(next));
    setParams(copy, { replace: true });
  };

  // With no week asked for or remembered, open the first week that has sessions.
  useEffect(() => {
    if (!params.get('week') && rememberedWeek() === null && weeks.length > 0 && !weeks.includes(week)) {
      go(weeks[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weeks.join(',')]);

  const previous = [...weeks].reverse().find((w) => w < week);
  const next = weeks.find((w) => w > week);

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="nowrap" className={classes.stepper}>
        <Button
          variant="default"
          leftSection={<IconChevronLeft size={18} aria-hidden="true" />}
          disabled={previous === undefined}
          onClick={() => previous !== undefined && go(previous)}
        >
          {t('explorer.previousWeek')}
        </Button>
        <Title order={2} className={classes.weekTitle} aria-live="polite">
          {t('explorer.week', { n: week })}
        </Title>
        <Button
          variant="default"
          rightSection={<IconChevronRight size={18} aria-hidden="true" />}
          disabled={next === undefined}
          onClick={() => next !== undefined && go(next)}
        >
          {t('explorer.nextWeek')}
        </Button>
      </Group>
      {!current && !data.isError && <LoadingState title={t('explorer.loading')} skeletons={2} />}
      {data.isError && (
        <ErrorState title={t('explorer.error')} body={t('explorer.errorBody')} />
      )}
      {current && current.sessions.length === 0 && (
        <EmptyState
          icon={IconCalendarOff}
          title={t('explorer.emptyWeek.title', { n: week })}
          body={
            weeks.length > 0
              ? t('explorer.emptyWeek.withWeeks', { weeks: weeks.join(', ') })
              : t('explorer.emptyWeek.noWeeks')
          }
        />
      )}
      {current?.sessions.map((session) => (
        <SessionCard key={session.id} session={session} showModule />
      ))}
    </Stack>
  );
}

function ModuleCard({ module }: { module: StructureModule }) {
  const { t } = useTranslation();
  return (
    <Paper withBorder className={classes.moduleCard} component="li">
      <Link to={`/explorer/modules/${module.id}`} className={classes.moduleLink}>
        <span className={classes.code}>{module.code}</span>{' '}
        <span className={classes.moduleName}>{module.name}</span>
      </Link>
      <Group gap="xs">
        {module.credits && (
          <Badge variant="light" color="gray">
            {t('explorer.credits', { count: Number(module.credits) })}
          </Badge>
        )}
        <Text size="sm" c="dimmed">
          {t('explorer.sessionCount', { count: module.events.length })}
        </Text>
      </Group>
    </Paper>
  );
}

function BrowseView({ versionId }: { versionId: string }) {
  const { t } = useTranslation();
  const structure = useQuery({
    queryKey: queryKeys.versionStructure(versionId),
    queryFn: () => fetchVersionStructure(versionId),
  });
  if (structure.isPending) return <LoadingState title={t('explorer.loading')} skeletons={2} />;
  if (structure.isError) {
    return <ErrorState title={t('explorer.error')} body={t('explorer.errorBody')} />;
  }
  const { phases, modules_without_phase: loose, partial } = structure.data;
  const shown = [
    ...phases.map((p) => ({ key: p.id, name: p.name, modules: p.modules })),
    ...(loose.length ? [{ key: 'none', name: t('explorer.longitudinal'), modules: loose }] : []),
  ].filter((group) => group.modules.some((m) => !m.context_only));
  return (
    <Stack gap="lg">
      {partial && (
        <Alert color="ochre" variant="light">
          {t('explorer.partial')}
        </Alert>
      )}
      {shown.length === 0 && (
        <EmptyState
          icon={IconCalendarOff}
          title={t('explorer.noModules.title')}
          body={t('explorer.noModules.body')}
        />
      )}
      {shown.map((group) => (
        <section key={group.key} aria-labelledby={`phase-${group.key}`}>
          <Title order={2} id={`phase-${group.key}`} className={classes.phaseTitle}>
            {group.name}
          </Title>
          <ul className={classes.moduleList}>
            {group.modules
              .filter((m) => !m.context_only)
              .map((m) => (
                <ModuleCard key={m.id} module={m} />
              ))}
          </ul>
        </section>
      ))}
    </Stack>
  );
}

/** Where this year builds each competency group (only when the institution switches it on). No
 * scores, no individual framework items: the modules and sessions that carry each group. */
function BuiltView({ versionId }: { versionId: string }) {
  const { t } = useTranslation();
  const data = useQuery({
    queryKey: queryKeys.explorerCompetencies(versionId),
    queryFn: () => fetchExplorerCompetencies(versionId),
  });
  if (data.isPending) return <LoadingState title={t('explorer.loading')} skeletons={2} />;
  if (data.isError) return <ErrorState title={t('explorer.error')} body={t('explorer.errorBody')} />;
  if (data.data.frameworks.length === 0) {
    return (
      <EmptyState
        icon={IconCalendarOff}
        title={t('explorer.builtEmpty.title')}
        body={t('explorer.builtEmpty.body')}
      />
    );
  }
  return (
    <Stack gap="lg">
      <Text size="sm">{t('explorer.builtIntro')}</Text>
      {data.data.frameworks.map((framework) => (
        <Stack key={`${framework.name}-${framework.version_label}`} gap="md">
          <Text fw={600}>
            {t('explorer.builtFramework', { name: framework.name, version: framework.version_label })}
          </Text>
          {framework.groups.map((group) => (
            <section key={group.id} aria-labelledby={`group-${group.id}`}>
              <Title order={2} id={`group-${group.id}`} className={classes.phaseTitle}>
                <span className={classes.code}>{group.code}</span> {group.title}
              </Title>
              {group.modules.length === 0 ? (
                <Text size="sm" c="dimmed">
                  {t('explorer.builtNone')}
                </Text>
              ) : (
                <ul className={classes.moduleList}>
                  {group.modules.map((module) => (
                    <Paper withBorder className={classes.moduleCard} component="li" key={module.id}>
                      <Link to={`/explorer/modules/${module.id}`} className={classes.moduleLink}>
                        <span className={classes.code}>{module.code}</span>{' '}
                        <span className={classes.moduleName}>{module.name}</span>
                      </Link>
                      {module.sessions.length === 0 ? (
                        <Text size="sm" c="dimmed">
                          {t('explorer.builtModuleOnly')}
                        </Text>
                      ) : (
                        <ul className={classes.moduleList} aria-label={t('explorer.builtSessions')}>
                          {module.sessions.map((session) => (
                            <li key={session.id}>
                              <Link to={`/explorer/modules/${module.id}?session=${session.id}`} className={classes.builtSession}>
                                {session.week !== null
                                  ? `${t('explorer.week', { n: session.week })}: ${session.title}`
                                  : session.title}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </Paper>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </Stack>
      ))}
    </Stack>
  );
}

export function ExplorerHome() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const programmes = useProgrammes();
  const published = (programmes.data ?? [])
    .map((p) => ({ ...p, versions: p.versions.filter((v) => v.status === 'published') }))
    .filter((p) => p.versions.length > 0);
  const versionId =
    params.get('version') && published.some((p) => p.versions.some((v) => v.id === params.get('version')))
      ? (params.get('version') as string)
      : defaultVersionId(published, rememberedVersion());
  const showBuilt = Boolean(useInstitution()?.explorer?.show_competency_view);
  const asked = params.get('view');
  const view: View = asked === 'browse' ? 'browse' : asked === 'built' && showBuilt ? 'built' : 'week';

  const set = (changes: Record<string, string>) => {
    const copy = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) copy.set(key, value);
      else copy.delete(key);
    }
    setParams(copy, { replace: true });
  };

  if (programmes.isPending) {
    return (
      <Page title={t('explorer.title')}>
        <LoadingState title={t('explorer.loading')} />
      </Page>
    );
  }
  if (programmes.isError) {
    return (
      <Page title={t('explorer.title')}>
        <ErrorState title={t('explorer.error')} body={t('explorer.errorBody')} />
      </Page>
    );
  }
  if (!versionId) {
    return (
      <Page title={t('explorer.title')}>
        <EmptyState
          icon={IconCalendarOff}
          title={t('explorer.none.title')}
          body={t('explorer.none.body')}
        />
      </Page>
    );
  }

  const options = published.flatMap((p) =>
    p.versions.map((v) => ({ value: v.id, label: `${p.name} · ${versionLabel(t, v)}` }))
  );
  return (
    <Page title={t('explorer.title')} description={t('explorer.description')}>
      <div className={classes.controls}>
        {options.length > 1 && (
          <NativeSelect
            label={t('explorer.version')}
            value={versionId}
            onChange={(event) => set({ version: event.currentTarget.value, week: '' })}
            data={options}
          />
        )}
        <Button
          component={Link}
          to={`/search?version=${versionId}`}
          variant="default"
          leftSection={<IconSearch size={18} aria-hidden="true" />}
          className={classes.searchButton}
        >
          {t('explorer.search')}
        </Button>
      </div>
      <SegmentedControl
        fullWidth
        size="md"
        aria-label={t('explorer.viewLabel')}
        value={view}
        onChange={(value) => set({ view: value === 'browse' || value === 'built' ? value : '' })}
        data={[
          { value: 'week', label: t('explorer.thisWeek') },
          { value: 'browse', label: t('explorer.modules') },
          ...(showBuilt ? [{ value: 'built', label: t('explorer.built') }] : []),
        ]}
      />
      {view === 'week' && <WeekView versionId={versionId} />}
      {view === 'browse' && <BrowseView versionId={versionId} />}
      {view === 'built' && <BuiltView versionId={versionId} />}
    </Page>
  );
}
