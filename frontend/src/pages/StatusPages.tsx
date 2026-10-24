import { Button, Center, Loader, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

export function FullPageLoader() {
  const { t } = useTranslation();
  return (
    <Center h="100vh">
      <Loader aria-label={t('layout.loading')} />
    </Center>
  );
}

function Message({ title, body, children }: { title: string; body: string; children?: React.ReactNode }) {
  return (
    <Stack maw={560} gap="sm" py="xl">
      <Title order={2}>{title}</Title>
      <Text>{body}</Text>
      {children}
    </Stack>
  );
}

export function PlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return <Message title={t(titleKey)} body={t('pages.comingSoon')} />;
}

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <Message title={t('pages.notFoundTitle')} body={t('pages.notFoundBody')}>
      <Button component={Link} to="/" variant="light" w="fit-content">
        {t('pages.backHome')}
      </Button>
    </Message>
  );
}

export function NoAccessPage({ noRoles = false }: { noRoles?: boolean }) {
  const { t } = useTranslation();
  return (
    <Message
      title={t('pages.noAccessTitle')}
      body={t(noRoles ? 'pages.noRolesBody' : 'pages.noAccessBody')}
    />
  );
}

export function ErrorPage({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <Center h="100vh" px="md">
      <Message title={t('pages.errorTitle')} body={t('pages.errorBody')}>
        <Button onClick={onRetry} w="fit-content">
          {t('pages.retry')}
        </Button>
      </Message>
    </Center>
  );
}
