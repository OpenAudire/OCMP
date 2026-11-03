import { useEffect, useRef, useState } from 'react';
import { Button, Group, NativeSelect, Paper, Progress, Stack, Text } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import {
  cancelAiMappingRun,
  fetchAiMappingRuns,
  fetchFrameworkLibrary,
  queryKeys,
  startAiMapping,
} from '../api/endpoints';
import type { AiMappingRun, MappingWorkspace } from '../api/types';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';
import { editErrorMessage } from '../curriculum/editing';
import classes from './Mapping.module.css';

const POLL_MS = 2000;
const ACTIVE = new Set(['queued', 'running']);

function isActive(run: AiMappingRun | undefined): boolean {
  return run !== undefined && ACTIVE.has(run.status);
}

/** The modules that have objectives in this workspace, by code. */
function modulesOf(workspace: MappingWorkspace): { id: string; label: string }[] {
  const found = new Map<string, string>();
  for (const objective of workspace.objectives) {
    if (objective.module_id && !found.has(objective.module_id)) {
      found.set(
        objective.module_id,
        [objective.module_code, objective.module_name].filter(Boolean).join(' ')
      );
    }
  }
  return [...found].map(([id, label]) => ({ id, label })).sort((a, b) => a.label.localeCompare(b.label));
}

function StartForm({
  workspace,
  versionId,
  onClose,
  onStarted,
}: {
  workspace: MappingWorkspace;
  versionId: string;
  onClose: () => void;
  onStarted: () => void;
}) {
  const { t } = useTranslation();
  const library = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });
  const frameworks = (library.data?.frameworks ?? []).filter((f) => f.status === 'active');
  const [frameworkId, setFrameworkId] = useState('');
  const [moduleId, setModuleId] = useState('');
  const modules = modulesOf(workspace);
  const chosen = frameworkId || frameworks[0]?.id || '';
  const mutation = useMutation({
    mutationFn: () =>
      startAiMapping(versionId, { framework_id: chosen, module_id: moduleId || null }),
    onSuccess: onStarted,
  });
  return (
    <DialogForm
      submitLabel={t('mapping.ai.submit')}
      busy={mutation.isPending}
      error={
        mutation.isError
          ? editErrorMessage(t, mutation.error, t('mapping.ai.errors.conflict'))
          : null
      }
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen) mutation.mutate();
      }}
      onClose={onClose}
    >
      <Stack gap="md">
        {library.data && frameworks.length === 0 ? (
          <Text>{t('mapping.ai.noFramework')}</Text>
        ) : (
          <>
            <NativeSelect
              label={t('mapping.ai.framework')}
              value={chosen}
              onChange={(event) => setFrameworkId(event.currentTarget.value)}
              data={frameworks.map((f) => ({
                value: f.id,
                label: t('mapping.framework.option', { name: f.name, version: f.version_label }),
              }))}
            />
            <NativeSelect
              label={t('mapping.ai.scope')}
              description={t('mapping.ai.scopeHelp')}
              value={moduleId}
              onChange={(event) => setModuleId(event.currentTarget.value)}
              data={[
                { value: '', label: t('mapping.ai.scopeAll') },
                ...modules.map((m) => ({
                  value: m.id,
                  label: t('mapping.ai.scopeModule', { module: m.label }),
                })),
              ]}
            />
          </>
        )}
      </Stack>
    </DialogForm>
  );
}

/** What the run is doing or how it ended, in words (never colour alone). */
function RunState({ run }: { run: AiMappingRun }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => cancelAiMappingRun(run.id),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: queryKeys.aiMappingRuns(run.version_id) }),
  });
  const percent = run.total_items > 0 ? Math.round((run.done_items / run.total_items) * 100) : 0;
  const reason =
    run.status === 'budget_exceeded' || run.status === 'cancelled'
      ? t(`mapping.ai.run.reason.${run.status}`)
      : run.error_message;
  return (
    <Stack gap="xs">
      <Text fw={600} component="h3" size="md">
        {t('mapping.ai.run.heading')}
      </Text>
      <Text role="status">{t(`mapping.ai.run.status.${run.status}`)}</Text>
      <Progress
        value={percent}
        aria-label={t('mapping.ai.run.progressLabel')}
        animated={isActive(run)}
      />
      <Text size="sm">
        {t('mapping.ai.run.progress', { done: run.done_items, total: run.total_items })}
        {' · '}
        {t('mapping.ai.run.suggestions', { count: run.links_created })}
        {run.failed_items > 0 && (
          <>
            {' · '}
            {t('mapping.ai.run.failed', { count: run.failed_items })}
          </>
        )}
      </Text>
      {reason && run.status !== 'succeeded' && <Text size="sm">{reason}</Text>}
      {run.status === 'succeeded' && run.error_message && (
        <Text size="sm">{run.error_message}</Text>
      )}
      <Group gap="sm">
        {isActive(run) && (
          <Button variant="default" loading={cancel.isPending} onClick={() => cancel.mutate()}>
            {t('mapping.ai.run.cancel')}
          </Button>
        )}
        {!isActive(run) && run.links_created > 0 && (
          <Button component={Link} to="/mapping/review" variant="default">
            {t('mapping.ai.run.reviewLink')}
          </Button>
        )}
      </Group>
    </Stack>
  );
}

/**
 * Starts an AI mapping run for the open version and follows the latest one. Shown only to
 * people who may run it (the API checks as well). Results are suggestions in the review queue.
 */
export function AiMappingPanel({
  workspace,
  versionId,
}: {
  workspace: MappingWorkspace;
  versionId: string;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [opened, setOpened] = useState(false);
  const runs = useQuery({
    queryKey: queryKeys.aiMappingRuns(versionId),
    queryFn: () => fetchAiMappingRuns(versionId),
    retry: false,
    refetchInterval: (query) => (isActive(query.state.data?.[0]) ? POLL_MS : false),
  });
  const latest = runs.data?.[0];

  // When a run ends, the workspace and the review count have new suggestions to show.
  const wasActive = useRef(false);
  useEffect(() => {
    const active = isActive(latest);
    if (wasActive.current && !active) {
      void client.invalidateQueries({ queryKey: queryKeys.mappingWorkspace(versionId) });
      void client.invalidateQueries({ queryKey: queryKeys.reviewCount });
    }
    wasActive.current = active;
  }, [latest, client, versionId]);

  return (
    <Paper withBorder component="section" aria-labelledby="ai-mapping-title" className={classes.pane}>
      <Group justify="space-between" align="flex-start" gap="md">
        <Stack gap={4} style={{ flex: '1 1 320px' }}>
          <h2 id="ai-mapping-title" className={classes.paneHeading}>
            {t('mapping.ai.title')}
          </h2>
          <Text size="sm">{t('mapping.ai.intro')}</Text>
        </Stack>
        <Button
          leftSection={<IconSparkles size={18} aria-hidden />}
          disabled={isActive(latest)}
          onClick={() => setOpened(true)}
        >
          {t('mapping.ai.start')}
        </Button>
      </Group>
      {runs.isError && <Text size="sm">{t('mapping.ai.run.loadFailed')}</Text>}
      {latest && <RunState run={latest} />}
      <EditDialog opened={opened} title={t('mapping.ai.dialogTitle')} onClose={() => setOpened(false)}>
        <StartForm
          workspace={workspace}
          versionId={versionId}
          onClose={() => setOpened(false)}
          onStarted={() => {
            setOpened(false);
            void client.invalidateQueries({ queryKey: queryKeys.aiMappingRuns(versionId) });
          }}
        />
      </EditDialog>
    </Paper>
  );
}
