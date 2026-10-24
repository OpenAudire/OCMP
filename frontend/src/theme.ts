import { createTheme } from '@mantine/core';

/** Mantine theme. Defaults meet WCAG AA contrast; keep focus rings visible. */
export const theme = createTheme({
  primaryColor: 'indigo',
  defaultRadius: 'sm',
  focusRing: 'auto',
});
