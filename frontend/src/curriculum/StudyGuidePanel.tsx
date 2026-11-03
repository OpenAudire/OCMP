import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  FileInput,
  Group,
  NativeSelect,
  Paper,
  Progress,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { IconFileText } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import {
  acceptProposal,
  cancelStudyGuideRun,
  fetchProposals,
  fetchStudyGuideRuns,
  queryKeys,
  rejectProposal,
  uploadStudyGuide,
} from '../api/endpoints';
import type { ObjectiveDomain, ObjectiveProposal, StudyGuideRun } from '../api/types';
import { StudyGuideConfirmation } from '../ui/StudyGuideConfirmation';
import { studyGuideConfirmationPayload } from '../ui/studyGuidePayload';
import { DialogForm, EditDialog } from './EditDialog';
import { useRefreshCurriculum, type EditResult } from './editing';
import classes from './StudyGuidePanel.module.css';

const POLL_MS = 2000;
const ACTIVE = new Set(['queued', 'running']);
const DOMAINS: ObjectiveDomain[] = ['knowledge', 'skill', 'attitude'];

const isActive = (run: StudyGuideRun | undefined) => run !== undefined && ACTIVE.has(run.status);

function uploadError(t: ReturnType<typeof useTranslation>['t'], error: unknown): string {
  if (isApiError(error, 413)) return t('curriculum.studyGuide.errors.tooLarge');
  if (isApiError(error, 409))
    return t('curriculum.studyGuide.errors.refused', { reason: error.message });
  if (isApiError(error, 422)) {
    // A refusal from the service has a reason in words; a malformed form only has axios's text.
    const reason = error.message.startsWith('Request failed') ? '' : error.message;
    return t('curriculum.studyGuide.errors.unusable', { reason });
  }
  if (isApiError(error, 403)) return t('curriculum.studyGuide.errors.forbidden');
  if (isApiError(error, 429)) return t('curriculum.studyGuide.errors.tooMany');
  return t('curriculum.studyGuide.errors.generic');
}

function UploadForm({
  moduleId,
  onClose,
  onStarted,
}: {
  moduleId: string;
  onClose: () => void;
  onStarted: () => void;
}) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [missing, setMissing] = useState(false);
  const mutation = useMutation({
    mutationFn: () => uploadStudyGuide(moduleId, file as File, studyGuideConfirmationPayload(true)),
    onSuccess: onStarted,
  });
  return (
    <DialogForm
      submitLabel={t('curriculum.studyGuide.start')}
      error={mutation.isError ? uploadError(t, mutation.error) : null}
      busy={mutation.isPending}
      onSubmit={(event) => {
        event.preventDefault();
        if (!confirmed) {
          setMissing(true);
          return;
        }
        if (file) mutation.mutate();
      }}
      onClose={onClose}
    >
      <Text size="sm">{t('curriculum.studyGuide.uploadIntro')}</Text>
      <FileInput
        label={t('curriculum.studyGuide.file')}
        description={t('curriculum.studyGuide.fileHint')}
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        value={file}
        onChange={setFile}
        required
        clearable
        clearButtonProps={{ 'aria-label': t('curriculum.studyGuide.clearFile') }}
        data-autofocus
      />
      <StudyGuideConfirmation
        checked={confirmed}
        onChange={(value) => {
          setConfirmed(value);
          setMissing(false);
        }}
        error={missing ? t('curriculum.studyGuide.confirmFirst') : undefined}
      />
    </DialogForm>
  );
}

