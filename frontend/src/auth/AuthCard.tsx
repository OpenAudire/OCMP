import type { ReactNode } from 'react';
import { Center, Paper, Stack, Title } from '@mantine/core';

import { Wordmark } from '../layout/Wordmark';

/** The frame of the signed-out pages: product wordmark, page title, content. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Center mih="100vh" px="md" py="xl" component="main">
      <Paper withBorder p={{ base: 'lg', sm: 'xl' }} w="100%" maw={440}>
        <Stack gap="lg">
          <Stack gap="md">
            <Wordmark />
            <Title order={1} size="h2" fz={24}>
              {title}
            </Title>
          </Stack>
          {children}
        </Stack>
      </Paper>
    </Center>
  );
}
