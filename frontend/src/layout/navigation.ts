import {
  IconBinaryTree,
  IconChartBar,
  IconCompass,
  IconHierarchy3,
  IconLayoutDashboard,
  IconLink,
  IconSearch,
  IconSettings,
  type TablerIcon,
} from '@tabler/icons-react';

import { hasAny, Permission } from '../session/permissions';

export interface NavItem {
  /** Translation key under `nav.` and route path segment. */
  key: string;
  path: string;
  icon: TablerIcon;
  isVisible: (held: ReadonlySet<string>) => boolean;
}

/**
 * Main navigation (brief section 11): staff see Dashboard, Curriculum, Mapping,
 * Frameworks, Reports, Search and Admin as their permissions allow; people who
 * can only read the published curriculum (students) see Explorer and Search.
 */
export const NAV_ITEMS: NavItem[] = [
  {
    key: 'dashboard',
    path: '/dashboard',
    icon: IconLayoutDashboard,
    isVisible: (p) => hasAny(p, Permission.CurriculumView),
  },
  {
    key: 'curriculum',
    path: '/curriculum',
    icon: IconHierarchy3,
    isVisible: (p) => hasAny(p, Permission.CurriculumView),
  },
  {
    key: 'mapping',
    path: '/mapping',
    icon: IconLink,
    isVisible: (p) =>
      hasAny(p, Permission.MappingEdit, Permission.MappingReview, Permission.MappingSecondReview),
  },
  {
    key: 'frameworks',
    path: '/frameworks',
    icon: IconBinaryTree,
    isVisible: (p) => hasAny(p, Permission.CurriculumView, Permission.FrameworksManage),
  },
  {
    key: 'reports',
    path: '/reports',
    icon: IconChartBar,
    isVisible: (p) => hasAny(p, Permission.ReportsView),
  },
  {
    key: 'explorer',
    path: '/explorer',
    icon: IconCompass,
    isVisible: (p) =>
      hasAny(p, Permission.CurriculumViewPublished) && !hasAny(p, Permission.CurriculumView),
  },
  {
    key: 'search',
    path: '/search',
    icon: IconSearch,
    isVisible: (p) => hasAny(p, Permission.CurriculumView, Permission.CurriculumViewPublished),
  },
  {
    key: 'admin',
    path: '/admin',
    icon: IconSettings,
    isVisible: (p) =>
      hasAny(
        p,
        Permission.UsersManage,
        Permission.RolesManage,
        Permission.SettingsManage,
        Permission.AuditView
      ),
  },
];

export function visibleNavItems(held: ReadonlySet<string>): NavItem[] {
  return NAV_ITEMS.filter((item) => item.isVisible(held));
}
