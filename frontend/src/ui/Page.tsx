import type { ReactNode } from 'react';
import { Stack, Text, Title } from '@mantine/core';

import classes from './Page.module.css';

interface PageProps {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
}

/** A page inside the app frame: the page title (the only h1), a short description, content. */
export function Page({ title, description, children }: PageProps) {
  return (
    <div className={classes.page}>
      <Stack gap={8}>
        <Title order={1}>{title}</Title>
        {description && (
          <Text size="md" c="dimmed">
            {description}
          </Text>
        )}
      </Stack>
      {children}
    </div>
  );
}
