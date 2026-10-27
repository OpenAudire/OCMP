import { useState, type FormEvent } from 'react';
import { NativeSelect, Text } from '@mantine/core';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { bulkAcceptReview } from '../api/endpoints';
import type { BulkAcceptRequest, BulkAcceptResult } from '../api/types';
import { DialogForm, EditDialog } from '../curriculum/EditDialog';
import { editErrorMessage } from '../curriculum/editing';

const THRESHOLDS = [0.8, 0.85, 0.9, 0.95];

interface BulkAcceptDialogProps {
  /** What the queue is narrowed to; "accept all" never goes beyond it. */
  scope: Pick<BulkAcceptRequest, 'version_id' | 'framework_id' | 'module_id'>;
  fourEyes: boolean;
  minConfidence: number;
  maxLinks: number;
  initial: number;
  onClose: () => void;
  onDone: (result: BulkAcceptResult, percent: number) => void;
}

function BulkForm({
  scope,
  fourEyes,
  minConfidence,
  maxLinks,
  initial,
  onClose,
  onDone,
}: BulkAcceptDialogProps) {
  const { t } = useTranslation();
  const choices = THRESHOLDS.filter((value) => value >= minConfidence);
  const [threshold, setThreshold] = useState(String(choices.includes(initial) ? initial : choices[0]));
  const percent = Math.round(Number(threshold) * 100);

  // Counting changes nothing: the person sees how many links will be accepted first.
  const preview = useQuery({
    queryKey: ['review-queue', 'bulk-preview', threshold, scope],
    queryFn: () => bulkAcceptReview({ ...scope, min_confidence: Number(threshold), dry_run: true }),
    staleTime: 0,
  });
  const mutation = useMutation({
    mutationFn: () => bulkAcceptReview({ ...scope, min_confidence: Number(threshold), dry_run: false }),
    onSuccess: (result) => onDone(result, percent),
  });

  const eligible = preview.data?.eligible ?? 0;
  const handled = Math.min(eligible, maxLinks);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (handled > 0) mutation.mutate();
  };

  return (
    <DialogForm
      submitLabel={t('review.bulk.submit', { count: handled })}
      error={mutation.isError ? editErrorMessage(t, mutation.error) : null}
      busy={mutation.isPending}
      onSubmit={handled > 0 ? submit : undefined}
      onClose={onClose}
    >
      <Text>{t('review.bulk.body', { max: maxLinks })}</Text>
      <NativeSelect
        label={t('review.bulk.threshold')}
        value={threshold}
        onChange={(event) => setThreshold(event.currentTarget.value)}
        data={choices.map((value) => ({
          value: String(value),
          label: t('review.bulk.option', { percent: Math.round(value * 100) }),
        }))}
      />
      <Text role="status" fw={600}>
        {preview.isPending && t('review.bulk.counting')}
        {preview.isError && t('review.bulk.countFailed')}
        {preview.data &&
          (eligible === 0
            ? t('review.bulk.none', { percent })
            : t('review.bulk.count', { count: handled, percent }))}
      </Text>
      {eligible > maxLinks && (
        <Text size="sm" c="dimmed">
          {t('review.bulk.more', { count: eligible - maxLinks })}
        </Text>
      )}
      <Text size="sm" c="dimmed">
        {t(fourEyes ? 'review.bulk.fourEyes' : 'review.bulk.effect')}
      </Text>
      <Text size="sm" c="dimmed">
        {t('review.bulk.rules')}
      </Text>
    </DialogForm>
  );
}

/** "Accept all N and above": counts first, explains the rules, then accepts one batch. */
export function BulkAcceptDialog(props: BulkAcceptDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog opened title={t('review.bulk.title')} onClose={props.onClose}>
      <BulkForm {...props} />
    </EditDialog>
  );
}
