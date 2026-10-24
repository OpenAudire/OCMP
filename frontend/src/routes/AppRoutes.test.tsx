import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { Institution, RoleAssignment, User } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { createQueryClient } from '../queryClient';
import { AppRoutes } from './AppRoutes';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  logout: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const user: User = {
  id: 'u1',
  email: 'student@example.org',
  display_name: 'Demo Student',
  is_active: true,
  last_login_at: null,
};

function role(key: string, permissions: string[]): RoleAssignment {
  return {
    id: `a-${key}`,
    user_id: user.id,
    role: { key, name: key, permissions },
    scope_type: 'instance',
    scope_id: null,
    expires_at: null,
    created_at: '2026-10-25T00:00:00Z',
  };
}

const institution: Institution = {
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

function renderAt(path: string) {
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

function signedInWith(...roles: RoleAssignment[]) {
  mocked.fetchMe.mockResolvedValue(user);
  mocked.fetchMyRoles.mockResolvedValue(roles);
  mocked.fetchInstitution.mockResolvedValue(institution);
}

describe('app routes', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    applyTerminology(i18n, {});
  });

  it('sends signed-out visitors to the sign-in page', async () => {
    mocked.fetchMe.mockRejectedValue(new ApiError(401, 'Not authenticated.'));
    mocked.fetchMyRoles.mockRejectedValue(new ApiError(401, 'Not authenticated.'));

    renderAt('/curriculum');

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
    expect(mocked.fetchInstitution).not.toHaveBeenCalled();
  });

  it('takes students to the explorer and shows only their sections', async () => {
    signedInWith(role('student', ['curriculum.view_published']));

    renderAt('/');

    expect(await screen.findByRole('heading', { name: 'Explorer' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const links = within(nav).getAllByRole('link').map((link) => link.textContent);
    expect(links).toEqual(['Explorer', 'Search']);
    expect(await screen.findByText('Demo University')).toBeInTheDocument();
  });

  it('applies the institution terminology', async () => {
    signedInWith(role('student', ['curriculum.view_published']));

    renderAt('/');

    await waitFor(() => expect(i18n.t('terms.module', { count: 2 })).toBe('Courses'));
  });

  it('refuses sections the user cannot use, even by direct address', async () => {
    signedInWith(role('lecturer', ['curriculum.view', 'objectives.edit']));

    renderAt('/admin');

    expect(await screen.findByRole('heading', { name: 'No access' })).toBeInTheDocument();
  });

  it('explains when an account has no roles yet', async () => {
    signedInWith();

    renderAt('/');

    expect(await screen.findByText(/no roles yet/)).toBeInTheDocument();
  });

  it('shows a not-found page for unknown addresses', async () => {
    signedInWith(role('student', ['curriculum.view_published']));

    renderAt('/no-such-page');

    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('offers a retry when the API cannot be reached', async () => {
    mocked.fetchMe.mockRejectedValue(new ApiError(0, 'Network Error'));
    mocked.fetchMyRoles.mockRejectedValue(new ApiError(0, 'Network Error'));

    renderAt('/');

    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('works before first-run setup (no institution yet)', async () => {
    signedInWith(role('student', ['curriculum.view_published']));
    mocked.fetchInstitution.mockRejectedValue(new ApiError(404, 'not set up'));

    renderAt('/explorer');

    expect(await screen.findByRole('heading', { name: 'Explorer' })).toBeInTheDocument();
  });
});
