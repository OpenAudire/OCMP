import type { FormEvent } from 'react';
import { Checkbox, NativeSelect, Stack, Text, Textarea } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  createEventObjective,
  createModuleOutcome,
  createProgrammeOutcome,
  deleteObjective,
  fetchEventLinkOptions,
  fetchModuleLinkOptions,
  fetchTaxonomyScales,
  queryKeys,
  updateObjective,
} from '../api/endpoints';
import type {
  Objective,
  ObjectiveDomain,
  ObjectiveInput,
  ObjectiveOption,
  ObjectiveStatus,
} from '../api/types';
import { LoadingState } from '../ui/States';
import { DialogForm, EditDialog } from './EditDialog';
import {
  editErrorMessage,
  objectiveNoun,
  optionalText,
  useRefreshCurriculum,
  type EditResult,
  type ObjectiveOwner,
} from './editing';
import classes from './ObjectiveDialog.module.css';

interface ObjectiveDialogProps {
  opened: boolean;
  versionId: string;
  owner: ObjectiveOwner;
  /** The objective to change; without it the dialog adds one. */
  objective?: Objective;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

interface Values {
  text: string;
  domain: string;
  taxonomyLevel: string;
  status: ObjectiveStatus;
  parents: string[];
}

const DOMAINS: ObjectiveDomain[] = ['knowledge', 'skill', 'attitude'];
const STATUSES: ObjectiveStatus[] = ['draft', 'approved', 'retired'];

function useLinkOptions(owner: ObjectiveOwner) {
  const key =
    owner.kind === 'module'
      ? queryKeys.linkOptions('module', owner.module.id)
      : owner.kind === 'event'
        ? queryKeys.linkOptions('event', owner.event.id)
        : (['link-options', 'programme'] as const);
  return useQuery({
    queryKey: key,
    queryFn: (): Promise<ObjectiveOption[]> =>
      owner.kind === 'module'
        ? fetchModuleLinkOptions(owner.module.id)
        : owner.kind === 'event'
          ? fetchEventLinkOptions(owner.event.id)
          : Promise.resolve([]),
    // Programme outcomes do not link upward.
    enabled: owner.kind !== 'programme',
  });
}

function save(owner: ObjectiveOwner, versionId: string, input: ObjectiveInput, id?: string) {
  if (id) return updateObjective(id, input);
  switch (owner.kind) {
    case 'programme':
      return createProgrammeOutcome(versionId, input);
    case 'module':
      return createModuleOutcome(owner.module.id, input);
    case 'event':
      return createEventObjective(owner.event.id, input);
  }
}

function ObjectiveForm({
  versionId,
  owner,
  objective,
  onClose,
  onSaved,
}: Omit<ObjectiveDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const refresh = useRefreshCurriculum(versionId);
  const noun = objectiveNoun(t, owner);
  const scales = useQuery({ queryKey: queryKeys.taxonomyScales, queryFn: fetchTaxonomyScales });
  const options = useLinkOptions(owner);
  const form = useForm<Values>({
    initialValues: {
      text: objective?.text ?? '',
      domain: objective?.domain ?? '',
      taxonomyLevel: objective?.taxonomy_level_id ?? '',
      status: objective?.status ?? 'draft',
      parents: objective?.parent_ids ?? [],
    },
    validate: {
      text: (value) => (value.trim() ? null : t('curriculum.edit.required')),
    },
  });
  const mutation = useMutation({
    mutationFn: (values: Values) => {
      const onOffer = new Set((options.data ?? []).map((option) => option.id));
      const input: ObjectiveInput = {
        text: values.text.trim(),
        domain: (optionalText(values.domain) as ObjectiveDomain | null) ?? null,
        taxonomy_level_id: optionalText(values.taxonomyLevel),
        status: values.status,
        // Only the links on offer are sent; the others stay as they are.
        parent_ids: values.parents.filter((id) => onOffer.has(id)),
      };
      return save(owner, versionId, input, objective?.id);
    },
    onSuccess: async () => {
      await refresh();
      onSaved({
        message: t(objective ? 'curriculum.objectives.saved' : 'curriculum.objectives.added', {
          noun,
        }),
      });
    },
  });

  const offered = options.data ?? [];
  const hiddenLinks = objective
    ? objective.parent_ids.filter((id) => !offered.some((option) => option.id === id)).length
    : 0;
  const levelGroups = (scales.data ?? [])
    .filter((scale) => scale.levels.length > 0)
    .map((scale) => ({
      group: scale.name,
      items: scale.levels.map((level) => ({ value: level.id, label: level.name })),
    }));

  return (
    <DialogForm
      submitLabel={objective ? t('curriculum.edit.save') : t('curriculum.edit.add', { noun })}
      error={mutation.isError ? editErrorMessage(t, mutation.error) : null}
      busy={mutation.isPending}
      onSubmit={form.onSubmit((values) => mutation.mutate(values))}
      onClose={onClose}
    >
      <Textarea
        label={t('curriculum.objectives.text')}
        description={t('curriculum.objectives.textHint')}
        required
        rows={4}
        maxLength={2000}
        data-autofocus
        {...form.getInputProps('text')}
      />
      <NativeSelect
        label={t('curriculum.objectives.domain')}
        data={[
          { value: '', label: t('curriculum.domain.none') },
          ...DOMAINS.map((domain) => ({ value: domain, label: t(`curriculum.domain.${domain}`) })),
        ]}
        {...form.getInputProps('domain')}
      />
      <NativeSelect
        label={t('curriculum.objectives.taxonomyLevel')}
        description={scales.isError ? t('curriculum.objectives.scalesError') : undefined}
        data={[{ value: '', label: t('curriculum.details.notSet') }, ...levelGroups]}
        {...form.getInputProps('taxonomyLevel')}
      />
      <NativeSelect
        label={t('curriculum.objectives.status')}
        data={STATUSES.map((status) => ({
          value: status,
          label: t(`curriculum.objectiveStatus.${status}`),
        }))}
        {...form.getInputProps('status')}
      />
      {owner.kind !== 'programme' && (
        <Stack gap="xs">
          {options.isPending ? (
            <LoadingState skeletons={1} />
          ) : options.isError ? (
            <Text role="alert" size="sm">
              {t('curriculum.objectives.optionsError')}
            </Text>
          ) : offered.length > 0 ? (
            <Checkbox.Group
              label={t('curriculum.objectives.parents')}
              description={t('curriculum.objectives.parentsHint')}
              {...form.getInputProps('parents')}
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
                          {option.module_code ??
                            t('curriculum.objectives.programmeLevel', {
                              programme: t('terms.programme', { count: 1 }),
                            })}
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
              {t('curriculum.objectives.noOptions')}
            </Text>
          )}
          {hiddenLinks > 0 && (
            <Text size="sm" c="dimmed">
              {t('curriculum.objectives.hiddenLinks', { count: hiddenLinks })}
            </Text>
          )}
        </Stack>
      )}
    </DialogForm>
  );
}

/** Add an outcome or objective to its owner, or change one. */
export function ObjectiveDialog({ opened, ...props }: ObjectiveDialogProps) {
  const { t } = useTranslation();
  const noun = objectiveNoun(t, props.owner);
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={
        props.objective
          ? t('curriculum.objectives.editTitle', { noun })
          : t('curriculum.objectives.addTitle', { noun })
      }
    >
      <ObjectiveForm {...props} />
    </EditDialog>
  );
}

