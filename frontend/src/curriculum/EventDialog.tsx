import { NativeSelect, NumberInput, Text, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  createLearningEvent,
  fetchLearningEvent,
  fetchTeachingFormats,
  queryKeys,
  updateLearningEvent,
} from '../api/endpoints';
import type {
  LearningEventDetail,
  LearningEventInput,
  StructureEvent,
  StructureModule,
  StructurePhase,
} from '../api/types';
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

interface EventDialogProps {
  opened: boolean;
  versionId: string;
  module: StructureModule;
  phase: StructurePhase | null;
  /** The session to change; without it the dialog adds one to the module. */
  event?: StructureEvent;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

interface Values {
  title: string;
  format: string;
  contactMinutes: number | string;
  selfStudyMinutes: number | string;
  week: number | string;
  description: string;
  lmsRef: string;
}

interface EventFormProps extends Omit<EventDialogProps, 'opened'> {
  detail?: LearningEventDetail;
}

function minutesRule(t: (key: string) => string) {
  return (value: number | string) =>
    value === '' || (Number.isInteger(Number(value)) && Number(value) >= 0)
      ? null
      : t('curriculum.edit.wholeNumber');
}

function EventForm({ versionId, module, phase, event, detail, onClose, onSaved }: EventFormProps) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const refresh = useRefreshCurriculum(versionId);
  const formats = useQuery({ queryKey: queryKeys.teachingFormats, queryFn: fetchTeachingFormats });
  const form = useForm<Values>({
    initialValues: {
      title: detail?.title ?? '',
      format: detail?.format_value_id ?? '',
      contactMinutes: detail?.contact_minutes ?? 0,
      selfStudyMinutes: detail?.self_study_minutes ?? 0,
      week: detail?.week ?? '',
      description: detail?.description ?? '',
      lmsRef: detail?.external_lms_ref ?? '',
    },
    validate: {
      title: (value) => (value.trim() ? null : t('curriculum.edit.required')),
      contactMinutes: minutesRule(t),
      selfStudyMinutes: minutesRule(t),
      week: minutesRule(t),
    },
  });
  const save = useMutation({
    mutationFn: (values: Values) => {
      const input: LearningEventInput = {
        title: values.title.trim(),
        format_value_id: values.format || null,
        contact_minutes: optionalNumber(values.contactMinutes) ?? 0,
        self_study_minutes: optionalNumber(values.selfStudyMinutes) ?? 0,
        week: optionalNumber(values.week),
        description: values.description.trim(),
        external_lms_ref: optionalText(values.lmsRef),
      };
      return event ? updateLearningEvent(event.id, input) : createLearningEvent(module.id, input);
    },
    onSuccess: async (saved) => {
      await refresh();
      onSaved({
        message: t(event ? 'curriculum.edit.saved' : 'curriculum.edit.added', {
          name: saved.title,
        }),
        select: `event:${saved.id}`,
        reveal: [...moduleAncestors(phase?.id ?? null), `module:${module.id}`],
      });
    },
  });

  // Keep a format that has been retired since it was chosen, so saving does not drop it.
  const options = (formats.data ?? []).map((format) => ({
    value: format.id,
    label: format.label,
  }));
  if (detail?.format_value_id && !options.some((o) => o.value === detail.format_value_id)) {
    options.unshift({ value: detail.format_value_id, label: detail.format ?? '' });
  }

  return (
    <DialogForm
      submitLabel={
        event ? t('curriculum.edit.save') : t('curriculum.edit.add', { noun: nouns.session })
      }
      error={save.isError ? editErrorMessage(t, save.error) : null}
      busy={save.isPending}
      onSubmit={form.onSubmit((values) => save.mutate(values))}
      onClose={onClose}
    >
      <TextInput
        label={t('curriculum.edit.fields.title')}
        required
        maxLength={255}
        data-autofocus
        {...form.getInputProps('title')}
      />
      <NativeSelect
        label={t('curriculum.details.format')}
        description={formats.isError ? t('curriculum.edit.errors.formats') : undefined}
        data={[{ value: '', label: t('curriculum.details.notSet') }, ...options]}
        {...form.getInputProps('format')}
      />
      <NumberInput
        label={t('curriculum.edit.fields.contactMinutes')}
        min={0}
        allowDecimal={false}
        {...form.getInputProps('contactMinutes')}
      />
      <NumberInput
        label={t('curriculum.edit.fields.selfStudyMinutes')}
        min={0}
        allowDecimal={false}
        {...form.getInputProps('selfStudyMinutes')}
      />
      <NumberInput
        label={t('curriculum.details.week')}
        min={0}
        allowDecimal={false}
        {...form.getInputProps('week')}
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

/** Loads the session's full details before showing the form to change it. */
function EditEventForm(props: EventFormProps & { event: StructureEvent }) {
  const { t } = useTranslation();
  const detail = useQuery({
    queryKey: queryKeys.learningEvent(props.event.id),
    queryFn: () => fetchLearningEvent(props.event.id),
  });
  if (detail.isPending) return <LoadingState skeletons={2} />;
  if (detail.isError) {
    return (
      <DialogForm submitLabel="" error={null} busy={false} onClose={props.onClose}>
        <Text role="alert">{t('curriculum.edit.errors.loadItem')}</Text>
      </DialogForm>
    );
  }
  return <EventForm {...props} detail={detail.data} />;
}

/** Add a session to a module, or change one. */
export function EventDialog({ opened, event, ...props }: EventDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={
        event
          ? t('curriculum.edit.editTitle', { name: event.title })
          : t('curriculum.edit.addTo', {
              noun: nounsFor(t).session,
              name: props.module.code,
            })
      }
    >
      {event ? <EditEventForm event={event} {...props} /> : <EventForm {...props} />}
    </EditDialog>
  );
}