function RunStatus({
  run,
  onCancel,
  cancelling,
}: {
  run: StudyGuideRun;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const { t } = useTranslation();
  const percent = run.total_items > 0 ? Math.round((run.done_items / run.total_items) * 100) : 0;
  const label =
    run.status === 'queued'
      ? t('curriculum.studyGuide.state.queued')
      : run.status === 'running'
        ? t('curriculum.studyGuide.state.running')
        : t(`curriculum.studyGuide.state.${run.status}`);
  return (
    <Stack gap="xs" className={classes.run}>
      <Text fw={600} size="sm">
        {label}
      </Text>
      {isActive(run) && (
        <Progress
          value={percent}
          aria-label={t('curriculum.studyGuide.progress')}
          aria-valuetext={t('curriculum.studyGuide.parts', {
            done: run.done_items,
            total: run.total_items,
          })}
        />
      )}
      <Text size="sm">
        {t('curriculum.studyGuide.parts', { done: run.done_items, total: run.total_items })}{' '}
        {t('curriculum.studyGuide.proposed', { count: run.proposals_created })}
        {run.failed_items > 0 &&
          ` ${t('curriculum.studyGuide.failedParts', { count: run.failed_items })}`}
      </Text>
      {run.truncated && (
        <Text size="sm" c="dimmed">
          {t('curriculum.studyGuide.truncated')}
        </Text>
      )}
      {run.error_message && !isActive(run) && <Text size="sm">{run.error_message}</Text>}
      {isActive(run) && (
        <Group>
          <Button variant="default" onClick={onCancel} loading={cancelling}>
            {t('curriculum.studyGuide.cancel')}
          </Button>
        </Group>
      )}
    </Stack>
  );
}

function ProposalCard({
  proposal,
  versionId,
  moduleId,
  onSaved,
}: {
  proposal: ObjectiveProposal;
  versionId: string;
  moduleId: string;
  onSaved: (result: EditResult) => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const refresh = useRefreshCurriculum(versionId);
  const [text, setText] = useState(proposal.text);
  const [domain, setDomain] = useState<string>(proposal.domain ?? '');
  const done = async (message: string) => {
    await client.invalidateQueries({ queryKey: queryKeys.proposals(moduleId) });
    await client.invalidateQueries({ queryKey: queryKeys.studyGuideRuns(moduleId) });
    onSaved({ message, focus: true });
  };
  const accept = useMutation({
    mutationFn: () =>
      acceptProposal(proposal.id, {
        text: text.trim(),
        domain: (domain || null) as ObjectiveDomain | null,
        set_domain: true,
      }),
    onSuccess: async () => {
      await refresh();
      await done(t('curriculum.studyGuide.accepted'));
    },
  });
  const reject = useMutation({
    mutationFn: () => rejectProposal(proposal.id),
    onSuccess: () => done(t('curriculum.studyGuide.rejected')),
  });
  const failed = accept.isError ? accept.error : reject.isError ? reject.error : null;
  const busy = accept.isPending || reject.isPending;
  return (
    <li className={classes.proposal}>
      <Stack gap="xs">
        <Textarea
          label={t('curriculum.studyGuide.wording')}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
          rows={3}
          maxLength={2000}
        />
        <NativeSelect
          label={t('curriculum.objectives.domain')}
          value={domain}
          onChange={(event) => setDomain(event.currentTarget.value)}
          data={[
            { value: '', label: t('curriculum.domain.none') },
            ...DOMAINS.map((d) => ({ value: d, label: t(`curriculum.domain.${d}`) })),
          ]}
        />
        {proposal.source_quote && (
          <Text size="sm" c="dimmed">
            {t('curriculum.studyGuide.source', { quote: proposal.source_quote })}
          </Text>
        )}
        {failed !== null && (
          <Alert color="red" role="alert">
            {isApiError(failed, 409)
              ? t('curriculum.studyGuide.errors.decided')
              : t('curriculum.studyGuide.errors.generic')}
          </Alert>
        )}
        <Group gap="sm">
          <Button
            disabled={busy || text.trim() === ''}
            loading={accept.isPending}
            onClick={() => accept.mutate()}
          >
            {t('curriculum.studyGuide.accept')}
          </Button>
          <Button
            variant="default"
            disabled={busy}
            loading={reject.isPending}
            onClick={() => reject.mutate()}
          >
            {t('curriculum.studyGuide.reject')}
          </Button>
        </Group>
      </Stack>
    </li>
  );
}

/**
 * Read a study guide for a module: upload a PDF or Word file (with the confirmation that it holds
 * no real patient information), follow the AI's reading, and accept or reject each objective it
 * proposes. Nothing becomes an objective until a person accepts it.
 */
export function StudyGuidePanel({
  moduleId,
  versionId,
  onSaved,
}: {
  moduleId: string;
  versionId: string;
  onSaved: (result: EditResult) => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [dialog, setDialog] = useState(false);
  const runs = useQuery({
    queryKey: queryKeys.studyGuideRuns(moduleId),
    queryFn: () => fetchStudyGuideRuns(moduleId),
    refetchInterval: (query) => (isActive(query.state.data?.[0]) ? POLL_MS : false),
  });
  const proposals = useQuery({
    queryKey: queryKeys.proposals(moduleId),
    queryFn: () => fetchProposals(moduleId),
  });
  const latest = runs.data?.[0];
  const cancel = useMutation({
    mutationFn: (id: string) => cancelStudyGuideRun(id),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.studyGuideRuns(moduleId) }),
  });
  // New proposals appear while the reading goes on; read them again as each piece is done.
  const seen = useRef(latest?.proposals_created ?? 0);
  useEffect(() => {
    const now = latest?.proposals_created ?? 0;
    if (now !== seen.current) {
      seen.current = now;
      void client.invalidateQueries({ queryKey: queryKeys.proposals(moduleId) });
    }
  }, [latest?.proposals_created, client, moduleId]);

  const pending = proposals.data ?? [];
  return (
    <Paper
      component="section"
      aria-labelledby={`study-guide-${moduleId}`}
      className={classes.panel}
    >
      <Group justify="space-between" align="flex-start">
        <Title order={3} id={`study-guide-${moduleId}`} className={classes.title}>
          <IconFileText size={18} aria-hidden="true" className={classes.icon} />
          {t('curriculum.studyGuide.title')}
        </Title>
        <Button variant="default" disabled={isActive(latest)} onClick={() => setDialog(true)}>
          {t('curriculum.studyGuide.open')}
        </Button>
      </Group>
      <Text size="sm" c="dimmed">
        {t('curriculum.studyGuide.intro')}
      </Text>
      {runs.isError && (
        <Alert color="red" role="alert">
          {t('curriculum.studyGuide.errors.progress')}
        </Alert>
      )}
      {latest && (
        <RunStatus
          run={latest}
          cancelling={cancel.isPending}
          onCancel={() => cancel.mutate(latest.id)}
        />
      )}
      {pending.length > 0 && (
        <Stack gap="xs">
          <Text fw={600}>{t('curriculum.studyGuide.pending', { count: pending.length })}</Text>
          <ul className={classes.list} aria-label={t('curriculum.studyGuide.pendingList')}>
            {pending.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                proposal={proposal}
                versionId={versionId}
                moduleId={moduleId}
                onSaved={onSaved}
              />
            ))}
          </ul>
        </Stack>
      )}
      <EditDialog
        opened={dialog}
        onClose={() => setDialog(false)}
        title={t('curriculum.studyGuide.dialogTitle')}
      >
        <UploadForm
          moduleId={moduleId}
          onClose={() => setDialog(false)}
          onStarted={async () => {
            setDialog(false);
            await client.invalidateQueries({ queryKey: queryKeys.studyGuideRuns(moduleId) });
          }}
        />
      </EditDialog>
    </Paper>
  );
}
