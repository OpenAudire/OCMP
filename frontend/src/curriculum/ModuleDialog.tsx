import { NativeSelect, NumberInput, Text, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { createModule, fetchModule, queryKeys, updateModule } from '../api/endpoints';
import type { ModuleDetail, ModuleInput, StructureModule, VersionStructure } from '../api/types';
import { LoadingState } from '../ui/States';
import { DialogForm, EditDialog } from './EditDialog';
import {
  editErrorMessage,
  moduleAncestors,
  nounsFor,
  optionalNumber,
  optionalText,
  useRefreshCurriculum,
  type EditResult,
} from './editing';

interface ModuleDialogProps {
  opened: boolean;
  structure: VersionStructure;
  /** The module to change; without it the dialog adds one. */
  module?: StructureModule;
  /** Where a new module goes: a phase id, or null for "Across phases". */
  phaseId?: string | null;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

interface Values {
  code: string;
  name: string;
  /** '' for a module that runs across phases. */
  phase: string;
  credits: number | string;
  nqfLevel: number | string;
  description: string;
  lmsRef: string;
}

interface ModuleFormProps extends Omit<ModuleDialogProps, 'opened' | 'module'> {
  module?: StructureModule;
  detail?: ModuleDetail;
}

function ModuleForm({ structure, module, detail, phaseId, onClose, onSaved }: ModuleFormProps) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const versionId = structure.version.id;
  const refresh = useRefreshCurriculum(versionId);
  // Only people who may change the programme's structure move modules between phases.
  const canMove = structure.can_edit;
  const form = useForm<Values>({
    initialValues: {
      code: detail?.code ?? '',
      name: detail?.name ?? '',
      phase: (detail ? detail.phase_id : phaseId) ?? '',
      credits: detail?.credits != null ? Number(detail.credits) : '',
      nqfLevel: detail?.nqf_level ?? '',
      description: detail?.description ?? '',
      lmsRef: detail?.external_lms_ref ?? '',
    },
    validate: {
      code: (value) => (value.trim() ? null : t('curriculum.edit.required')),
      name: (value) => (value.trim() ? null : t('curriculum.edit.required')),
      credits: (value) =>
        value === '' || Number(value) >= 0 ? null : t('curriculum.edit.notNegative'),
      nqfLevel: (value) => {
        const level = Number(value);
        return value === '' || (Number.isInteger(level) && level >= 1 && level <= 10)
          ? null
          : t('curriculum.edit.nqfRange');
      },
    },
  });
  const save = useMutation({
    mutationFn: (values: Values) => {
      const credits = optionalNumber(values.credits);
      const input: ModuleInput = {
        code: values.code.trim(),
        name: values.name.trim(),
        phase_id: values.phase || null,
        credits: credits === null ? null : String(credits),
        nqf_level: optionalNumber(values.nqfLevel),
        description: values.description.trim(),
        external_lms_ref: optionalText(values.lmsRef),
      };
      if (!module) return createModule(versionId, input);
      const { phase_id, ...rest } = input;
      return updateModule(module.id, canMove ? { ...rest, phase_id } : rest);
    },
    onSuccess: async (saved) => {
      await refresh();
      const name = `${saved.code} ${saved.name}`;
      onSaved({
        message: t(module ? 'curriculum.edit.saved' : 'curriculum.edit.added', { name }),
        select: `module:${saved.id}`,
        reveal: moduleAncestors(saved.phase_id),
      });
    },
  });

  return (
    <DialogForm
      submitLabel={
        module ? t('curriculum.edit.save') : t('curriculum.edit.add', { noun: nouns.module })
      }
      error={
        save.isError
          ? editErrorMessage(t, save.error, t('curriculum.edit.errors.codeTaken', nouns))
          : null
      }
      busy={save.isPending}
      onSubmit={form.onSubmit((values) => save.mutate(values))}
      onClose={onClose}
    >
      <TextInput
        label={t('curriculum.edit.fields.code')}
        required
        maxLength={32}
        data-autofocus
        {...form.getInputProps('code')}
      />
      <TextInput
        label={t('curriculum.edit.fields.name')}
        required
        maxLength={255}
        {...form.getInputProps('name')}
      />
      {canMove && (
        <NativeSelect
          label={t('terms.phase', { count: 1 })}
          data={[
            ...structure.phases.map((phase) => ({ value: phase.id, label: phase.name })),
            { value: '', label: t('curriculum.edit.fields.acrossPhases') },
          ]}
          {...form.getInputProps('phase')}
        />
      )}
      <NumberInput
        label={t('curriculum.details.credits')}
        min={0}
        max={9999.9}
        decimalScale={1}
        {...form.getInputProps('credits')}
      />
      <NumberInput
        label={t('curriculum.details.nqfLevel')}
        min={1}
        max={10}
        allowDecimal={false}
        {...form.getInputProps('nqfLevel')}
      />
      <Textarea
        label={t('curriculum.edit.fields.description')}
        rows={4}
        maxLength={10000}
        {...form.getInputProps('description')}
      />
      <TextInput
        label={t('curriculum.edit.fields.lmsRef')}
        description={t('curriculum.edit.fields.lmsRefHint')}
        maxLength={255}
        {...form.getInputProps('lmsRef')}
      />
    </DialogForm>
  );
}

/** Loads the module's full details before showing the form to change it. */
function EditModuleForm(props: ModuleFormProps & { module: StructureModule }) {
  const { t } = useTranslation();
  const detail = useQuery({
    queryKey: queryKeys.module(props.module.id),
    queryFn: () => fetchModule(props.module.id),
  });
  if (detail.isPending) return <LoadingState skeletons={2} />;
  if (detail.isError) {
    return (
      <DialogForm submitLabel="" error={null} busy={false} onClose={props.onClose}>
        <Text role="alert">{t('curriculum.edit.errors.loadItem')}</Text>
      </DialogForm>
    );
  }
  return <ModuleForm {...props} detail={detail.data} />;
}

/** Add a module to the version, or change one. */
export function ModuleDialog({ opened, module, ...props }: ModuleDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={
        module
          ? t('curriculum.edit.editTitle', { name: `${module.code} ${module.name}` })
          : t('curriculum.edit.add', { noun: nounsFor(t).module })
      }
    >
      {module ? <EditModuleForm module={module} {...props} /> : <ModuleForm {...props} />}
    </EditDialog>
  );
}
