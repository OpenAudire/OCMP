import { Anchor, Group, Text } from '@mantine/core';
import { IconFileSpreadsheet, IconFileTypePdf } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { reportExportUrl } from '../api/endpoints';
import type { CoverageMethod } from '../api/types';
import classes from './Coverage.module.css';

/** The two download links of a report; `href` gives the address for a format. */
export function ExportLinksFor({ href }: { href: (format: 'xlsx' | 'pdf') => string }) {
  const { t } = useTranslation();
  return (
    <div className={classes.exports}>
      <Group gap="lg">
        <Anchor href={href('xlsx')} download className={classes.exportLink}>
          <IconFileSpreadsheet size={18} aria-hidden /> {t('reports.export.excel')}
        </Anchor>
        <Anchor href={href('pdf')} download className={classes.exportLink}>
          <IconFileTypePdf size={18} aria-hidden /> {t('reports.export.pdf')}
        </Anchor>
      </Group>
      <Text size="sm" c="dimmed">
        {t('reports.export.help')}
      </Text>
    </div>
  );
}

/** Download the coverage or gap report on the screen as an Excel workbook or a PDF. The file
 * states the method and the time it was made on every sheet and page. The link is a plain
 * address, so the browser downloads it with the session; the server checks who may. */
export function ExportLinks({
  versionId,
  frameworkId,
  reportKey,
  method,
}: {
  versionId: string | null;
  frameworkId: string | null;
  reportKey: string;
  method: CoverageMethod;
}) {
  if (!versionId || !frameworkId) return null;
  return (
    <ExportLinksFor
      href={(format) =>
        reportExportUrl(versionId, reportKey, { format, framework_id: frameworkId, method })
      }
    />
  );
}
