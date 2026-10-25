import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import './theme/fonts';
import './theme/global.css';

import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router';

import { createQueryClient } from './queryClient';
import { AppRoutes } from './routes/AppRoutes';
import { ThemeProvider } from './theme/ThemeProvider';

const queryClient = createQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Notifications />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
