import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  FileInput,
  Group,
  Paper,
  Text,
  Title,
} from '@mantine/core';
import { IconAlertTriangle, IconFileImport } from '@tabler/icons-react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import {
  frameworkExcelTemplateUrl,
  importFrameworkPack,
  previewFrameworkPack,
} from '../api/endpoints';
import type { PackCounts, PackImportResult, PackPreview } from '../api/types';
import { SuccessNotice } from '../pages/SuccessNotice';
import { LoadingState } from '../ui/States';
import classes from './PackImport.module.css';

/** File size in words people read (the server enforces the real limit). */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function errorKey(error: unknown): string {
  if (isApiError(error, 413)) return 'tooLarge';
  if (isApiError(error, 429)) return 'tooMany';
  if (isApiError(error, 403)) return 'forbidden';
  if (isApiError(error, 404)) return 'expired';
  if (isApiError(error, 409) || isApiError(error, 422)) return 'invalid';
  return 'generic';
}

function Counts({ counts }: { counts: PackCounts }) {
  const { t } = useTranslation();
  const lines: string[] = [t('import.pack.count.items', { count: counts.items, levels: counts.levels })];
  if (counts.cross_references > 0) {
    let line = t('import.pack.count.crossReferences', { count: counts.cross_references });
    if (counts.external_references > 0) {
      line += `, ${t('import.pack.count.externalReferences', { count: counts.external_references })}`;
    }
    lines.push(line);
  }
  if (counts.crosswalks > 0) {
    lines.push(
      t('import.pack.count.crosswalks', { count: counts.crosswalks, entries: counts.crosswalk_entries })
    );
  }
  if (counts.taxonomy_scales > 0) {
    lines.push(t('import.pack.count.scales', { count: counts.taxonomy_scales }));
  }
  if (counts.tag_lists > 0) {
    lines.push(t('import.pack.count.tagLists', { count: counts.tag_lists, values: counts.tag_values }));
  }
  return (
    <ul className={classes.counts}>
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

function Problems({ preview }: { preview: PackPreview }) {
  const { t } = useTranslation();
  const name = preview.metadata?.name;
  return (
    <>
      <Alert color="red" title={t('import.pack.invalidTitle')} icon={<IconAlertTriangle aria-hidden />}>
        <Text size="sm">{t('import.pack.invalidBody', { count: preview.errors.length })}</Text>
        {preview.metadata && (
          <Text size="sm">
            {t('import.pack.invalidFor', { name, version: preview.metadata.version })}
          </Text>
        )}
      </Alert>
      <table className={classes.problems}>
        <thead>
          <tr>
            <th scope="col">{t('import.pack.where')}</th>
            <th scope="col">{t('import.pack.problem')}</th>
          </tr>
        </thead>
        <tbody>
          {preview.errors.map((problem, index) => (
            <tr key={index}>
              <td>
                {problem.path ? (
                  <code className={classes.path}>{problem.path}</code>
                ) : (
                  t('import.pack.wholeFile')
                )}
              </td>
              <td className={classes.message}>{problem.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Details({ preview }: { preview: PackPreview }) {
  const { t } = useTranslation();
  const meta = preview.metadata!;
  const rows: [string, string][] = [
    [t('import.pack.name'), meta.name],
    [t('import.pack.key'), meta.key],
    [t('import.pack.version'), meta.version],
    [t('import.pack.publisher'), meta.publisher],
    [t('import.pack.profile'), t(`import.pack.profiles.${meta.profile}`)],
    [t('import.pack.licence'), meta.licence || t('import.pack.noLicence')],
  ];
  if (meta.url) rows.push([t('import.pack.url'), meta.url]);
  return (
    <>
      <Title order={3} className={classes.subtitle}>
        {t('import.pack.details')}
      </Title>
      <dl className={classes.details}>
        {rows.map(([label, value]) => (
          <div key={label} className={classes.detailRow}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function ItemSample({ preview }: { preview: PackPreview }) {
  const { t } = useTranslation();
  const total = preview.counts?.items ?? preview.sample.length;
  return (
    <>
      <Title order={3} className={classes.subtitle}>
        {t('import.pack.itemsTitle')}
      </Title>
      <Text size="sm" c="dimmed">
        {preview.sample_truncated
          ? t('import.pack.itemsShown', { shown: preview.sample.length, total })
          : t('import.pack.itemsAll', { total })}
      </Text>
      <div
        className={classes.sample}
        role="region"
        aria-label={t('import.pack.itemsRegion')}
        tabIndex={0}
      >
        <ul className={classes.tree}>
          {preview.sample.map((item) => (
            <li key={item.code} style={{ paddingInlineStart: `${item.depth * 20}px` }}>
              <code className={classes.code}>{item.code}</code> {item.title}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

function ImportDone({ result, onAnother }: { result: PackImportResult; onAnother: () => void }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const facts = [t('import.pack.doneItems', { count: result.items })];
  if (result.crosswalks > 0) {
    facts.push(
      t('import.pack.doneCrosswalks', { count: result.crosswalks, entries: result.crosswalk_entries })
    );
  }
  if (result.tag_lists_created > 0 || result.tag_values_added > 0) {
    facts.push(
      t('import.pack.doneTags', { lists: result.tag_lists_created, values: result.tag_values_added })
    );
  }
  if (result.superseded_versions > 0) {
    facts.push(t('import.pack.doneSuperseded', { count: result.superseded_versions }));
  }
  return (
    <>
      <div ref={ref} tabIndex={-1} className={classes.focusable}>
        <SuccessNotice>
          <strong>{t('import.pack.doneTitle', { name: result.name })}</strong>{' '}
          {t('import.pack.doneBody', {
            name: result.name,
            version: result.version,
            status: t(`import.pack.status.${result.status}`),
          })}
        </SuccessNotice>
      </div>
      <ul className={classes.counts}>
        {facts.map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>
      <div>
        <Button variant="default" onClick={onAnother}>
          {t('import.pack.importAnother')}
        </Button>
      </div>
    </>
  );
}

/** Upload a framework pack, read the checks, confirm (nothing is saved before that). */
export function PackImportCard() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [activate, setActivate] = useState(false);

  const check = useMutation({ mutationFn: previewFrameworkPack });
  const run = useMutation({
    mutationFn: (token: string) => importFrameworkPack(token, activate),
  });

  const reset = () => {
    setFile(null);
    setActivate(false);
    check.reset();
    run.reset();
  };

  const preview = check.data;
  const title = t('import.pack.title');

  let body;
  if (run.isSuccess) {
    body = <ImportDone result={run.data} onAnother={reset} />;
  } else if (run.isPending) {
    body = (
      <LoadingState
        title={t('import.pack.importing', { name: preview?.metadata?.name })}
        note={t('import.pack.importingNote')}
        skeletons={1}
      />
    );
  } else if (check.isPending) {
    body = (
      <LoadingState
        title={t('import.pack.checking', {
          name: file?.name ?? '',
          size: formatSize(file?.size ?? 0),
        })}
        note={t('import.pack.checkingNote')}
        skeletons={1}
      />
    );
  } else if (preview && !preview.valid) {
    body = (
      <>
        <Problems preview={preview} />
        <div>
          <Button variant="default" onClick={reset}>
            {t('import.pack.chooseAnother')}
          </Button>
        </div>
      </>
    );
  } else if (preview?.valid && preview.metadata && preview.counts) {
    const meta = preview.metadata;
    body = (
      <>
        <Title order={3}>{t('import.pack.validTitle')}</Title>
        <Text c="dimmed">
          {t('import.pack.validBody', { name: meta.name, version: meta.version })}
        </Text>
        <Details preview={preview} />
        <Title order={3} className={classes.subtitle}>
          {t('import.pack.contents')}
        </Title>
        <Counts counts={preview.counts} />
        {preview.warnings.length > 0 && (
          <div className={classes.note} data-tone="attention">
            <Text fw={600} size="sm">
              <IconAlertTriangle size={16} aria-hidden className={classes.noteIcon} />
              {t('import.pack.notes')}
            </Text>
            <ul className={classes.noteList}>
              {preview.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        <ItemSample preview={preview} />
        <Checkbox
          checked={activate}
          onChange={(event) => setActivate(event.currentTarget.checked)}
          label={t('import.pack.activate', { name: meta.name })}
          description={t('import.pack.activateHint')}
        />
        {run.isError && <Alert color="red">{t(`import.pack.errors.${errorKey(run.error)}`)}</Alert>}
        <Group>
          <Button onClick={() => preview.token && run.mutate(preview.token)}>
            {t('import.pack.import')}
          </Button>
          <Button variant="default" onClick={reset}>
            {t('import.pack.chooseAnother')}
          </Button>
        </Group>
      </>
    );
  } else {
    body = (
      <form
        className={classes.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (file) check.mutate(file);
        }}
      >
        <Text c="dimmed">{t('import.pack.description')}</Text>
        <Anchor href={frameworkExcelTemplateUrl()} download>
          {t('import.pack.excelTemplate')}
        </Anchor>
        <FileInput
          label={t('import.pack.fileLabel')}
          description={t('import.pack.fileHint')}
          placeholder={t('import.pack.filePlaceholder')}
          accept=".json,application/json,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          value={file}
          onChange={setFile}
          leftSection={<IconFileImport size={18} aria-hidden />}
          clearable
        />
        {check.isError && (
          <Alert color="red">{t(`import.pack.errors.${errorKey(check.error)}`)}</Alert>
        )}
        <div>
          <Button type="submit" disabled={!file}>
            {t('import.pack.check')}
          </Button>
        </div>
      </form>
    );
  }

  return (
    <Paper withBorder className={classes.card}>
      <Title order={2}>{title}</Title>
      {body}
    </Paper>
  );
}