function DeleteForm({
  versionId,
  objective,
  noun,
  onClose,
  onSaved,
}: Pick<ObjectiveDialogProps, 'versionId' | 'onClose' | 'onSaved'> & {
  objective: Objective;
  noun: string;
}) {
  const { t } = useTranslation();
  const refresh = useRefreshCurriculum(versionId);
  const run = useMutation({
    mutationFn: () => deleteObjective(objective.id),
    onSuccess: async () => {
      await refresh();
      // The Delete button is gone, so the confirmation takes focus.
      onSaved({ message: t('curriculum.objectives.deleted', { noun }), focus: true });
    },
  });
  return (
    <DialogForm
      submitLabel={t('curriculum.edit.delete', { noun })}
      error={run.isError ? editErrorMessage(t, run.error) : null}
      busy={run.isPending}
      danger
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        run.mutate();
      }}
      onClose={onClose}
    >
      <Text className={classes.quote}>{objective.text}</Text>
      <Text size="sm" c="dimmed">
        {t('curriculum.objectives.deleteNote')}
      </Text>
    </DialogForm>
  );
}

/** Confirm deleting an outcome or objective. */
export function ObjectiveDeleteDialog({
  opened,
  owner,
  objective,
  ...props
}: Omit<ObjectiveDialogProps, 'objective'> & { objective: Objective }) {
  const { t } = useTranslation();
  const noun = objectiveNoun(t, owner);
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('curriculum.objectives.deleteTitle', { noun })}
    >
      <DeleteForm {...props} objective={objective} noun={noun} />
    </EditDialog>
  );
}
