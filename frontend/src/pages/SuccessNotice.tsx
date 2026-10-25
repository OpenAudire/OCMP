import type { ReactNode } from 'react';
import { Paper, Text } from '@mantine/core';

/**
 * A confirmation message, announced politely by screen readers (role="status").
 * Mantine's Alert always uses role="alert", which is meant for errors.
 */
export function SuccessNotice({ children }: { children: ReactNode }) {
  return (
    <Paper
      role="status"
      withBorder
      p="sm"
      radius="md"
      bg="var(--cic-brand-soft)"
      c="var(--cic-brand-ink)"
    >
      <Text size="sm">{children}</Text>
    </Paper>
  );
}
