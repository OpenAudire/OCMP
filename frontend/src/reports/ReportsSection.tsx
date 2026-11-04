import { Button, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconChartDots3, IconGrid4x4 } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, Route, Routes } from 'react-router';

import { Page } from '../ui/Page';
import { CoveragePage } from './CoveragePage';
import { GapsPage } from './GapsPage';
import classes from './Coverage.module.css';

export const COVERAGE_PATH = '/reports/coverage';
export const GAPS_PATH = '/reports/gaps';

function ReportsHome() {
  const { t } = useTranslation();
  return (
    <Page title={t('nav.reports')} description={t('reports.intro')}>
      <Stack gap="md">
        <Paper withBorder className={classes.card} component="section" aria-labelledby="r-coverage">
          <Title order={2} id="r-coverage" className={classes.title}>
            {t('reports.coverage.title')}
          </Title>
          <Text c="dimmed">{t('reports.coverage.description')}</Text>
          <Group mt="sm">
            <Button
              component={Link}
              to={COVERAGE_PATH}
              leftSection={<IconGrid4x4 size={18} aria-hidden />}
            >
              {t('reports.open')}
            </Button>
          </Group>
        </Paper>
        <Paper withBorder className={classes.card} component="section" aria-labelledby="r-gaps">
          <Title order={2} id="r-gaps" className={classes.title}>
            {t('reports.gaps.title')}
          </Title>
          <Text c="dimmed">{t('reports.gaps.description')}</Text>
          <Group mt="sm">
            <Button
              component={Link}
              to={GAPS_PATH}
              leftSection={<IconChartDots3 size={18} aria-hidden />}
            >
              {t('reports.open')}
            </Button>
          </Group>
        </Paper>
      </Stack>
    </Page>
  );
}

/** The reports (Slice 1.21 builds the coverage and gap reports; the others follow). */
export function ReportsSection() {
  return (
    <Routes>
      <Route index element={<ReportsHome />} />
      <Route path="coverage" element={<CoveragePage />} />
      <Route path="gaps" element={<GapsPage />} />
      <Route path="*" element={<ReportsHome />} />
    </Routes>
  );
}
