import { Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { fetchPassOnPreview, passTagOn, queryKeys } from '../api/endpoints';
import { LoadingState } from '../ui/States';
import { DialogForm, EditDialog } from './EditDialog';
import { editErrorMessage, useRefreshCurriculum, type EditResult } from './editing';
import { PreviewItems } from './TagDialog';
import classes from './TagDialog.module.css';

interface PassOnDialogProps {
  opened: boolean;
  taggingId: string;
  tagLabel: string;
  itemName: string;
  versionId: string;
  onClose: () => void;
  onSaved: (result: EditResult) => void;
}

function PassOnForm({
  taggingId,
  tagLabel,
  itemName,
  versionId,
  onClose,
  onSaved,
}: Omit<PassOnDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const refresh = useRefreshCurriculum(versionId);
  const preview = useQuery({
    queryKey: queryKeys.passOnPreview(taggingId),
    queryFn: () => fetchPassOnPreview(taggingId),
    // The preview must match what saving will do, so never reuse an old one.
    staleTime: 0,
    gcTime: 0,
  });
  const reached = (preview.data?.items ?? []).filter((item) => item.status === 'new');

  const mutation = useMutation({
    mutationFn: () => passTagOn(taggingId),
    onSuccess: async (applied) => {
      await refresh();
      await client.invalidateQueries({ queryKey: ['tag-preview'] });
      onSaved({
        message: t('tags.passOn.done', {
          tag: tagLabel,
          name: itemName,
          count: applied.inherited_count,
        }),
        focus: true,
      });
    },
  });

  return (
    <DialogForm
      submitLabel={t('tags.passOn.save', { count: reached.length })}
      error={mutation.isError ? editErrorMessage(t, mutation.error) : null}
      busy={mutation.isPending}
      onSubmit={(event) => {
        event.preventDefault();
        if (reached.length > 0) mutation.mutate();
      }}
      onClose={onClose}
    >
      <Text>{t('tags.passOn.intro', { tag: tagLabel, name: itemName })}</Text>
      <div className={classes.preview} aria-live="polite">
        {preview.isPending ? (
          <LoadingState skeletons={1} />
        ) : preview.isError ? (
          <Text role="alert" size="sm">
            {t('tags.preview.error')}
          </Text>
        ) : preview.data.items.length === 0 || reached.length === 0 ? (
          <Text size="sm" c="dimmed">
            {t('tags.passOn.nothing')}
          </Text>
        ) : (
          <PreviewItems items={preview.data.items} />
        )}
      </div>
    </DialogForm>
  );
}

/** Previews the newer items a direct tag has not reached, then gives them the tag. */
export function PassOnDialog({ opened, ...props }: PassOnDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('tags.passOn.title', { tag: props.tagLabel, name: props.itemName })}
    >
      <PassOnForm {...props} />
    </EditDialog>
  );
}
