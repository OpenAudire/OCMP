import { QueryClient } from '@tanstack/react-query';

import { isApiError } from './api/client';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 1000 * 60 * 5,
        // Client errors (401, 403, 404, 422...) will not change on retry.
        retry: (failureCount, error) =>
          failureCount < 2 && !(isApiError(error) && error.status >= 400 && error.status < 500),
      },
    },
  });
}
