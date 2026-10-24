import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import type { Institution, RoleAssignment, User } from '../api/types';
import { createQueryClient } from '../queryClient';
import { AppRoutes } from '../routes/AppRoutes';

/** Render the whole app at an address, with fresh query state and no retries. */
export function renderAt(path: string) {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>
  );
}

export const testUser: User = {
  id: 'u1',
  email: 'demo.user@example.org',
  display_name: 'Demo User',
  is_active: true,
  last_login_at: null,
  has_password: true,
};

export function role(key: string, permissions: string[]): RoleAssignment {
  return {
    id: `a-${key}`,
    user_id: testUser.id,
    role: { key, name: key, permissions },
    scope_type: 'instance',
    scope_id: null,
    expires_at: null,
    created_at: '2026-10-25T00:00:00Z',
  };
}

export const testInstitution: Institution = {
  id: 'i1',
  name: 'Demo University',
  short_code: 'DEMO',
  country: 'ZA',
  terminology: { module: { singular: 'Course', plural: 'Courses' } },
  profiles: ['core'],
  features: [],
  default_taxonomy_scale: null,
  mapping: { four_eyes: false, second_review_for_rejects: false },
};
