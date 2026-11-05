import {
  IconAdjustments,
  IconChartBar,
  IconCompass,
  IconLayoutDashboard,
  IconRoute,
  IconSearch,
  IconSitemap,
  IconSquareCheck,
  IconStack2,
  IconUpload,
  type TablerIcon,
} from '@tabler/icons-react';

import { hasAny, Permission } from '../session/permissions';

export interface NavItem {
  /** Translation key under `nav.` */
  key: string;
  path: string;
  icon: TablerIcon;
  /** Shown indented under this item (the review queue under mapping). */
  parent?: string;
  isVisible: (held: ReadonlySet<string>) => boolean;
}

/**
 * Main navigation (brief section 11, Phase 1 decision 7): staff see Dashboard,
 * Curriculum, Mapping with its Review queue, Frameworks, Reports, Import and export,
 * Search and Admin as their permissions allow; people who can only read the published
 * curriculum (students) see Explorer and Search.
 */
export const NAV_ITEMS: NavItem[] = [
  {
    key: 'dashboard',
    path: '/dashboard',
    icon: IconLayoutDashboard,
    // The committee overview is a report of the whole curriculum.
    isVisible: (p) => p.has(Permission.ReportsView) && p.has(Permission.CurriculumView),
  },
  {
    key: 'curriculum',
    path: '/curriculum',
    icon: IconStack2,
    isVisible: (p) => hasAny(p, Permission.CurriculumView),
  },
  {
    key: 'mapping',
    path: '/mapping',
    icon: IconRoute,
    isVisible: (p) =>
      hasAny(p, Permission.MappingEdit, Permission.MappingReview, Permission.MappingSecondReview),
  },
  {
    key: 'review',
    path: '/mapping/review',
    icon: IconSquareCheck,
    parent: 'mapping',
    isVisible: (p) => hasAny(p, Permission.MappingReview, Permission.MappingSecondReview),
  },
  {
    key: 'frameworks',
    path: '/frameworks',
    icon: IconSitemap,
    isVisible: (p) => hasAny(p, Permission.CurriculumView, Permission.FrameworksManage),
  },
  {
    key: 'reports',
    path: '/reports',
    icon: IconChartBar,
    isVisible: (p) => hasAny(p, Permission.ReportsView),
  },
  {
    key: 'import',
    path: '/import',
    icon: IconUpload,
    isVisible: (p) =>
      hasAny(
        p,
        Permission.CurriculumEdit,
        Permission.FrameworksManage,
        Permission.TaglistsManage,
        Permission.MappingEdit
      ) ||
      // Exports: staff who read the whole curriculum and its reports (not external reviewers).
      (p.has(Permission.ReportsView) && p.has(Permission.CurriculumView)),
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
    icon: IconAdjustments,
    isVisible: (p) =>
      hasAny(
        p,
        Permission.UsersManage,
        Permission.RolesManage,
        Permission.SettingsManage,
        Permission.AuditView,
        Permission.TaglistsManage
      ),
  },
];

export function visibleNavItems(held: ReadonlySet<string>): NavItem[] {
  return NAV_ITEMS.filter((item) => item.isVisible(held));
}

/**
 * The item for an address: the longest path that matches whole segments, so
 * `/mapping/review/12` marks the review queue, not mapping as well.
 */
export function activeNavKey(items: readonly NavItem[], pathname: string): string | undefined {
  let best: NavItem | undefined;
  for (const item of items) {
    const matches = pathname === item.path || pathname.startsWith(`${item.path}/`);
    if (matches && (!best || item.path.length > best.path.length)) best = item;
  }
  return best?.key;
}
