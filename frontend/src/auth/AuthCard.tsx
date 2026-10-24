import type { ReactNode } from 'react';
import { Center, Paper, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** The frame of the signed-out pages: app name, page title, content. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <Center mih="100vh" px="md" py="xl" component="main">
      <Paper withBorder shadow="sm" p="xl" radius="md" w="100%" maw={420}>
        <Stack gap="lg">
          <Stack gap={4}>
            <Text fw={700} c="dimmed" size="sm">
              {t('app.title')}
            </Text>
            <Title order={1} size="h2">
              {title}
            </Title>
          </Stack>
          {children}
        </Stack>
      </Paper>
    </Center>
  );
}
