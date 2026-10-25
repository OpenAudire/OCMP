import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import { Permission } from '../session/permissions';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchAuthOptions: vi.fn(),
  fetchSetupStatus: vi.fn(),
  runSetup: vi.fn(),
}));

const mocked = vi.mocked(endpoints);
const signedOut = new ApiError(401, 'Not authenticated.');

async function type(label: RegExp, value: string) {
  fireEvent.change(await screen.findByLabelText(label), { target: { value } });
}

function click(name: string) {
  fireEvent.click(screen.getByRole('button', { name }));
}

async function fillInstitution() {
  await type(/^Setup token/, ' abcd-efgh-ijkl-mnop ');
  await type(/^Institution name/, 'Demo University');
  await type(/^Short code/, 'demo-hs');
  fireEvent.click(screen.getByLabelText(/Health sciences features/));
  click('Next');
}

async function fillAdmin(confirm = 'a long enough passphrase') {
  await type(/^Your name/, 'First Admin');
  await type(/^Your email address/, 'first.admin@example.org');
  await type(/^Password/, 'a long enough passphrase');
  await type(/^Repeat password/, confirm);
  click('Next');
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.fetchMe.mockRejectedValue(signedOut);
  mocked.fetchMyRoles.mockRejectedValue(signedOut);
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
  mocked.fetchAuthOptions.mockResolvedValue({
    password_min_length: 12,
    password_max_length: 256,
    sso_enabled: false,
    sso_provider_name: 'SSO',
  });
  mocked.fetchSetupStatus.mockResolvedValue({ needs_setup: true });
});

describe('first-run setup', () => {
  it('is where a fresh installation sends visitors', async () => {
    renderAt('/');

    expect(await screen.findByRole('heading', { name: 'Set up OCMP' })).toBeInTheDocument();
  });

  it('is closed once setup is complete', async () => {
    mocked.fetchSetupStatus.mockResolvedValue({ needs_setup: false });

    renderAt('/setup');

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('checks each step before moving on', async () => {
    renderAt('/setup');
    await screen.findByLabelText(/^Setup token/);

    click('Next');
    expect(await screen.findAllByText('This field is required.')).not.toHaveLength(0);

    await fillInstitution();
    await fillAdmin('a different passphrase');

    expect(await screen.findByText('The passwords do not match.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create and sign in' })).not.toBeInTheDocument();
  });

  it('creates the institution and admin, then signs in', async () => {
    mocked.runSetup.mockImplementation(async () => {
      mocked.fetchMe.mockResolvedValue(testUser);
      mocked.fetchMyRoles.mockResolvedValue([
        role('platform_admin', Object.values(Permission)),
      ]);
      mocked.fetchSetupStatus.mockResolvedValue({ needs_setup: false });
    });
    renderAt('/setup');

    await fillInstitution();
    await fillAdmin();
    expect(await screen.findByText('DEMO-HS')).toBeInTheDocument(); // summary
    click('Create and sign in');

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(mocked.runSetup).toHaveBeenCalledWith({
      token: 'abcd-efgh-ijkl-mnop',
      institution_name: 'Demo University',
      institution_short_code: 'demo-hs',
      country: 'ZA',
      health_profile: true,
      admin_display_name: 'First Admin',
      admin_email: 'first.admin@example.org',
      admin_password: 'a long enough passphrase',
    });
  });

  it('returns to the first step when the token is wrong', async () => {
    mocked.runSetup.mockRejectedValue(new ApiError(403, 'The setup token is not correct.'));
    renderAt('/setup');

    await fillInstitution();
    await fillAdmin();
    click('Create and sign in');

    expect(await screen.findByText(/setup token is not correct/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText(/^Setup token/)).toBeVisible());
  });

  it('explains when someone else completed setup first', async () => {
    mocked.runSetup.mockRejectedValue(new ApiError(409, 'already set up'));
    renderAt('/setup');

    await fillInstitution();
    await fillAdmin();
    click('Create and sign in');

    expect(await screen.findByText(/already been set up/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login');
  });
});
