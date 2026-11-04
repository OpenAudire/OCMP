import { NativeSelect, Stack, Text } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { fetchFrameworkLibrary, queryKeys } from '../api/endpoints';
import { useProgrammes } from '../curriculum/currentVersion';
import { versionLabel } from '../curriculum/versions';
import classes from './Coverage.module.css';
import { METHODS, type Choice } from './useChoice';

/** The three choices that make a report: version, framework and method (with its definition). */
export function CoverageControls({
  choice,
  definition,
}: {
  choice: Choice & { set: (changes: Record<string, string>) => void };
  definition?: string;
}) {
  const { t } = useTranslation();
  const programmes = useProgrammes();
  const library = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });
  const versions = (programmes.data ?? []).flatMap((p) =>
    p.versions.map((v) => ({ value: v.id, label: `${p.code} · ${versionLabel(t, v)}` }))
  );
  const frameworks = (library.data?.frameworks ?? [])
    .filter((f) => f.status !== 'draft')
    .map((f) => ({ value: f.id, label: `${f.name} (${f.version_label})` }));
  return (
    <div className={classes.controls}>
      <NativeSelect
        label={t('reports.coverage.version')}
        value={choice.versionId ?? ''}
        onChange={(event) => choice.set({ version: event.currentTarget.value })}
        data={versions}
      />
      <NativeSelect
        label={t('reports.coverage.framework')}
        value={choice.frameworkId ?? ''}
        onChange={(event) => choice.set({ framework: event.currentTarget.value })}
        data={frameworks}
      />
      <Stack gap={4}>
        <NativeSelect
          label={t('reports.coverage.method')}
          value={choice.method}
          onChange={(event) => choice.set({ method: event.currentTarget.value })}
          data={METHODS.map((m) => ({ value: m, label: t(`reports.methods.${m}`) }))}
        />
        {definition && (
          <Text size="sm" c="dimmed">
            {definition}
          </Text>
        )}
      </Stack>
    </div>
  );
}
