import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Group, Paper, Text, Title } from '@mantine/core';
import {
  IconEye,
  IconEyeOff,
  IconPencil,
  IconPlus,
  IconTags,
  IconTrash,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { fetchTagLists, queryKeys, updateTagList, updateTagValue } from '../api/endpoints';
import type { TagList, TagValue } from '../api/types';
import { editErrorMessage } from '../curriculum/editing';
import { SuccessNotice } from '../pages/SuccessNotice';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import {
  DeleteDialog,
  ListDialog,
  ValueDialog,
  type DeleteTarget,
  type Saved,
} from './TagListDialogs';
import { ITEM_TYPES } from './tagListOptions';
import classes from './TagListsPage.module.css';

type Dialog =
  | { kind: 'addList' }
  | { kind: 'editList'; list: TagList }
  | { kind: 'addTag'; list: TagList }
  | { kind: 'editTag'; list: TagList; value: TagValue }
  | { kind: 'delete'; target: DeleteTarget };

interface Notice extends Saved {
  key: number;
}

function usedOn(list: TagList): string[] {
  return ITEM_TYPES.filter((type) => list.entity_types.includes(type.value)).map((type) => type.term);
}

/** The tag lists of the institution, for the curriculum office to keep. */
export function TagListsPage() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const lists = useQuery({ queryKey: queryKeys.tagLists, queryFn: fetchTagLists });
  const [dialog, setDialog] = useState<Dialog | null>(null);
  // Kept while a dialog closes so it does not flash empty.
  const [last, setLast] = useState<Dialog | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (notice?.focus) noticeRef.current?.focus();
  }, [notice]);

  const open = (next: Dialog) => {
    setLast(next);
    setDialog(next);
  };
  const close = () => setDialog(null);
  const saved = (result: Saved) => {
    setDialog(null);
    setFailure(null);
    setNotice({ ...result, key: Date.now() });
  };

  const toggle = useMutation({
    mutationFn: async (change: { list: TagList; value?: TagValue }): Promise<void> => {
      if (change.value) {
        await updateTagValue(change.value.id, { is_active: !change.value.is_active });
      } else {
        await updateTagList(change.list.id, { is_active: !change.list.is_active });
      }
    },
    onMutate: () => setFailure(null),
    onSuccess: async (_data, change) => {
      await client.invalidateQueries({ queryKey: queryKeys.tagLists });
      const active = change.value ? !change.value.is_active : !change.list.is_active;
      const name = change.value ? change.value.label : change.list.name;
      setNotice({
        key: Date.now(),
        message: t(active ? 'admin.tagLists.nowActive' : 'admin.tagLists.nowInactive', { name }),
      });
    },
    onError: (error) => setFailure(editErrorMessage(t, error)),
  });

  const noticeBox = notice && (
    <div key={notice.key} ref={noticeRef} tabIndex={-1} className={classes.notice}>
      <SuccessNotice>{notice.message}</SuccessNotice>
    </div>
  );
  const addList = (
    <Button
      leftSection={<IconPlus size={18} aria-hidden />}
      onClick={() => open({ kind: 'addList' })}
    >
      {t('admin.tagLists.addList')}
    </Button>
  );
  const title = t('admin.tagLists.title');

  if (lists.isPending) {
    return (
      <Page title={title}>
        <LoadingState skeletons={2} />
      </Page>
    );
  }
  if (lists.isError) {
    return (
      <Page title={title}>
        <ErrorState
          title={t('admin.tagLists.loadErrorTitle')}
          body={t('admin.tagLists.loadErrorBody')}
          actions={<Button onClick={() => void lists.refetch()}>{t('pages.retry')}</Button>}
        />
      </Page>
    );
  }

  const common = { onClose: close, onSaved: saved };
  const current = dialog ?? last;
  return (
    <Page title={title} description={t('admin.tagLists.description_page')}>
      {noticeBox}
      {failure && <Alert color="red">{failure}</Alert>}
      {lists.data.length === 0 ? (
        <EmptyState
          icon={IconTags}
          title={t('admin.tagLists.emptyTitle')}
          body={t('admin.tagLists.emptyBody')}
          actions={addList}
        />
      ) : (
        <>
          <Group>{addList}</Group>
          {lists.data.map((list) => {
            const inUse = list.values.some((value) => value.usage_count > 0);
            return (
              <Paper
                key={list.id}
                withBorder
                className={classes.card}
                component="section"
                aria-label={list.name}
              >
                <div className={classes.header}>
                  <Title order={2} className={classes.listTitle}>
                    {list.name}
                  </Title>
                  <span className={classes.chip}>{t(`admin.tagLists.kind.${list.kind}`)}</span>
                  {!list.is_active && (
                    <span className={classes.chip} data-tone="attention">
                      {t('admin.tagLists.inactive')}
                    </span>
                  )}
                </div>
                {list.description && <Text className={classes.text}>{list.description}</Text>}
                <Text size="sm" c="dimmed">
                  {t('admin.tagLists.usedOn', {
                    types: usedOn(list)
                      .map((term) => t(`terms.${term}`, { count: 2 }).toLocaleLowerCase())
                      .join(', '),
                  })}
                </Text>
                <Group gap="sm">
                  <Button
                    variant="default"
                    leftSection={<IconPencil size={18} aria-hidden />}
                    aria-label={t('admin.tagLists.editListLabel', { name: list.name })}
                    onClick={() => open({ kind: 'editList', list })}
                  >
                    {t('admin.tagLists.editList')}
                  </Button>
                  <Button
                    variant="default"
                    leftSection={
                      list.is_active ? (
                        <IconEyeOff size={18} aria-hidden />
                      ) : (
                        <IconEye size={18} aria-hidden />
                      )
                    }
                    aria-label={t(
                      list.is_active ? 'admin.tagLists.deactivateListLabel' : 'admin.tagLists.activateListLabel',
                      { name: list.name }
                    )}
                    loading={toggle.isPending && toggle.variables?.list.id === list.id && !toggle.variables.value}
                    onClick={() => toggle.mutate({ list })}
                  >
                    {t(list.is_active ? 'admin.tagLists.deactivate' : 'admin.tagLists.activate')}
                  </Button>
                  <Button
                    variant="default"
                    leftSection={<IconTrash size={18} aria-hidden />}
                    aria-label={t('admin.tagLists.deleteListLabel', { name: list.name })}
                    disabled={inUse}
                    onClick={() => open({ kind: 'delete', target: { kind: 'list', list } })}
                  >
                    {t('admin.tagLists.deleteList')}
                  </Button>
                </Group>
                {inUse && (
                  <Text size="sm" c="dimmed">
                    {t('admin.tagLists.listInUse')}
                  </Text>
                )}

                <Group justify="space-between" gap="sm" className={classes.valuesHead}>
                  <Title order={3} className={classes.valuesTitle}>
                    {t('admin.tagLists.tags')}
                  </Title>
                  <Button
                    variant="default"
                    leftSection={<IconPlus size={18} aria-hidden />}
                    aria-label={t('admin.tagLists.addTagTo', { list: list.name })}
                    onClick={() => open({ kind: 'addTag', list })}
                  >
                    {t('admin.tagLists.addTag')}
                  </Button>
                </Group>
                {list.values.length === 0 ? (
                  <Text c="dimmed">{t('admin.tagLists.noTags')}</Text>
                ) : (
                  <ul className={classes.values}>
                    {list.values.map((value) => (
                      <li key={value.id} className={classes.value}>
                        <div className={classes.valueText}>
                          <span className={classes.valueLabel}>{value.label}</span>
                          {value.code && <span className={classes.code}>{value.code}</span>}
                          {!value.is_active && (
                            <span className={classes.chip} data-tone="attention">
                              {t('admin.tagLists.inactive')}
                            </span>
                          )}
                          <span className={classes.usage}>
                            {value.usage_count > 0
                              ? t('admin.tagLists.usage', { count: value.usage_count })
                              : t('admin.tagLists.unused')}
                          </span>
                        </div>
                        <Group gap="sm">
                          <Button
                            variant="default"
                            leftSection={<IconPencil size={18} aria-hidden />}
                            aria-label={t('admin.tagLists.editTagLabel', { label: value.label })}
                            onClick={() => open({ kind: 'editTag', list, value })}
                          >
                            {t('admin.tagLists.editTag')}
                          </Button>
                          <Button
                            variant="default"
                            leftSection={
                              value.is_active ? (
                                <IconEyeOff size={18} aria-hidden />
                              ) : (
                                <IconEye size={18} aria-hidden />
                              )
                            }
                            aria-label={t(
                              value.is_active
                                ? 'admin.tagLists.deactivateTagLabel'
                                : 'admin.tagLists.activateTagLabel',
                              { label: value.label }
                            )}
                            loading={toggle.isPending && toggle.variables?.value?.id === value.id}
                            onClick={() => toggle.mutate({ list, value })}
                          >
                            {t(value.is_active ? 'admin.tagLists.deactivate' : 'admin.tagLists.activate')}
                          </Button>
                          <Button
                            variant="default"
                            leftSection={<IconTrash size={18} aria-hidden />}
                            aria-label={t('admin.tagLists.deleteTagLabel', { label: value.label })}
                            disabled={value.usage_count > 0}
                            onClick={() =>
                              open({ kind: 'delete', target: { kind: 'value', value, list } })
                            }
                          >
                            {t('admin.tagLists.deleteTag')}
                          </Button>
                        </Group>
                      </li>
                    ))}
                  </ul>
                )}
              </Paper>
            );
          })}
        </>
      )}

      <ListDialog opened={dialog?.kind === 'addList'} {...common} />
      {current?.kind === 'editList' && (
        <ListDialog opened={dialog?.kind === 'editList'} list={current.list} {...common} />
      )}
      {current?.kind === 'addTag' && (
        <ValueDialog opened={dialog?.kind === 'addTag'} list={current.list} {...common} />
      )}
      {current?.kind === 'editTag' && (
        <ValueDialog
          opened={dialog?.kind === 'editTag'}
          list={current.list}
          value={current.value}
          {...common}
        />
      )}
      {current?.kind === 'delete' && (
        <DeleteDialog opened={dialog?.kind === 'delete'} target={current.target} {...common} />
      )}
    </Page>
  );
}
