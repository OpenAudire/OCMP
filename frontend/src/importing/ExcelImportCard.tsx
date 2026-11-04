import { useState } from 'react';
import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  FileInput,
  Group,
  NativeSelect,
  Paper,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconAlertTriangle, IconDownload, IconFileImport } from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import type { CurriculumImportApplied, CurriculumImportPreview } from '../api/types';
import { useProgrammes } from '../curriculum/currentVersion';
import { versionLabel } from '../curriculum/versions';
import { SuccessNotice } from '../pages/SuccessNotice';
import { LoadingState } from '../ui/States';
import classes from './PackImport.module.css';

const ACTIONS = ['create', 'update', 'unchanged'] as const;

export interface ExcelImportKind {
  /** Names the texts under `import.kinds.<kind>` and the card's heading id. */
  kind: 'curriculum' | 'tags' | 'mappings';
  /** The sheets, in order (their texts are `import.sheets.<key>`). */
  sheets: readonly string[];
  /** Whether the import goes into a draft curriculum version (the user chooses one). */
  needsVersion: boolean;
  templateUrl: (versionId: string) => string;
  preview: (versionId: string, file: File) => Promise<CurriculumImportPreview>;
  apply: (versionId: string, token: string, decided: boolean) => Promise<CurriculumImportApplied>;
  /** Offer "these were already reviewed elsewhere" (mappings, for people who may review). */
  canDecide?: boolean;
}

function errorKey(error: unknown): string {
  if (isApiError(error, 413)) return 'tooLarge';
  if (isApiError(error, 429)) return 'tooMany';
  if (isApiError(error, 403) || isApiError(error, 404)) return 'forbidden';
  if (isApiError(error, 409)) return 'conflict';
  if (isApiError(error, 422)) return 'expired';
  return 'generic';
}

function CountsTable({
  counts,
  sheets,
}: {
  counts: CurriculumImportPreview['counts'];
  sheets: readonly string[];
}) {
  const { t } = useTranslation();
  return (
    <Table>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>{t('import.curriculum.sheet')}</Table.Th>
          {ACTIONS.map((a) => (
            <Table.Th key={a}>{t(`import.curriculum.action.${a}`)}</Table.Th>
          ))}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {sheets
          .filter((s) => ACTIONS.some((a) => (counts[s]?.[a] ?? 0) > 0))
          .map((s) => (
            <Table.Tr key={s}>
              <Table.Td>{t(`import.sheets.${s}`)}</Table.Td>
              {ACTIONS.map((a) => (
                <Table.Td key={a}>{counts[s]?.[a] ?? 0}</Table.Td>
              ))}
            </Table.Tr>
          ))}
      </Table.Tbody>
    </Table>
  );
}

/** An Excel import: choose (a version and) a file, check it (nothing is written), read what would
 * happen row by row, then confirm. Used for the curriculum, tags and mappings. */
