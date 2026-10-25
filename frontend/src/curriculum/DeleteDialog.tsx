import type { FormEvent } from 'react';
import { Text } from '@mantine/core';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { deleteLearningEvent, deleteModule, deletePhase } from '../api/endpoints';
import type { StructureEvent, StructureModule, StructurePhase } from '../api/types';
import { DialogForm, EditDialog } from './EditDialog';
import {
  editErrorMessage,
  moduleAncestors,
  moduleParentId,
  nounsFor,
  useRefreshCurriculum,
  type EditResult,
} from './editing';
import { ROOT_ID } from './treeModel';

export type DeleteTarget =
  | { kind: 'phase'; phase: StructurePhase }
  | { kind: 'module'; module: StructureModule; phase: StructurePhase | null }
  | {
      kind: 'event';
      event: StructureEvent;
      module: StructureModule;
      phase: StructurePhase | null;
    };

interface DeleteDialogProps {
  opened: boolean;
  versionId: string;
  target: DeleteTarget;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

function nameOf(target: DeleteTarget): string {
  switch (target.kind) {
    case 'phase':
      return target.phase.name;
    case 'module':
      return `${target.module.code} ${target.module.name}`;
    case 'event':
      return target.event.title;
  }
}

function remove(target: DeleteTarget): Promise<void> {
  switch (target.kind) {
    case 'phase':
      return deletePhase(target.phase.id);
    case 'module':
      return deleteModule(target.module.id);
    case 'event':
      return deleteLearningEvent(target.event.id);
  }
}

/** Where the selection goes once the item is gone: its parent. */
function afterDelete(target: DeleteTarget): Pick<EditResult, 'select' | 'reveal'> {
  switch (target.kind) {
    case 'phase':
      return { select: ROOT_ID, reveal: [] };
    case 'module':
      return { select: moduleParentId(target.phase?.id ?? null), reveal: [ROOT_ID] };
    case 'event':
      return {
        select: `module:${target.module.id}`,
        reveal: moduleAncestors(target.phase?.id ?? null),
      };
  }
}

function DeleteForm({ versionId, target, onClose, onSaved }: Omit<DeleteDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const refresh = useRefreshCurriculum(versionId);
  const name = nameOf(target);
  const counted = (term: string, count: number) => `${count} ${nouns.noun(term, count)}`;
  const run = useMutation({
    mutationFn: () => remove(target),
    onSuccess: async () => {
      await refresh();
      onSaved({ message: t('curriculum.edit.deleted', { name }), ...afterDelete(target) });
    },
  });
  const error = run.isError ? editErrorMessage(t, run.error) : null;
  const submit = {
    submitLabel: t('curriculum.edit.delete', { noun: nouns.noun(termOf(target)) }),
    error,
    busy: run.isPending,
    danger: true,
    onSubmit: (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      run.mutate();
    },
    onClose,
  };

  if (target.kind === 'phase') {
    const count = target.phase.modules.length;
    if (count > 0) {
      return (
        <DialogForm submitLabel="" error={null} busy={false} onClose={onClose}>
          <Text>
            {t('curriculum.edit.phaseNotEmpty', {
              phase: nouns.phase,
              modules: counted('module', count),
            })}
          </Text>
        </DialogForm>
      );
    }
    return (
      <DialogForm {...submit}>
        <Text>{t('curriculum.edit.deletePhase', { phase: nouns.phase })}</Text>
        <Text size="sm" c="dimmed">
          {t('curriculum.edit.deleteNote')}
        </Text>
      </DialogForm>
    );
  }

  let consequence: string;
  if (target.kind === 'module') {
    const sessions = target.module.events.length;
    const objectives =
      target.module.objective_count +
      target.module.events.reduce((total, e) => total + e.objective_count, 0);
    consequence = t('curriculum.edit.deleteModule', {
      sessions: counted('learning_event', sessions),
      objectives: counted('objective', objectives),
    });
  } else {
    consequence = t('curriculum.edit.deleteEvent', {
      objectives: counted('objective', target.event.objective_count),
    });
  }
  return (
    <DialogForm {...submit}>
      <Text>{consequence}</Text>
      <Text size="sm" c="dimmed">
        {t('curriculum.edit.deleteNote')}
      </Text>
    </DialogForm>
  );
}

function termOf(target: DeleteTarget): string {
  return target.kind === 'event' ? 'learning_event' : target.kind;
}

/** Confirm deleting a phase, module or session, saying what goes with it. */
export function DeleteDialog({ opened, target, ...props }: DeleteDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('curriculum.edit.deleteTitle', { name: nameOf(target) })}
    >
      <DeleteForm target={target} {...props} />
    </EditDialog>
  );
}
