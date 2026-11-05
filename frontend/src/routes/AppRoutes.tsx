import type { ReactNode } from 'react';
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router';

import { AccountPage } from '../account/AccountPage';
import { AdminSection } from '../admin/AdminSection';
import { ForgotPasswordPage } from '../auth/ForgotPasswordPage';
import { LoginPage } from '../auth/LoginPage';
import { ResetPasswordPage } from '../auth/ResetPasswordPage';
import { CurriculumSection } from '../curriculum/CurriculumPage';
import { DashboardPage } from '../dashboard/DashboardPage';
import { ExplorerSection } from '../explorer/ExplorerSection';
import { FrameworksSection } from '../frameworks/FrameworksSection';
import { MappingSection } from '../mapping/MappingPage';
import { ReviewSection } from '../review/ReviewPage';
import { ImportSection } from '../importing/ImportSection';
import { InstitutionProvider } from '../institution/InstitutionProvider';
import { AppLayout } from '../layout/AppLayout';
import { NAV_ITEMS, visibleNavItems, type NavItem } from '../layout/navigation';
import {
  ErrorPage,
  FullPageLoader,
  NoAccessPage,
  NotFoundPage,
  PlaceholderPage,
} from '../pages/StatusPages';
import { useSession } from '../session/useSession';
import { ReportsSection } from '../reports/ReportsSection';
import { SearchPage } from '../search/SearchPage';
import { SetupPage } from '../setup/SetupPage';

/** Only for signed-in users; others go to the sign-in page and come back after. */
function RequireAuth() {
  const { data: session, isPending, isError, refetch } = useSession();
  const location = useLocation();

  if (isPending) return <FullPageLoader />;
  if (isError) return <ErrorPage onRetry={() => void refetch()} />;
  if (!session) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return (
    <InstitutionProvider enabled>
      <Outlet />
    </InstitutionProvider>
  );
}

/** The start page: the first section this user may use. */
function StartPage() {
  const { data: session } = useSession();
  const first = visibleNavItems(session?.permissions ?? new Set())[0];
  return first ? <Navigate to={first.path} replace /> : <NoAccessPage noRoles />;
}

/** Sections that are built; the others show a placeholder. */
const SECTIONS: Partial<Record<string, () => ReactNode>> = {
  dashboard: () => <DashboardPage />,
  explorer: () => <ExplorerSection />,
  curriculum: () => <CurriculumSection />,
  frameworks: () => <FrameworksSection />,
  mapping: () => <MappingSection />,
  review: () => <ReviewSection />,
  admin: () => <AdminSection />,
  import: () => <ImportSection />,
  search: () => <SearchPage />,
  reports: () => <ReportsSection />,
};

/** A section page, shown only to users whose permissions include it. */
function Section({ item }: { item: NavItem }) {
  const { data: session } = useSession();
  if (!item.isVisible(session?.permissions ?? new Set())) return <NoAccessPage />;
  return SECTIONS[item.key]?.() ?? <PlaceholderPage titleKey={`nav.${item.key}`} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/setup" element={<SetupPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<StartPage />} />
          <Route path="/account" element={<AccountPage />} />
          {NAV_ITEMS.map((item) => (
            <Route key={item.key} path={`${item.path}/*`} element={<Section item={item} />} />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
