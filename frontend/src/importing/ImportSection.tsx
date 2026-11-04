import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router';

import { PlaceholderPage } from '../pages/StatusPages';
import { Permission } from '../session/permissions';
import { useSession } from '../session/useSession';
import { Page } from '../ui/Page';
import { CurriculumImportCard } from './CurriculumImportCard';
import { ExportCard } from './ExportCard';
import { ImportHistoryCard } from './ImportHistoryCard';
import { PackImportCard } from './PackImportPage';
import { MappingImportCard, TagImportCard } from './TagAndMappingImportCards';
import { TemplatesCard } from './TemplatesCard';

interface Allowed {
  curriculum: boolean;
  frameworks: boolean;
  tags: boolean;
  mappings: boolean;
  exports: boolean;
}

function ImportHome({ allowed }: { allowed: Allowed }) {
  const { t } = useTranslation();
  return (
    <Page title={t('nav.import')} description={t('import.intro')}>
      {allowed.curriculum && <CurriculumImportCard />}
      {allowed.mappings && <MappingImportCard />}
      {allowed.tags && <TagImportCard />}
      {allowed.frameworks && <PackImportCard />}
      {allowed.frameworks && <TemplatesCard />}
      {allowed.exports && <ExportCard />}
      <ImportHistoryCard />
    </Page>
  );
}

/** `/import`: Excel imports of the curriculum, mappings and tags, the framework import (pack file
 * or Excel) and the history of applied imports, each for the people who may do it. */
export function ImportSection() {
  const { data: session } = useSession();
  const has = (permission: string) =>
    session?.permissions.has(permission as Permission) ?? false;
  const allowed: Allowed = {
    frameworks: has(Permission.FrameworksManage),
    curriculum: has(Permission.CurriculumEdit) && has(Permission.ObjectivesEdit),
    tags: has(Permission.TaglistsManage),
    mappings: has(Permission.MappingEdit),
    exports: has(Permission.ReportsView) && has(Permission.CurriculumView),
  };
  if (!Object.values(allowed).some(Boolean)) return <PlaceholderPage titleKey="nav.import" />;
  return (
    <Routes>
      <Route path="*" element={<ImportHome allowed={allowed} />} />
    </Routes>
  );
}
