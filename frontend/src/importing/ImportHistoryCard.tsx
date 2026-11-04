import { Paper, Table, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { fetchImportJobs } from '../api/endpoints';
import type { ImportJob } from '../api/types';
import { formatMade } from '../reports/coverageFormat';
import { ErrorState, LoadingState } from '../ui/States';
import classes from './PackImport.module.css';

/** The number of rows of every sheet of a job that were created or updated. */
function total(job: ImportJob, action: 'create' | 'update'): number {
  return Object.values(job.counts).reduce((n, c) => n + (c[action] ?? 0), 0);
}

/** The applied imports (yours, or everyone's if you may read the audit log). Counts only. */
export function ImportHistoryCard() {
  const { t, i18n } = useTranslation();
  const jobs = useQuery({ queryKey: ['import-jobs'], queryFn: fetchImportJobs });
  return (
    <Paper withBorder className={classes.card} component="section" aria-labelledby="import-history">
      <Title order={2} id="import-history">
        {t('import.history.title')}
      </Title>
      <Text c="dimmed">{t('import.history.intro')}</Text>
      {jobs.isLoading && <LoadingState />}
      {jobs.isError && (
        <ErrorState title={t('import.history.errorTitle')} body={t('import.history.errorBody')} />
      )}
      {jobs.isSuccess && jobs.data.length === 0 && <Text>{t('import.history.none')}</Text>}
      {jobs.isSuccess && jobs.data.length > 0 && (
        <Table.ScrollContainer minWidth={560}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('import.history.when')}</Table.Th>
                <Table.Th>{t('import.history.what')}</Table.Th>
                <Table.Th>{t('import.history.version')}</Table.Th>
                <Table.Th>{t('import.history.by')}</Table.Th>
                <Table.Th>{t('import.history.result')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {jobs.data.map((job) => (
                <Table.Tr key={job.id}>
                  <Table.Td>{formatMade(job.created_at, i18n.language)}</Table.Td>
                  <Table.Td>{t(`import.history.kinds.${job.kind}`)}</Table.Td>
                  <Table.Td>
                    {job.programme_code ? `${job.programme_code} ${job.academic_year}` : '–'}
                  </Table.Td>
                  <Table.Td>{job.by ?? '–'}</Table.Td>
                  <Table.Td>{t('import.history.counts', { created: total(job, 'create'), updated: total(job, 'update') })}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Paper>
  );
}
