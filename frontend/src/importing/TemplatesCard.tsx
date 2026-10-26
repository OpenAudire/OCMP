import { Anchor, Paper, Text, Title } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { fetchPackTemplates, packTemplateUrl, queryKeys } from '../api/endpoints';
import classes from './PackImport.module.css';

/** The blank, structure-only templates (placeholders, never official text). */
export function TemplatesCard() {
  const { t } = useTranslation();
  const templates = useQuery({ queryKey: queryKeys.packTemplates, queryFn: fetchPackTemplates });
  return (
    <Paper withBorder className={classes.card}>
      <Title order={2}>{t('import.templates.title')}</Title>
      <Text c="dimmed">{t('import.templates.description')}</Text>
      {templates.isError && <Text role="alert">{t('import.templates.loadError')}</Text>}
      {templates.isSuccess && templates.data.length === 0 && (
        <Text>{t('import.templates.empty')}</Text>
      )}
      {templates.isSuccess && templates.data.length > 0 && (
        <ul className={classes.templates}>
          {templates.data.map((template) => (
            <li key={template.name} className={classes.template}>
              <div>
                <Text fw={600}>{template.title}</Text>
                <Text size="sm" c="dimmed">
                  {t('import.templates.itemCount', { count: template.items })}
                </Text>
              </div>
              <Anchor
                href={packTemplateUrl(template.name)}
                download={`${template.name}.json`}
                className={classes.download}
                aria-label={t('import.templates.download', { title: template.title })}
              >
                <IconDownload size={18} aria-hidden />
                <span aria-hidden>{t('import.templates.downloadShort')}</span>
              </Anchor>
            </li>
          ))}
        </ul>
      )}
    </Paper>
  );
}
