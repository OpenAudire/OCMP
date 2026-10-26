import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router';

import { PlaceholderPage } from '../pages/StatusPages';
import { Permission } from '../session/permissions';
import { useSession } from '../session/useSession';
import { Page } from '../ui/Page';
import { PackImportCard } from './PackImportPage';
import { TemplatesCard } from './TemplatesCard';

function ImportHome() {
  const { t } = useTranslation();
  return (
    <Page title={t('nav.import')} description={t('import.intro')}>
      <PackImportCard />
      <TemplatesCard />
    </Page>
  );
}

/** `/import`: framework pack import for people who manage frameworks (more arrives later). */
export function ImportSection() {
  const { data: session } = useSession();
  const canManageFrameworks = session?.permissions.has(Permission.FrameworksManage) ?? false;
  if (!canManageFrameworks) return <PlaceholderPage titleKey="nav.import" />;
  return (
    <Routes>
      <Route path="*" element={<ImportHome />} />
    </Routes>
  );
}
