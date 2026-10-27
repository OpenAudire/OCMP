import { useState, type FormEvent } from 'react';
import { Radio, Text, Textarea } from '@mantine/core';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { addMappingLink, updateMappingLink } from '../api/endpoints';
import type { DepthMatch, WorkspaceLink } from '../api/types';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';
import { editErrorMessage } from '../curriculum/editing';
import { MappingHelp } from './MappingHelp';
import { COVERAGE_LEVELS, DEPTH_CHOICES } from './scale';
import classes from './Mapping.module.css';

const REASON_MAX = 1000;

interface LinkDialogProps {
  opened: boolean;
  objectiveId: string;
  objectiveText: string;
  /** The item to link. */
  item: { id: string; code: string; title: string };
  /** The link being changed; without it a new link is made. */
  link?: WorkspaceLink;
  /** What saving does to the link's status, said before saving. */
  statusNote: string;
  onClose: () => void;
  onSaved: (link: WorkspaceLink, wasNew: boolean) => void;
}

function LinkForm({
  objectiveId,
  objectiveText,
  item,
  link,
  statusNote,
  onClose,
  onSaved,
}: Omit<LinkDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const [coverage, setCoverage] = useState<string>(
    link?.coverage === null || link?.coverage === undefined ? '' : String(link.coverage)
  );
  const [depth, setDepth] = useState<string>(link?.depth_match ?? '');
  const [reason, setReason] = useState(link?.rationale ?? '');
  const [problem, setProblem] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      const input = {
        coverage: Number(coverage),
        depth_match: depth as DepthMatch,
        rationale: reason.trim(),
      };
      return link ? updateMappingLink(link.id, input) : addMappingLink(objectiveId, item.id, input);
    },
    onSuccess: (saved) => onSaved(saved, !link),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (coverage === '') return setProblem(t('mapping.dialog.chooseCoverage'));
    if (depth === '') return setProblem(t('mapping.dialog.chooseDepth'));
    if (reason.length > REASON_MAX) return setProblem(t('mapping.dialog.reasonTooLong'));
    setProblem(null);
    mutation.mutate();
  };

  const error =
    problem ??
    (mutation.isError ? editErrorMessage(t, mutation.error, t('mapping.errors.conflict')) : null);

  return (
    <DialogForm
      submitLabel={link ? t('mapping.dialog.save') : t('mapping.dialog.add')}
      error={error}
      busy={mutation.isPending}
      onSubmit={submit}
      onClose={onClose}
    >
      <div>
        <Text size="sm" c="dimmed">
          {t('mapping.dialog.objective')}
        </Text>
        <Text>{objectiveText}</Text>
      </div>
      <div>
        <Text size="sm" c="dimmed">
          {t('mapping.dialog.item')}
        </Text>
        <Text>
          <span className={classes.code}>{item.code}</span> {item.title}
        </Text>
      </div>
      <MappingHelp />
      <Radio.Group
        label={t('mapping.dialog.coverageLegend')}
        description={t('mapping.dialog.coverageHint')}
        value={coverage}
        onChange={setCoverage}
        withAsterisk
      >
        <div className={classes.choices}>
          {COVERAGE_LEVELS.map((level) => (
            <div key={level} className={classes.choice} data-checked={coverage === String(level)}>
              <Radio
                value={String(level)}
                label={t('mapping.coverage.choice', {
                  value: level,
                  label: t(`mapping.coverage.levels.${level}`),
                })}
              />
            </div>
          ))}
        </div>
      </Radio.Group>
      <Radio.Group
        label={t('mapping.dialog.depthLegend')}
        description={t('mapping.dialog.depthHint')}
        value={depth}
        onChange={setDepth}
        withAsterisk
      >
        <div className={classes.choices}>
          {DEPTH_CHOICES.map((choice) => (
            <div key={choice} className={classes.choice} data-checked={depth === choice}>
              <Radio value={choice} label={t(`mapping.depth.names.${choice}`)} />
            </div>
          ))}
        </div>
        {depth !== '' && (
          <Text size="sm" c="dimmed" mt={8}>
            {t(`mapping.depth.definitions.${depth as DepthMatch}`)}
          </Text>
        )}
      </Radio.Group>
      <Textarea
        label={t('mapping.dialog.reason')}
        description={t('mapping.dialog.reasonHint')}
        value={reason}
        onChange={(event) => setReason(event.currentTarget.value)}
        rows={3}
      />
      <Text size="sm">{statusNote}</Text>
    </DialogForm>
  );
}

/** Links an objective to a framework item, or changes the link: coverage, depth, reason. */
export function LinkDialog({ opened, link, ...rest }: LinkDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      title={link ? t('mapping.dialog.editTitle') : t('mapping.dialog.addTitle')}
      onClose={rest.onClose}
    >
      <LinkForm link={link} {...rest} />
    </EditDialog>
  );
}
