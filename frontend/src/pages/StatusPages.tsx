import { Button, Center, Loader } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Page } from '../ui/Page';
import { ErrorState } from '../ui/States';

export function FullPageLoader() {
  const { t } = useTranslation();
  return (
    <Center h="100vh">
      <Loader aria-label={t('layout.loading')} />
    </Center>
  );
}

export function PlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return <Page title={t(titleKey)} description={t('pages.comingSoon')} />;
}

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <Page title={t('pages.notFoundTitle')} description={t('pages.notFoundBody')}>
      <Button component={Link} to="/" variant="default" w="fit-content">
        {t('pages.backHome')}
      </Button>
    </Page>
  );
}

export function NoAccessPage({ noRoles = false }: { noRoles?: boolean }) {
  const { t } = useTranslation();
  return (
    <Page
      title={t('pages.noAccessTitle')}
      description={t(noRoles ? 'pages.noRolesBody' : 'pages.noAccessBody')}
    />
  );
}

/** The API could not be reached before the app frame could load. */
export function ErrorPage({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <Center mih="100vh" px="md" component="main">
      <ErrorState
        title={t('pages.errorTitle')}
        body={t('pages.errorBody')}
        actions={<Button onClick={onRetry}>{t('pages.retry')}</Button>}
      />
    </Center>
  );
}
