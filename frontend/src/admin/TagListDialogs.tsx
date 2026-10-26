import type { FormEvent } from 'react';
import { Checkbox, NativeSelect, Text, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import {
  createTagList,
  createTagValue,
  deleteTagList,
  deleteTagValue,
  fetchTagListPlaces,
  queryKeys,
  updateTagList,
  updateTagValue,
} from '../api/endpoints';
import type { TagList, TagListKind, TagValue } from '../api/types';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';
import { editErrorMessage, optionalText } from '../curriculum/editing';
import { ITEM_TYPES, LIST_KINDS } from './tagListOptions';

/** What a dialog reports when it has saved: the sentence to announce. */
export interface Saved {
  message: string;
  /** Move focus to the confirmation (the button that made the change is gone). */
  focus?: boolean;
}

interface BaseProps {
  opened: boolean;
  onClose: () => void;
  onSaved: (result: Saved) => void;
}

function useRefreshLists() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: queryKeys.tagLists });
}

// --- A tag list: add or change ------------------------------------------------------

interface ListValues {
  name: string;
  key: string;
  kind: TagListKind;
  description: string;
  entityTypes: string[];
  /** '' is the whole institution, otherwise a faculty id. */
  place: string;
}

const KEY_PATTERN = /^[a-z0-9_-]+$/;

function ListForm({
  list,
  onClose,
  onSaved,
}: Omit<BaseProps, 'opened'> & { list?: TagList }) {
  const { t } = useTranslation();
  const refresh = useRefreshLists();
  const places = useQuery({
    queryKey: queryKeys.tagListPlaces,
    queryFn: fetchTagListPlaces,
    enabled: !list,
  });
  const form = useForm<ListValues>({
    initialValues: {
      place: '',
      name: list?.name ?? '',
      key: list?.key ?? '',
      kind: list?.kind ?? 'custom',
      description: list?.description ?? '',
      entityTypes: list
        ? list.entity_types.filter((type) => type !== 'programme')
        : ITEM_TYPES.map((type) => type.value),
    },
    validate: {
      name: (value) => (value.trim() ? null : t('curriculum.edit.required')),
      key: (value) =>
        list || KEY_PATTERN.test(value) ? null : t('admin.tagLists.keyInvalid'),
      entityTypes: (value) => (value.length > 0 ? null : t('admin.tagLists.typesRequired')),
    },
  });
  const mutation = useMutation({
    mutationFn: (values: ListValues) => {
      // Who may create where decides the choices; with only faculties on offer the first one.
      const place =
        values.place ||
        (places.data && !places.data.institution ? (places.data.faculties[0]?.id ?? '') : '');
      // A list made before this screen may also list programmes; keep that as it is.
      const kept = list?.entity_types.includes('programme') ? ['programme'] : [];
      const entity_types = [...values.entityTypes, ...kept];
      return list
        ? updateTagList(list.id, {
            name: values.name.trim(),
            description: values.description.trim(),
            entity_types,
          })
        : createTagList({
            key: values.key.trim(),
            name: values.name.trim(),
            kind: values.kind,
            description: values.description.trim(),
            entity_types,
            faculty_id: place || null,
          });
    },
    onSuccess: async (saved) => {
      await refresh();
      onSaved({ message: t(list ? 'admin.tagLists.listSaved' : 'admin.tagLists.listAdded', { name: saved.name }) });
    },
  });
  return (
    <DialogForm
      submitLabel={list ? t('curriculum.edit.save') : t('admin.tagLists.addList')}
      error={
        mutation.isError
          ? editErrorMessage(t, mutation.error, t('admin.tagLists.keyTaken'))
          : null
      }
      busy={mutation.isPending}
      onSubmit={form.onSubmit((values) => mutation.mutate(values))}
      onClose={onClose}
    >
      <TextInput
        label={t('admin.tagLists.name')}
        required
        maxLength={255}
        data-autofocus
        {...form.getInputProps('name')}
      />
      {!list && places.data && (places.data.institution || places.data.faculties.length > 1) && (
        <NativeSelect
          label={t('admin.tagLists.placeLabel')}
          description={t('admin.tagLists.placeHint')}
          data={[
            ...(places.data.institution
              ? [{ value: '', label: t('admin.tagLists.institutionWide') }]
              : []),
            ...places.data.faculties.map((faculty) => ({ value: faculty.id, label: faculty.name })),
          ]}
          {...form.getInputProps('place')}
        />
      )}
      {!list &&
        places.data &&
        !places.data.institution &&
        places.data.faculties.length === 1 && (
          <Text size="sm" c="dimmed">
            {t('admin.tagLists.placeFixed', { faculty: places.data.faculties[0].name })}
          </Text>
        )}
      {list ? (
        <Text size="sm" c="dimmed">
          {t('admin.tagLists.keyFixed', {
            key: list.key,
            kind: t(`admin.tagLists.kind.${list.kind}`),
          })}
        </Text>
      ) : (
        <>
          <TextInput
            label={t('admin.tagLists.key')}
            description={t('admin.tagLists.keyHint')}
            required
            maxLength={64}
            {...form.getInputProps('key')}
          />
          <NativeSelect
            label={t('admin.tagLists.kindLabel')}
            description={t('admin.tagLists.kindHint')}
            data={LIST_KINDS.map((kind) => ({
              value: kind,
              label: t(`admin.tagLists.kind.${kind}`),
            }))}
            {...form.getInputProps('kind')}
          />
        </>
      )}
      <Textarea
        label={t('admin.tagLists.description')}
        rows={3}
        maxLength={2000}
        {...form.getInputProps('description')}
      />
      <Checkbox.Group
        label={t('admin.tagLists.appliesTo')}
        description={t('admin.tagLists.appliesHint')}
        required
        {...form.getInputProps('entityTypes')}
      >
        {ITEM_TYPES.map((type) => (
          <Checkbox
            key={type.value}
            value={type.value}
            mt="xs"
            label={t(`terms.${type.term}`, { count: 2 })}
          />
        ))}
      </Checkbox.Group>
    </DialogForm>
  );
}

