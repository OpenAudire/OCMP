import type { FormEvent } from 'react';
import { Checkbox, NativeSelect, NumberInput, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  createAssessment,
  createAssessmentItem,
  deleteAssessment,
  deleteAssessmentItem,
  fetchAssessableObjectives,
  fetchAssessmentMethods,
  queryKeys,
  updateAssessment,
  updateAssessmentItem,
} from '../api/endpoints';
import type {
  Assessment,
  AssessmentInput,
  AssessmentItem,
  AssessmentItemInput,
} from '../api/types';
import { LoadingState } from '../ui/States';
import { DialogForm, EditDialog } from './EditDialog';
import {
  editErrorMessage,
  optionalNumber,
  useRefreshCurriculum,
  type EditResult,
} from './editing';
import classes from './ObjectiveDialog.module.css';

interface CommonProps {
  opened: boolean;
  versionId: string;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

interface AssessmentDialogProps extends CommonProps {
  moduleId: string;
  /** The assessment to change; without it the dialog adds one. */
  assessment?: Assessment;
}

interface AssessmentValues {
  name: string;
  method: string;
  weight: number | string;
  timing: string;
  timeMinutes: number | string;
}

function AssessmentForm({
  versionId,
  moduleId,
  assessment,
  onClose,
  onSaved,
}: Omit<AssessmentDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const refresh = useRefreshCurriculum(versionId);
  const methods = useQuery({
    queryKey: queryKeys.assessmentMethods,
    queryFn: fetchAssessmentMethods,
  });
  const form = useForm<AssessmentValues>({
    initialValues: {
      name: assessment?.name ?? '',
      method: assessment?.method_value_id ?? '',
      weight: assessment?.weight != null ? Number(assessment.weight) : '',
      timing: assessment?.timing ?? '',
      timeMinutes: assessment?.time_minutes ?? 0,
    },
    validate: {
      name: (value) => (value.trim() ? null : t('curriculum.edit.required')),
      weight: (value) =>
        value === '' || (Number(value) >= 0 && Number(value) <= 100)
          ? null
          : t('curriculum.assessments.weightRange'),
      timeMinutes: (value) =>
        value === '' || (Number.isInteger(Number(value)) && Number(value) >= 0)
          ? null
          : t('curriculum.edit.wholeNumber'),
    },
  });
  const save = useMutation({
    mutationFn: (values: AssessmentValues) => {
      const input: AssessmentInput = {
        name: values.name.trim(),
        method_value_id: values.method || null,
        weight: optionalNumber(values.weight),
        timing: values.timing.trim(),
        time_minutes: optionalNumber(values.timeMinutes) ?? 0,
      };
      return assessment
        ? updateAssessment(assessment.id, input)
        : createAssessment(moduleId, input);
    },
    onSuccess: async (saved) => {
      await refresh();
      onSaved({
        message: t(assessment ? 'curriculum.assessments.saved' : 'curriculum.assessments.added', {
          name: saved.name,
        }),
      });
    },
  });

  // Keep a method that has been retired since it was chosen, so saving does not drop it.
  const options = (methods.data ?? []).map((method) => ({ value: method.id, label: method.label }));
  if (assessment?.method_value_id && !options.some((o) => o.value === assessment.method_value_id)) {
    options.unshift({ value: assessment.method_value_id, label: assessment.method ?? '' });
  }

  return (
    <DialogForm
      submitLabel={
        assessment ? t('curriculum.edit.save') : t('curriculum.assessments.addAssessment')
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
        label={t('curriculum.assessments.method')}
        description={methods.isError ? t('curriculum.assessments.methodsError') : undefined}
        data={[{ value: '', label: t('curriculum.details.notSet') }, ...options]}
        {...form.getInputProps('method')}
      />
      <NumberInput
        label={t('curriculum.assessments.weight')}
        description={t('curriculum.assessments.weightHint')}
        min={0}
        max={100}
        decimalScale={1}
        {...form.getInputProps('weight')}
      />
      <TextInput
        label={t('curriculum.assessments.timing')}
        description={t('curriculum.assessments.timingHint')}
        maxLength={128}
        {...form.getInputProps('timing')}
      />
      <NumberInput
        label={t('curriculum.assessments.timeMinutes')}
        description={t('curriculum.assessments.timeHint')}
        min={0}
        allowDecimal={false}
        {...form.getInputProps('timeMinutes')}
      />
    </DialogForm>
  );
}

/** Add an assessment to a module, or change one. */
export function AssessmentDialog({ opened, assessment, ...props }: AssessmentDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={
        assessment
          ? t('curriculum.edit.editTitle', { name: assessment.name })
          : t('curriculum.assessments.addAssessment')
      }
    >
      <AssessmentForm assessment={assessment} {...props} />
    </EditDialog>
  );
}

interface ItemDialogProps extends CommonProps {
  moduleId: string;
  assessment: Assessment;
  /** The item to change; without it the dialog adds one. */
  item?: AssessmentItem;
}

interface ItemValues {
  label: string;
  marks: number | string;
  objectives: string[];
}

function ItemForm({
  versionId,
  moduleId,
  assessment,
  item,
  onClose,
  onSaved,
}: Omit<ItemDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const refresh = useRefreshCurriculum(versionId);
  const objectives = useQuery({
    queryKey: queryKeys.assessableObjectives(moduleId),
    queryFn: () => fetchAssessableObjectives(moduleId),
  });
  const form = useForm<ItemValues>({
    initialValues: {
      label: item?.label ?? '',
      marks: item?.marks != null ? Number(item.marks) : '',
      objectives: item?.objective_ids ?? [],
    },
    validate: {
      label: (value) => (value.trim() ? null : t('curriculum.edit.required')),
      marks: (value) =>
        value === '' || Number(value) >= 0 ? null : t('curriculum.edit.notNegative'),
    },
  });
  const save = useMutation({
    mutationFn: (values: ItemValues) => {
      const input: AssessmentItemInput = {
        label: values.label.trim(),
        marks: optionalNumber(values.marks),
        objective_ids: values.objectives,
      };
      return item
        ? updateAssessmentItem(item.id, input)
        : createAssessmentItem(assessment.id, input);
    },
    onSuccess: async (_saved, submitted) => {
      await refresh();
      onSaved({
        message: t(item ? 'curriculum.assessments.itemSaved' : 'curriculum.assessments.itemAdded', {
          name: submitted.label.trim(),
        }),
      });
    },
  });
  const offered = objectives.data ?? [];

  return (
    <DialogForm
      submitLabel={item ? t('curriculum.edit.save') : t('curriculum.assessments.addItem')}
      error={save.isError ? editErrorMessage(t, save.error) : null}
      busy={save.isPending}
      onSubmit={form.onSubmit((submitted) => save.mutate(submitted))}
      onClose={onClose}
    >
      <TextInput
        label={t('curriculum.assessments.itemLabel')}
        description={t('curriculum.assessments.itemLabelHint')}
        required
        maxLength={255}
        data-autofocus
        {...form.getInputProps('label')}
      />
      <NumberInput
        label={t('curriculum.assessments.marks')}
        min={0}
        decimalScale={1}
        {...form.getInputProps('marks')}
      />
      <Stack gap="xs">
        {objectives.isPending ? (
          <LoadingState skeletons={1} />
        ) : objectives.isError ? (
          <Text role="alert" size="sm">
            {t('curriculum.assessments.objectivesError')}
          </Text>
        ) : offered.length > 0 ? (
          <Checkbox.Group
            label={t('curriculum.assessments.assesses')}
            description={t('curriculum.assessments.assessesHint')}
            {...form.getInputProps('objectives')}
          >
            <Stack gap={0} mt="xs">
              {offered.map((option) => (
                <Checkbox
                  key={option.id}
                  value={option.id}
                  classNames={{ root: classes.option }}
                  label={
                    <>
                      <span className={classes.optionLevel}>
                        {option.event_title ?? t('curriculum.assessments.moduleLevel')}
                        {': '}
                      </span>
                      {option.text}
                    </>
                  }
                />
              ))}
            </Stack>
          </Checkbox.Group>
        ) : (
          <Text size="sm" c="dimmed">
            {t('curriculum.assessments.noObjectives')}
          </Text>
        )}
      </Stack>
    </DialogForm>
  );
}

/** Add an item to an assessment, or change one. */
export function ItemDialog({ opened, item, ...props }: ItemDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={
        item
          ? t('curriculum.edit.editTitle', { name: item.label })
          : t('curriculum.assessments.addItemTo', { name: props.assessment.name })
      }
    >
      <ItemForm item={item} {...props} />
    </EditDialog>
  );
}

