import { useState } from 'react';
import { Checkbox, NativeSelect, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import { addTag, fetchTagLists, fetchTagPreview, queryKeys } from '../api/endpoints';
import type { PreviewItem, TaggableKind } from '../api/types';
import { LoadingState } from '../ui/States';
import { DialogForm, EditDialog } from './EditDialog';
import { editErrorMessage, useRefreshCurriculum, type EditResult } from './editing';
import classes from './TagDialog.module.css';

interface TagDialogProps {
  opened: boolean;
  kind: TaggableKind;
  itemId: string;
  itemName: string;
  versionId: string;
  /** Tags already set directly on the item; they are not offered again. */
  directValueIds: ReadonlySet<string>;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

/** What a preview line says will happen to the item, in words. */
function statusText(t: TFunction, item: PreviewItem): string {
  if (item.status === 'new') return t('tags.preview.new');
  if (item.status === 'has_tag') return t('tags.preview.hasTag');
  return t('tags.preview.notApplicable');
}

function itemKindText(t: TFunction, item: PreviewItem): string {
  if (item.item_type === 'learning_event') return t('terms.learning_event', { count: 1 });
  if (item.level === 'programme') return t('tags.preview.programmeOutcome');
  if (item.level === 'module') return t('tags.preview.moduleOutcome');
  return t('terms.objective', { count: 1 });
}

/** The items a tag would reach, each with what will happen to it; scrolls and can be focused. */
export function PreviewItems({ items }: { items: PreviewItem[] }) {
  const { t } = useTranslation();
  return (
    <div
      className={classes.items}
      role="group"
      tabIndex={0}
      aria-label={t('tags.preview.listLabel', { count: items.length })}
    >
      <ul className={classes.list}>
        {items.map((item) => (
          <li key={item.item_id} className={classes.row}>
            <span className={classes.name}>
              <span className={classes.kind}>
                {itemKindText(t, item)}
                {item.module_code ? ` · ${item.module_code}` : ''}
                {': '}
              </span>
              {item.name}
            </span>
            <span className={classes.status} data-status={item.status}>
              {statusText(t, item)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TagForm({
  kind,
  itemId,
  itemName,
  versionId,
  directValueIds,
  onClose,
  onSaved,
}: Omit<TagDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const refresh = useRefreshCurriculum(versionId);
  const lists = useQuery({ queryKey: queryKeys.tagLists, queryFn: fetchTagLists });
  const [valueId, setValueId] = useState('');
  // Whether the person ticked or cleared the box; until then it follows what is on offer.
  const [chosen, setChosen] = useState<boolean | null>(null);
  const [missing, setMissing] = useState(false);

  const passesOn = kind !== 'learning_event';
  const preview = useQuery({
    queryKey: queryKeys.tagPreview(kind, itemId, valueId),
    queryFn: () => fetchTagPreview(kind, itemId, valueId),
    enabled: passesOn && valueId !== '',
    // The preview must match what saving will do, so never reuse an old one.
    staleTime: 0,
    gcTime: 0,
  });
  const reached = (preview.data?.items ?? []).filter((item) => item.status === 'new');
  const inherit = (chosen ?? true) && reached.length > 0;

  const mutation = useMutation({
    mutationFn: () => addTag(kind, itemId, valueId, inherit),
    onSuccess: async (applied) => {
      await refresh();
      await client.invalidateQueries({ queryKey: ['tag-preview'] });
      const label = lists.data
        ?.flatMap((list) => list.values)
        .find((value) => value.id === valueId)?.label;
      const values = { tag: label ?? '', name: itemName, count: applied.inherited_count };
      onSaved({
        message: t(applied.inherited_count > 0 ? 'tags.addedAndPassedOn' : 'tags.added', values),
      });
    },
  });

  const groups = (lists.data ?? [])
    .filter((list) => list.is_active && list.entity_types.includes(kind))
    .map((list) => ({
      group: list.name,
      items: list.values
        .filter((value) => value.is_active && !directValueIds.has(value.id))
        .map((value) => ({ value: value.id, label: value.label })),
    }))
    .filter((group) => group.items.length > 0);

  return (
    <DialogForm
      submitLabel={t('tags.save')}
      error={mutation.isError ? editErrorMessage(t, mutation.error) : null}
      busy={mutation.isPending}
      onSubmit={(event) => {
        event.preventDefault();
        if (valueId === '') {
          setMissing(true);
          return;
        }
        mutation.mutate();
      }}
      onClose={onClose}
    >
      {lists.isPending ? (
        <LoadingState skeletons={1} />
      ) : lists.isError ? (
        <Text role="alert" size="sm">
          {t('tags.listsError')}
        </Text>
      ) : groups.length === 0 ? (
        <Text c="dimmed">{t('tags.noLists')}</Text>
      ) : (
        <NativeSelect
          label={t('tags.chooseTag')}
          description={t('tags.chooseHint', { name: itemName })}
          data-autofocus
          required
          error={missing && valueId === '' ? t('curriculum.edit.required') : undefined}
          value={valueId}
          onChange={(event) => {
            setValueId(event.currentTarget.value);
            setChosen(null);
            setMissing(false);
          }}
          data={[{ value: '', label: t('tags.choosePlaceholder') }, ...groups]}
        />
      )}
      {passesOn && valueId !== '' && (
        <div className={classes.preview} aria-live="polite">
          {preview.isPending ? (
            <Text size="sm" c="dimmed">
              {t('tags.preview.loading')}
            </Text>
          ) : preview.isError ? (
            <Text role="alert" size="sm">
              {t('tags.preview.error')}
            </Text>
          ) : preview.data.items.length === 0 ? (
            <Text size="sm" c="dimmed">
              {t(kind === 'module' ? 'tags.preview.noSessions' : 'tags.preview.noLinked', {
                sessions: t('terms.learning_event', { count: 2 }).toLocaleLowerCase(),
                module: t('terms.module', { count: 1 }).toLocaleLowerCase(),
              })}
            </Text>
          ) : (
            <>
              <Checkbox
                label={t('tags.preview.inherit', { count: reached.length })}
                description={t('tags.preview.inheritHint')}
                checked={inherit}
                disabled={reached.length === 0}
                onChange={(event) => setChosen(event.currentTarget.checked)}
              />
              <PreviewItems items={preview.data.items} />
            </>
          )}
        </div>
      )}
    </DialogForm>
  );
}

/** Tag an item. For modules and objectives a preview lists every item the tag would reach. */
export function TagDialog({ opened, ...props }: TagDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('tags.addTitle', { name: props.itemName })}
    >
      <TagForm {...props} />
    </EditDialog>
  );
}
