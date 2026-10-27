import type { FormEvent } from 'react';
import { Text } from '@mantine/core';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { deleteFramework, queryKeys } from '../api/endpoints';
import type { FrameworkSummary } from '../api/types';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';

interface DeleteFrameworkDialogProps {
  framework: FrameworkSummary;
  onClose: () => void;
  onDeleted: (framework: FrameworkSummary) => void;
}

function errorText(t: (key: string) => string, error: unknown): string {
  if (isApiError(error, 409)) return t('frameworks.delete.inUse');
  if (isApiError(error, 403)) return t('frameworks.delete.forbidden');
  if (isApiError(error, 404)) return t('frameworks.delete.gone');
  return t('frameworks.delete.generic');
}

/**
 * Confirm deleting one unused framework version. The server refuses (409) while objectives
 * are mapped to it, a review is assigned on it or a newer version builds on it (ADR 037).
 */
export function DeleteFrameworkDialog({
  framework,
  onClose,
  onDeleted,
}: DeleteFrameworkDialogProps) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const run = useMutation({
    mutationFn: () => deleteFramework(framework.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.frameworks });
      onDeleted(framework);
    },
  });
  const names = { name: framework.name, version: framework.version_label };
  return (
    <EditDialog opened onClose={onClose} title={t('frameworks.delete.title', names)}>
      <DialogForm
        submitLabel={t('frameworks.delete.submit')}
        error={run.isError ? errorText(t, run.error) : null}
        busy={run.isPending}
        danger
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          run.mutate();
        }}
        onClose={onClose}
      >
        <Text>{t('frameworks.delete.body')}</Text>
      </DialogForm>
    </EditDialog>
  );
}
