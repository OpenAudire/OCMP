import type { ReactNode } from 'react';
import { MantineProvider } from '@mantine/core';

import { cssVariablesResolver, theme } from './theme';

/**
 * Mantine with the design tokens. The colour scheme follows the system until the user
 * picks one with the theme toggle; the choice is kept in this browser (local storage).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <MantineProvider
      theme={theme}
      cssVariablesResolver={cssVariablesResolver}
      defaultColorScheme="auto"
    >
      {children}
    </MantineProvider>
  );
}