export function ExcelImportCard({ config }: { config: ExcelImportKind }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const programmes = useProgrammes();
  const drafts = (programmes.data ?? []).flatMap((p) =>
    p.versions
      .filter((v) => v.status === 'draft')
      .map((v) => ({ value: v.id, label: `${p.code} · ${versionLabel(t, v)}` }))
  );
  const [versionId, setVersionId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const chosen = config.needsVersion ? versionId || drafts[0]?.value || '' : '';
  const [preview, setPreview] = useState<CurriculumImportPreview | null>(null);
  const [done, setDone] = useState<CurriculumImportApplied | null>(null);
  const [decided, setDecided] = useState(false);
  const base = `import.kinds.${config.kind}`;

  const check = useMutation({
    mutationFn: () => config.preview(chosen, file as File),
    onSuccess: (result) => {
      setPreview(result);
      setDone(null);
    },
  });
  const apply = useMutation({
    mutationFn: () => config.apply(chosen, preview?.token as string, decided),
    onSuccess: (result) => {
      setDone(result);
      setPreview(null);
      setFile(null);
      setDecided(false);
      void queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
    },
  });
  const failure = check.error ?? apply.error;
  const created = config.sheets.reduce((n, s) => n + (done?.counts[s]?.create ?? 0), 0);
  const updated = config.sheets.reduce((n, s) => n + (done?.counts[s]?.update ?? 0), 0);
  const waiting = config.needsVersion && drafts.length === 0;

  const reset = () => {
    setPreview(null);
    setDone(null);
  };

  return (
    <Paper
      withBorder
      className={classes.card}
      component="section"
      aria-labelledby={`import-${config.kind}`}
    >
      <Title order={2} id={`import-${config.kind}`}>
        {t(`${base}.title`)}
      </Title>
      <Text c="dimmed">{t(`${base}.intro`)}</Text>
      {config.needsVersion && programmes.isLoading && <LoadingState />}
      {config.needsVersion && programmes.isSuccess && waiting && (
        <Text>{t('import.curriculum.noDraft')}</Text>
      )}
      {!waiting && (
        <div className={classes.form}>
          {config.needsVersion && (
            <NativeSelect
              label={t('import.curriculum.version')}
              value={chosen}
              onChange={(event) => {
                setVersionId(event.currentTarget.value);
                reset();
              }}
              data={drafts}
            />
          )}
          <Anchor href={config.templateUrl(chosen)} download>
            <IconDownload size={16} aria-hidden /> {t(`${base}.template`)}
          </Anchor>
          <FileInput
            label={t('import.curriculum.file')}
            description={t('import.curriculum.fileHelp')}
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            value={file}
            onChange={(f) => {
              setFile(f);
              reset();
            }}
          />
          <Group>
            <Button
              leftSection={<IconFileImport size={18} aria-hidden />}
              disabled={!file}
              loading={check.isPending}
              onClick={() => check.mutate()}
            >
              {t('import.curriculum.check')}
            </Button>
          </Group>
        </div>
      )}
      {failure && (
        <Alert color="red" role="alert">
          {t(`import.curriculum.errors.${errorKey(failure)}`)}
        </Alert>
      )}
      {done && (
        <SuccessNotice>{t('import.curriculum.done', { created, updated })}</SuccessNotice>
      )}
      {preview && !preview.valid && (
        <>
          <Alert
            color="red"
            title={t('import.curriculum.invalidTitle')}
            icon={<IconAlertTriangle aria-hidden />}
          >
            {t('import.curriculum.invalidBody', {
              count: preview.problems.length + preview.more_problems,
            })}
          </Alert>
          <table className={classes.problems}>
            <thead>
              <tr>
                <th scope="col">{t('import.curriculum.sheet')}</th>
                <th scope="col">{t('import.curriculum.row')}</th>
                <th scope="col">{t('import.curriculum.column')}</th>
                <th scope="col">{t('import.pack.problem')}</th>
              </tr>
            </thead>
            <tbody>
              {preview.problems.map((p, index) => (
                <tr key={index}>
                  <td>{p.sheet ?? t('import.pack.wholeFile')}</td>
                  <td>{p.row ?? '–'}</td>
                  <td>{p.column ?? '–'}</td>
                  <td className={classes.message}>{p.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.more_problems > 0 && (
            <Text size="sm">
              {t('import.curriculum.moreProblems', { count: preview.more_problems })}
            </Text>
          )}
        </>
      )}
      {preview && preview.warnings.length > 0 && (
        <Alert color="ochre" variant="light" title={t('import.curriculum.warnings')}>
          <ul>
            {preview.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      )}
      {preview && preview.valid && (
        <>
          <Title order={3} className={classes.subtitle}>
            {t('import.curriculum.previewTitle')}
          </Title>
          <Text size="sm" c="dimmed">
            {preview.would_change
              ? t('import.curriculum.previewBody')
              : t('import.curriculum.nothingToDo')}
          </Text>
          <CountsTable counts={preview.counts} sheets={config.sheets} />
          <div
            className={classes.sample}
            role="region"
            aria-label={t('import.curriculum.rowsRegion')}
            tabIndex={0}
          >
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('import.curriculum.sheet')}</Table.Th>
                  <Table.Th>{t('import.curriculum.row')}</Table.Th>
                  <Table.Th>{t('import.curriculum.externalId')}</Table.Th>
                  <Table.Th>{t('import.curriculum.what')}</Table.Th>
                  <Table.Th>{t('import.curriculum.change')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {preview.rows.map((r) => (
                  <Table.Tr key={`${r.sheet}-${r.row}`}>
                    <Table.Td>{t(`import.sheets.${r.sheet}`)}</Table.Td>
                    <Table.Td>{r.row}</Table.Td>
                    <Table.Td>
                      <code className={classes.code}>{r.external_id}</code>
                    </Table.Td>
                    <Table.Td>{r.label}</Table.Td>
                    <Table.Td>
                      {t(`import.curriculum.action.${r.action}`)}
                      {r.changes.length > 0 && ` (${r.changes.join(', ')})`}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </div>
          {preview.more_rows > 0 && (
            <Text size="sm">{t('import.curriculum.moreRows', { count: preview.more_rows })}</Text>
          )}
          {config.canDecide && preview.would_change && (
            <Checkbox
              checked={decided}
              onChange={(event) => setDecided(event.currentTarget.checked)}
              label={t('import.kinds.mappings.decided')}
              description={t('import.kinds.mappings.decidedHelp')}
            />
          )}
          <Group>
            <Button
              disabled={!preview.would_change}
              loading={apply.isPending}
              onClick={() => apply.mutate()}
            >
              {t(`${base}.apply`)}
            </Button>
          </Group>
        </>
      )}
    </Paper>
  );
}
