import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router';

import { PlaceholderPage } from '../pages/StatusPages';
import { Permission } from '../session/permissions';
import { useSession } from '../session/useSession';
import { Page } from '../ui/Page';
import { CurriculumImportCard } from './CurriculumImportCard';
import { PackImportCard } from './PackImportPage';
import { TemplatesCard } from './TemplatesCard';

function ImportHome({
  curriculum,
  frameworks,
}: {
  curriculum: boolean;
  frameworks: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Page title={t('nav.import')} description={t('import.intro')}>
      {curriculum && <CurriculumImportCard />}
      {frameworks && <PackImportCard />}
      {frameworks && <TemplatesCard />}
    </Page>
  );
}

/** `/import`: the Excel import of a draft curriculum version (for people who may edit the
 * curriculum) and the framework pack import (for people who manage frameworks). */
export function ImportSection() {
  const { data: session } = useSession();
  const canManageFrameworks = session?.permissions.has(Permission.FrameworksManage) ?? false;
  const canImportCurriculum =
    (session?.permissions.has(Permission.CurriculumEdit) ?? false) &&
    (session?.permissions.has(Permission.ObjectivesEdit) ?? false);
  if (!canManageFrameworks && !canImportCurriculum) return <PlaceholderPage titleKey="nav.import" />;
  return (
    <Routes>
      <Route
        path="*"
        element={<ImportHome curriculum={canImportCurriculum} frameworks={canManageFrameworks} />}
      />
    </Routes>
  );
}
