import { Button, Paper, Stack, Text, Title } from '@mantine/core';
import {
  IconChartDots3,
  IconClipboardCheck,
  IconClock,
  IconCopy,
  IconGrid4x4,
  IconListTree,
  IconScale,
  IconTable,
} from '@tabler/icons-react';
import type { TablerIcon } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, Route, Routes } from 'react-router';

import { useFeature } from '../institution/useInstitution';
import { Page } from '../ui/Page';
import { CoveragePage } from './CoveragePage';
import { GapsPage } from './GapsPage';
import { ReportPage } from './ReportPage';
import { ALL_REPORTS, reportPath } from './reportPages';
import classes from './Coverage.module.css';

export const COVERAGE_PATH = '/reports/coverage';
export const GAPS_PATH = '/reports/gaps';

const ICONS: Record<string, TablerIcon> = {
  coverage: IconGrid4x4,
  gaps: IconChartDots3,
  redundancy: IconCopy,
  traceability: IconListTree,
  formats: IconClock,
  relationship: IconTable,
  'role-balance': IconScale,
  assessments: IconClipboardCheck,
};

function ReportsHome() {
  const { t } = useTranslation();
  const roleBalance = useFeature('role_balance_report');
  const reports = ALL_REPORTS.filter((key) => key !== 'role-balance' || roleBalance);
  return (
    <Page title={t('nav.reports')} description={t('reports.intro')}>
      <Stack gap="md">
        {reports.map((key) => {
          const Icon = ICONS[key] ?? IconGrid4x4;
          return (
            <Paper
              key={key}
              withBorder
              className={classes.card}
              component="section"
              aria-labelledby={`r-${key}`}
            >
              <Title order={2} id={`r-${key}`} className={classes.title}>
                {t(`reports.pages.${key}.title`)}
              </Title>
              <Text c="dimmed">{t(`reports.pages.${key}.description`)}</Text>
              <div>
                <Button
                  component={Link}
                  to={reportPath(key)}
                  mt="sm"
                  leftSection={<Icon size={18} aria-hidden />}
                >
                  {t('reports.open')}
                </Button>
              </div>
            </Paper>
          );
        })}
      </Stack>
    </Page>
  );
}

/** The reports: the coverage and gap reports have their own pages; the others are tables built
 * on the server (`ReportPage`). */
export function ReportsSection() {
  return (
    <Routes>
      <Route index element={<ReportsHome />} />
      <Route path="coverage" element={<CoveragePage />} />
      <Route path="gaps" element={<GapsPage />} />
      <Route path=":key" element={<ReportPage />} />
      <Route path="*" element={<ReportsHome />} />
    </Routes>
  );
}
