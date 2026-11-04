import { useState } from 'react';
import { Anchor, NativeSelect, Paper, Stack, Text, Title } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  fetchFrameworkLibrary,
  queryKeys,
  versionExportUrl,
} from '../api/endpoints';
import { defaultVersionId, rememberedVersion, useProgrammes } from '../curriculum/currentVersion';
import { versionLabel } from '../curriculum/versions';
import classes from './PackImport.module.css';

/** Exports of a curriculum version: the whole version as Excel (importable again), objectives by
 * framework items, and JSON. They contain only what the person may see. */
export function ExportCard() {
  const { t } = useTranslation();
  const programmes = useProgrammes();
  const library = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });
  const versions = (programmes.data ?? []).flatMap((p) =>
    p.versions.map((v) => ({ value: v.id, label: `${p.code} · ${versionLabel(t, v)}` }))
  );
  const [versionId, setVersionId] = useState('');
  const [frameworkId, setFrameworkId] = useState('');
  const chosen =
    versionId ||
    (programmes.data ? (defaultVersionId(programmes.data, rememberedVersion()) ?? '') : '');
  const frameworks = (library.data?.frameworks ?? []).filter((f) => f.status !== 'draft');
  const framework = frameworkId || frameworks[0]?.id || '';
  return (
    <Paper withBorder className={classes.card} component="section" aria-labelledby="export-card">
      <Title order={2} id="export-card">
        {t('import.export.title')}
      </Title>
      <Text c="dimmed">{t('import.export.intro')}</Text>
      {versions.length === 0 ? (
        <Text>{t('import.export.none')}</Text>
      ) : (
        <div className={classes.form}>
          <NativeSelect
            label={t('import.curriculum.version')}
            value={chosen}
            onChange={(event) => setVersionId(event.currentTarget.value)}
            data={versions}
          />
          <NativeSelect
            label={t('import.export.framework')}
            value={framework}
            onChange={(event) => setFrameworkId(event.currentTarget.value)}
            data={frameworks.map((f) => ({ value: f.id, label: `${f.name} (${f.version_label})` }))}
          />
          <Stack gap="xs">
            <Anchor href={versionExportUrl(chosen, 'workbook')} download>
              <IconDownload size={16} aria-hidden /> {t('import.export.workbook')}
            </Anchor>
            <Text size="sm" c="dimmed">
              {t('import.export.workbookHelp')}
            </Text>
            {framework && (
              <Anchor href={versionExportUrl(chosen, 'matrix', { framework_id: framework })} download>
                <IconDownload size={16} aria-hidden /> {t('import.export.matrix')}
              </Anchor>
            )}
            <Text size="sm" c="dimmed">
              {t('import.export.matrixHelp')}
            </Text>
            <Anchor href={versionExportUrl(chosen, 'json')} download>
              <IconDownload size={16} aria-hidden /> {t('import.export.json')}
            </Anchor>
            <Text size="sm" c="dimmed">
              {t('import.export.jsonHelp')}
            </Text>
          </Stack>
        </div>
      )}
    </Paper>
  );
}
