import { useState } from 'react';
import { Button, Group, Text } from '@mantine/core';
import { IconPlus, IconX } from '@tabler/icons-react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { removeTagging } from '../api/endpoints';
import type { ItemTag, TaggableKind } from '../api/types';
import { editErrorMessage, useRefreshCurriculum, type EditResult } from './editing';
import { TagDialog } from './TagDialog';
import { sourceLabel } from './tagSources';
import classes from './ItemTags.module.css';

interface ItemTagsProps {
  kind: TaggableKind;
  itemId: string;
  /** What the buttons name: the module, the session, or an excerpt of the objective. */
  itemName: string;
  versionId: string;
  tags: ItemTag[] | undefined;
  canEdit: boolean;
  onSaved: (result: EditResult) => void;
}

/**
 * The tags of one item: each with its list, and for inherited ones the source in words.
 * Only direct tags can be removed (inherited ones are removed where they were set).
 */
export function ItemTags({ kind, itemId, itemName, versionId, tags, canEdit, onSaved }: ItemTagsProps) {
  const { t } = useTranslation();
  const refresh = useRefreshCurriculum(versionId);
  const [adding, setAdding] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: (tag: ItemTag) => removeTagging(tag.direct_tagging_id as string),
    onMutate: (tag) => {
      setFailure(null);
      setRemoving(tag.tag_value_id);
    },
    onSuccess: async (_data, tag) => {
      await refresh();
      // The Remove button is gone, so the confirmation takes focus.
      onSaved({ message: t('tags.removed', { tag: tag.label, name: itemName }), focus: true });
    },
    onError: (error) => setFailure(editErrorMessage(t, error)),
    onSettled: () => setRemoving(null),
  });
  const shown = tags ?? [];
  const direct = new Set(shown.filter((tag) => tag.direct_tagging_id).map((tag) => tag.tag_value_id));

  return (
    <div className={classes.tags} role="group" aria-label={t('tags.groupLabel', { name: itemName })}>
      <Group justify="space-between" gap="sm">
        <Text className={classes.heading}>{t('tags.title')}</Text>
        {canEdit && (
          <Button
            variant="default"
            leftSection={<IconPlus size={18} aria-hidden />}
            aria-label={t('tags.addTo', { name: itemName })}
            onClick={() => setAdding(true)}
          >
            {t('tags.add')}
          </Button>
        )}
      </Group>
      {failure && (
        <Text role="alert" size="sm" c="var(--cic-warm-ink)">
          {failure}
        </Text>
      )}
      {shown.length === 0 ? (
        <Text c="dimmed" size="sm">
          {t('tags.none')}
        </Text>
      ) : (
        <ul className={classes.list}>
          {shown.map((tag) => (
            <li key={tag.tag_value_id} className={classes.item}>
              <span className={classes.chip} data-inherited={tag.direct_tagging_id ? undefined : ''}>
                {tag.label}
              </span>
              <span className={classes.detail}>
                {tag.list_name}
                {tag.sources.length > 0 && (
                  <>
                    {' · '}
                    {tag.direct_tagging_id
                      ? t('tags.alsoInherited', {
                          sources: tag.sources.map((source) => sourceLabel(t, source)).join(', '),
                        })
                      : t('tags.inheritedFrom', {
                          sources: tag.sources.map((source) => sourceLabel(t, source)).join(', '),
                        })}
                  </>
                )}
              </span>
              {canEdit && tag.direct_tagging_id && (
                <Button
                  variant="default"
                  leftSection={<IconX size={18} aria-hidden />}
                  aria-label={t('tags.removeFrom', { tag: tag.label, name: itemName })}
                  loading={removing === tag.tag_value_id}
                  onClick={() => remove.mutate(tag)}
                >
                  {t('tags.remove')}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <TagDialog
          opened={adding}
          kind={kind}
          itemId={itemId}
          itemName={itemName}
          versionId={versionId}
          directValueIds={direct}
          onClose={() => setAdding(false)}
          onSaved={(result) => {
            setAdding(false);
            onSaved(result);
          }}
        />
      )}
    </div>
  );
}
