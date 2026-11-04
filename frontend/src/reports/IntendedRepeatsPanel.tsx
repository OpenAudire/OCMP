import { Button, Group, NativeSelect, Paper, Table, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  addIntendedRepeat,
  fetchIntendedRepeats,
  queryKeys,
  removeIntendedRepeat,
} from '../api/endpoints';
import type { ReportDocument } from '../api/types';
import { SuccessNotice } from '../pages/SuccessNotice';
import classes from './Coverage.module.css';

/** Mark items of the "taught in many sessions" report as intentional (a spiral curriculum), and
 * list or remove the marks. Marking needs `curriculum.edit` at the programme: without it the panel
 * only lists. */
export function IntendedRepeatsPanel({
  versionId,
  frameworkId,
  report,
}: {
  versionId: string;
  frameworkId: string;
  report: ReportDocument;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const marks = useQuery({
    queryKey: queryKeys.intendedRepeats(versionId),
    queryFn: () => fetchIntendedRepeats(versionId),
  });
  const [code, setCode] = useState('');
  const [reason, setReason] = useState('');
  const [done, setDone] = useState<string | null>(null);

  // The items the report lists now (first column is the code, second the title).
  const listed = (report.sections[0]?.rows ?? []).map((row) => ({
    code: String(row[0]),
    label: `${row[0]} ${row[1] ?? ''}`.trim(),
  }));
  const chosen = code || listed[0]?.code || '';

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.intendedRepeats(versionId) });
    void queryClient.invalidateQueries({ queryKey: ['reports', 'document', versionId] });
  };
  const add = useMutation({
    mutationFn: () => addIntendedRepeat(versionId, { framework_id: frameworkId, code: chosen, reason }),
    onSuccess: () => {
      setDone(chosen);
      setCode('');
      setReason('');
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => removeIntendedRepeat(versionId, id),
    onSuccess: () => {
      setDone(null);
      refresh();
    },
  });

  if (!marks.data) return null;
  const canEdit = marks.data.can_edit;
  if (!canEdit && marks.data.marks.length === 0) return null;
  return (
    <Paper
      withBorder
      component="section"
      className={classes.card}
      aria-labelledby="intended-title"
    >
      <Title order={2} id="intended-title" className={classes.title}>
        {t('reports.intended.title')}
      </Title>
      <Text size="sm" c="dimmed">
        {t('reports.intended.intro')}
      </Text>
      {done && <SuccessNotice>{t('reports.intended.marked', { code: done })}</SuccessNotice>}
      {canEdit && listed.length > 0 && (
        <Group align="flex-end" mt="sm">
          <NativeSelect
            label={t('reports.intended.item')}
            value={chosen}
            onChange={(event) => setCode(event.currentTarget.value)}
            data={listed.map((i) => ({ value: i.code, label: i.label }))}
          />
          <TextInput
            label={t('reports.intended.reason')}
            value={reason}
            maxLength={500}
            onChange={(event) => setReason(event.currentTarget.value)}
          />
          <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!chosen}>
            {t('reports.intended.mark')}
          </Button>
        </Group>
      )}
      {canEdit && listed.length === 0 && (
        <Text mt="xs">{t('reports.intended.nothingToMark')}</Text>
      )}
      {(add.isError || remove.isError) && (
        <Text c="red" role="alert" mt="xs">
          {t('reports.intended.failed')}
        </Text>
      )}
      {marks.data.marks.length > 0 && (
        <Table mt="md">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('reports.intended.item')}</Table.Th>
              <Table.Th>{t('reports.intended.reason')}</Table.Th>
              {canEdit && <Table.Th>{t('reports.intended.action')}</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {marks.data.marks.map((mark) => (
              <Table.Tr key={mark.id}>
                <Table.Td>{`${mark.code} ${mark.title}`}</Table.Td>
                <Table.Td>{mark.reason || '–'}</Table.Td>
                {canEdit && (
                  <Table.Td>
                    <Button
                      variant="default"
                      size="xs"
                      onClick={() => remove.mutate(mark.id)}
                      loading={remove.isPending && remove.variables === mark.id}
                      aria-label={t('reports.intended.removeFor', { code: mark.code })}
                    >
                      {t('reports.intended.remove')}
                    </Button>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Paper>
  );
}