interface DeleteProps extends CommonProps {
  /** What is deleted: an assessment (with its items) or one item. */
  target: { kind: 'assessment'; assessment: Assessment } | { kind: 'item'; item: AssessmentItem };
}

function DeleteForm({ versionId, target, onClose, onSaved }: Omit<DeleteProps, 'opened'>) {
  const { t } = useTranslation();
  const refresh = useRefreshCurriculum(versionId);
  const name = target.kind === 'assessment' ? target.assessment.name : target.item.label;
  const run = useMutation({
    mutationFn: () =>
      target.kind === 'assessment'
        ? deleteAssessment(target.assessment.id)
        : deleteAssessmentItem(target.item.id),
    onSuccess: async () => {
      await refresh();
      // The Delete button is gone, so the confirmation takes focus.
      onSaved({ message: t('curriculum.edit.deleted', { name }), focus: true });
    },
  });
  return (
    <DialogForm
      submitLabel={t(
        target.kind === 'assessment'
          ? 'curriculum.assessments.deleteAssessment'
          : 'curriculum.assessments.deleteItem'
      )}
      error={run.isError ? editErrorMessage(t, run.error) : null}
      busy={run.isPending}
      danger
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        run.mutate();
      }}
      onClose={onClose}
    >
      <Text className={classes.quote}>{name}</Text>
      {target.kind === 'assessment' && (
        <Text size="sm">{t('curriculum.assessments.deleteAssessmentNote')}</Text>
      )}
      <Text size="sm" c="dimmed">
        {t('curriculum.edit.deleteNote')}
      </Text>
    </DialogForm>
  );
}

/** Confirm deleting an assessment (with its items) or an item. */
export function AssessmentDeleteDialog({ opened, ...props }: DeleteProps) {
  const { t } = useTranslation();
  const name =
    props.target.kind === 'assessment' ? props.target.assessment.name : props.target.item.label;
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('curriculum.edit.deleteTitle', { name })}
    >
      <DeleteForm {...props} />
    </EditDialog>
  );
}
