import { Button, Group } from '@mantine/core';
import {
  IconAdjustments,
  IconChartDots,
  IconShieldLock,
  IconSparkles,
  IconTags,
  IconUsers,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, Route, Routes } from 'react-router';

import { NoAccessPage } from '../pages/StatusPages';
import { Permission } from '../session/permissions';
import { useSession } from '../session/useSession';
import { Page } from '../ui/Page';
import { AiEvaluationPage } from './AiEvaluationPage';
import { AiSettingsPage } from './AiSettingsPage';
import { InstitutionSettingsPage } from './InstitutionSettingsPage';
import { RolesPage } from './RolesPage';
import { TagListsPage } from './TagListsPage';
import { UserDetailPage } from './UserDetailPage';
import { UsersPage } from './UsersPage';

export const TAG_LISTS_PATH = '/admin/tag-lists';
export const AI_SETTINGS_PATH = '/admin/ai';
export const AI_EVALUATION_PATH = '/admin/ai-evaluation';
export const USERS_PATH = '/admin/users';
export const ROLES_PATH = '/admin/roles';
export const SETTINGS_PATH = '/admin/settings';

/** `/admin`: the admin screens this user may use (more arrive in later slices). */
function AdminHome() {
  const { t } = useTranslation();
  const { data: session } = useSession();
  const canManageTags = session?.permissions.has(Permission.TaglistsManage) ?? false;
  const canManageSettings = session?.permissions.has(Permission.SettingsManage) ?? false;
  const canManageUsers = session?.permissions.has(Permission.UsersManage) ?? false;
  const canManageRoles = session?.permissions.has(Permission.RolesManage) ?? false;
  const any = canManageTags || canManageSettings || canManageUsers || canManageRoles;
  return (
    <Page title={t('nav.admin')} description={any ? t('admin.intro') : t('pages.comingSoon')}>
      <Group>
        {canManageUsers && (
          <Button
            component={Link}
            to={USERS_PATH}
            variant="default"
            leftSection={<IconUsers size={18} aria-hidden />}
          >
            {t('admin.usersLink')}
          </Button>
        )}
        {canManageRoles && (
          <Button
            component={Link}
            to={ROLES_PATH}
            variant="default"
            leftSection={<IconShieldLock size={18} aria-hidden />}
          >
            {t('admin.rolesLink')}
          </Button>
        )}
        {canManageSettings && (
          <Button
            component={Link}
            to={SETTINGS_PATH}
            variant="default"
            leftSection={<IconAdjustments size={18} aria-hidden />}
          >
            {t('admin.settingsLink')}
          </Button>
        )}
        {canManageTags && (
          <Button
            component={Link}
            to={TAG_LISTS_PATH}
            variant="default"
            leftSection={<IconTags size={18} aria-hidden />}
          >
            {t('admin.tagListsLink')}
          </Button>
        )}
        {canManageSettings && (
          <Button
            component={Link}
            to={AI_SETTINGS_PATH}
            variant="default"
            leftSection={<IconSparkles size={18} aria-hidden />}
          >
            {t('admin.aiLink')}
          </Button>
        )}
        {canManageSettings && (
          <Button
            component={Link}
            to={AI_EVALUATION_PATH}
            variant="default"
            leftSection={<IconChartDots size={18} aria-hidden />}
          >
            {t('admin.evaluationLink')}
          </Button>
        )}
      </Group>
    </Page>
  );
}

/** The admin section: tag lists for the curriculum office, AI settings for administrators. */
export function AdminSection() {
  const { data: session } = useSession();
  const canManageTags = session?.permissions.has(Permission.TaglistsManage) ?? false;
  const canManageSettings = session?.permissions.has(Permission.SettingsManage) ?? false;
  const canManageUsers = session?.permissions.has(Permission.UsersManage) ?? false;
  const canManageRoles = session?.permissions.has(Permission.RolesManage) ?? false;
  return (
    <Routes>
      <Route index element={<AdminHome />} />
      <Route path="users" element={canManageUsers ? <UsersPage /> : <NoAccessPage />} />
      <Route path="users/:userId" element={canManageUsers ? <UserDetailPage /> : <NoAccessPage />} />
      <Route path="roles" element={canManageRoles ? <RolesPage /> : <NoAccessPage />} />
      <Route
        path="settings"
        element={canManageSettings ? <InstitutionSettingsPage /> : <NoAccessPage />}
      />
      <Route
        path="tag-lists"
        element={canManageTags ? <TagListsPage /> : <NoAccessPage />}
      />
      <Route
        path="ai"
        element={canManageSettings ? <AiSettingsPage /> : <NoAccessPage />}
      />
      <Route
        path="ai-evaluation"
        element={canManageSettings ? <AiEvaluationPage /> : <NoAccessPage />}
      />
      <Route path="*" element={<AdminHome />} />
    </Routes>
  );
}
