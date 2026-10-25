import { NativeSelect, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { createPhase, updatePhase } from '../api/endpoints';
import type { PhaseInput, PhaseKind, StructurePhase } from '../api/types';
import { DialogForm, EditDialog } from './EditDialog';
import { editErrorMessage, nounsFor, useRefreshCurriculum, type EditResult } from './editing';
import { ROOT_ID } from './treeModel';

const KINDS: PhaseKind[] = ['year', 'phase', 'block', 'longitudinal_thread'];

interface PhaseDialogProps {
  opened: boolean;
  versionId: string;
  /** The phase to change; without it the dialog adds one. */
  phase?: StructurePhase;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

function PhaseForm({ versionId, phase, onClose, onSaved }: Omit<PhaseDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const refresh = useRefreshCurriculum(versionId);
  const form = useForm<PhaseInput>({
    initialValues: { name: phase?.name ?? '', kind: phase?.kind ?? 'year' },
    validate: {
      name: (value) => (value.trim() ? null : t('curriculum.edit.required')),
    },
  });
  const save = useMutation({
    mutationFn: (values: PhaseInput) => {
      const input = { ...values, name: values.name.trim() };
      return phase ? updatePhase(phase.id, input) : createPhase(versionId, input);
    },
    onSuccess: async (saved) => {
      await refresh();
      onSaved(
        phase
          ? { message: t('curriculum.edit.saved', { name: saved.name }) }
          : {
              message: t('curriculum.edit.added', { name: saved.name }),
              select: `phase:${saved.id}`,
              reveal: [ROOT_ID],
            }
      );
    },
  });

  return (
    <DialogForm
      submitLabel={
        phase ? t('curriculum.edit.save') : t('curriculum.edit.add', { noun: nouns.phase })
      }
      error={save.isError ? editErrorMessage(t, save.error) : null}
      busy={save.isPending}
      onSubmit={form.onSubmit((values) => save.mutate(values))}
      onClose={onClose}
    >
      <TextInput
        label={t('curriculum.edit.fields.name')}
        required
        maxLength={255}
        data-autofocus
        {...form.getInputProps('name')}
      />
      <NativeSelect
        label={t('curriculum.edit.fields.kind')}
        data={KINDS.map((kind) => ({ value: kind, label: t(`curriculum.phaseKind.${kind}`) }))}
        {...form.getInputProps('kind')}
      />
    </DialogForm>
  );
}

/** Add a phase to the version, or rename one and change its kind. */
export function PhaseDialog({ opened, phase, ...props }: PhaseDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={
        phase
          ? t('curriculum.edit.editTitle', { name: phase.name })
          : t('curriculum.edit.add', { noun: nounsFor(t).phase })
      }
    >
      <PhaseForm phase={phase} {...props} />
    </EditDialog>
  );
}
