import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { RoleAssignment } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchAuthOptions: vi.fn(),
  logout: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function signedInWith(...roles: RoleAssignment[]) {
  mocked.fetchMe.mockResolvedValue(testUser);
  mocked.fetchMyRoles.mockResolvedValue(roles);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
}

describe('app routes', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    applyTerminology(i18n, {});
    mocked.fetchAuthOptions.mockResolvedValue({
      password_min_length: 12,
      password_max_length: 256,
      sso_enabled: false,
      sso_provider_name: 'SSO',
    });
  });

  it('sends signed-out visitors to the sign-in page', async () => {
    mocked.fetchMe.mockRejectedValue(new ApiError(401, 'Not authenticated.'));
    mocked.fetchMyRoles.mockRejectedValue(new ApiError(401, 'Not authenticated.'));

    renderAt('/curriculum');

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
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