/** Add a tag list, or change one's name, description and the items it applies to. */
export function ListDialog({ opened, list, ...props }: BaseProps & { list?: TagList }) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={list ? t('admin.tagLists.editListTitle', { name: list.name }) : t('admin.tagLists.addListTitle')}
    >
      <ListForm list={list} {...props} />
    </EditDialog>
  );
}

// --- A tag: add or change -----------------------------------------------------------

interface ValueValues {
  label: string;
  code: string;
  description: string;
}

function ValueForm({
  list,
  value,
  onClose,
  onSaved,
}: Omit<BaseProps, 'opened'> & { list: TagList; value?: TagValue }) {
  const { t } = useTranslation();
  const refresh = useRefreshLists();
  const form = useForm<ValueValues>({
    initialValues: {
      label: value?.label ?? '',
      code: value?.code ?? '',
      description: value?.description ?? '',
    },
    validate: { label: (text) => (text.trim() ? null : t('curriculum.edit.required')) },
  });
  const mutation = useMutation({
    mutationFn: (values: ValueValues) => {
      const input = {
        label: values.label.trim(),
        code: optionalText(values.code),
        description: values.description.trim(),
      };
      return value ? updateTagValue(value.id, input) : createTagValue(list.id, input);
    },
    onSuccess: async (saved) => {
      await refresh();
      onSaved({
        message: t(value ? 'admin.tagLists.tagSaved' : 'admin.tagLists.tagAdded', {
          label: saved.label,
          list: list.name,
        }),
      });
    },
  });
  return (
    <DialogForm
      submitLabel={value ? t('curriculum.edit.save') : t('admin.tagLists.addTag')}
      error={
        mutation.isError
          ? editErrorMessage(t, mutation.error, t('admin.tagLists.labelTaken'))
          : null
      }
      busy={mutation.isPending}
      onSubmit={form.onSubmit((values) => mutation.mutate(values))}
      onClose={onClose}
    >
      <TextInput
        label={t('admin.tagLists.label')}
        required
        maxLength={255}
        data-autofocus
        {...form.getInputProps('label')}
      />
      <TextInput
        label={t('admin.tagLists.code')}
        description={t('admin.tagLists.codeHint')}
        maxLength={64}
        {...form.getInputProps('code')}
      />
      <Textarea
        label={t('admin.tagLists.description')}
        rows={3}
        maxLength={2000}
        {...form.getInputProps('description')}
      />
    </DialogForm>
  );
}

/** Add a tag to a list, or change one. */
export function ValueDialog({
  opened,
  list,
  value,
  ...props
}: BaseProps & { list: TagList; value?: TagValue }) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={
        value
          ? t('admin.tagLists.editTagTitle', { label: value.label })
          : t('admin.tagLists.addTagTitle', { list: list.name })
      }
    >
      <ValueForm list={list} value={value} {...props} />
    </EditDialog>
  );
}

// --- Delete ---------------------------------------------------------------------------

export type DeleteTarget = { kind: 'list'; list: TagList } | { kind: 'value'; value: TagValue; list: TagList };

function DeleteForm({
  target,
  onClose,
  onSaved,
}: Omit<BaseProps, 'opened'> & { target: DeleteTarget }) {
  const { t } = useTranslation();
  const refresh = useRefreshLists();
  const run = useMutation({
    mutationFn: () =>
      target.kind === 'list' ? deleteTagList(target.list.id) : deleteTagValue(target.value.id),
    onSuccess: async () => {
      await refresh();
      // The Delete button is gone, so the confirmation takes focus.
      onSaved({
        message:
          target.kind === 'list'
            ? t('admin.tagLists.listDeleted', { name: target.list.name })
            : t('admin.tagLists.tagDeleted', { label: target.value.label }),
        focus: true,
      });
    },
  });
  const name = target.kind === 'list' ? target.list.name : target.value.label;
  return (
    <DialogForm
      submitLabel={t('admin.tagLists.deleteConfirm', { name })}
      error={
        run.isError
          ? isApiError(run.error, 409)
            ? t('admin.tagLists.inUse')
            : editErrorMessage(t, run.error)
          : null
      }
      busy={run.isPending}
      danger
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        run.mutate();
      }}
      onClose={onClose}
    >
      <Text>
        {target.kind === 'list'
          ? t('admin.tagLists.deleteListBody', { name })
          : t('admin.tagLists.deleteTagBody', { name, list: target.list.name })}
      </Text>
      <Text size="sm" c="dimmed">
        {t('curriculum.edit.deleteNote')}
      </Text>
    </DialogForm>
  );
}

/** Confirm deleting a list or tag that nothing uses. */
export function DeleteDialog({
  opened,
  target,
  ...props
}: BaseProps & { target: DeleteTarget }) {
  const { t } = useTranslation();
  const name = target.kind === 'list' ? target.list.name : target.value.label;
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('admin.tagLists.deleteTitle', { name })}
    >
      <DeleteForm target={target} {...props} />
    </EditDialog>
  );
}
