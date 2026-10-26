import { Button } from '@mantine/core';
import { IconTags } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, Route, Routes } from 'react-router';

import { NoAccessPage } from '../pages/StatusPages';
import { Permission } from '../session/permissions';
import { useSession } from '../session/useSession';
import { Page } from '../ui/Page';
import { TagListsPage } from './TagListsPage';

export const TAG_LISTS_PATH = '/admin/tag-lists';

/** `/admin`: the admin screens this user may use (more arrive in later slices). */
function AdminHome() {
  const { t } = useTranslation();
  const { data: session } = useSession();
  const canManageTags = session?.permissions.has(Permission.TaglistsManage) ?? false;
  return (
    <Page
      title={t('nav.admin')}
      description={canManageTags ? t('admin.intro') : t('pages.comingSoon')}
    >
      {canManageTags && (
        <div>
          <Button
            component={Link}
            to={TAG_LISTS_PATH}
            variant="default"
            leftSection={<IconTags size={18} aria-hidden />}
          >
            {t('admin.tagListsLink')}
          </Button>
        </div>
      )}
    </Page>
  );
}

/** The admin section: tag lists for the curriculum office. */
export function AdminSection() {
  const { data: session } = useSession();
  const canManageTags = session?.permissions.has(Permission.TaglistsManage) ?? false;
  return (
    <Routes>
      <Route index element={<AdminHome />} />
      <Route
        path="tag-lists"
        element={canManageTags ? <TagListsPage /> : <NoAccessPage />}
      />
      <Route path="*" element={<AdminHome />} />
    </Routes>
  );
}
