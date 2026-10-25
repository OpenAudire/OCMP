import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';

import { AccountPage } from '../account/AccountPage';
import { ForgotPasswordPage } from '../auth/ForgotPasswordPage';
import { LoginPage } from '../auth/LoginPage';
import { ResetPasswordPage } from '../auth/ResetPasswordPage';
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

/** A section page, shown only to users whose permissions include it. */
function Section({ item }: { item: NavItem }) {
  const { data: session } = useSession();
  if (!item.isVisible(session?.permissions ?? new Set())) return <NoAccessPage />;
  return <PlaceholderPage titleKey={`nav.${item.key}`} />;
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
