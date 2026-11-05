import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { safeNext } from './safeNext';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchAuthOptions: vi.fn(),
  fetchSetupStatus: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  requestPasswordReset: vi.fn(),
  confirmPasswordReset: vi.fn(),
  changePassword: vi.fn(),
  fetchApiTokens: vi.fn(),
}));

const mocked = vi.mocked(endpoints);
const signedOut = new ApiError(401, 'Not authenticated.');
const STUDENT = role('student', ['curriculum.view_published']);

function options(sso = false) {
  mocked.fetchAuthOptions.mockResolvedValue({
    password_min_length: 12,
    password_max_length: 256,
    sso_enabled: sso,
    sso_provider_name: 'University SSO',
  });
}

function startSignedOut() {
  mocked.fetchMe.mockRejectedValue(signedOut);
  mocked.fetchMyRoles.mockRejectedValue(signedOut);
}

function signInSucceeds() {
  mocked.login.mockImplementation(async () => {
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([STUDENT]);
  });
}

async function type(label: RegExp, value: string) {
  fireEvent.change(await screen.findByLabelText(label), { target: { value } });
}

function submit(name: string | RegExp) {
  fireEvent.click(screen.getByRole('button', { name }));
}

beforeEach(() => {
  vi.resetAllMocks();
  options();
  mocked.fetchSetupStatus.mockResolvedValue({ needs_setup: false });
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
  mocked.fetchApiTokens.mockResolvedValue([]);
});

describe('sign in', () => {
  it('signs in and continues to the requested page', async () => {
    startSignedOut();
    signInSucceeds();
    renderAt('/login?next=%2Fsearch');

    await type(/^Email/, '  demo.user@example.org ');
    await type(/^Password/, 'a long enough passphrase');
    submit('Sign in');

    expect(await screen.findByRole('heading', { name: 'Search' })).toBeInTheDocument();
    expect(mocked.login).toHaveBeenCalledWith('demo.user@example.org', 'a long enough passphrase');
  });

  it('never redirects to another site after signing in', async () => {
    startSignedOut();
    signInSucceeds();
    renderAt('/login?next=%2F%2Fevil.example.com');

    await type(/^Email/, 'demo.user@example.org');
    await type(/^Password/, 'a long enough passphrase');
    submit('Sign in');

    // The start page for a student is the explorer.
    expect(await screen.findByRole('heading', { name: 'Explorer' })).toBeInTheDocument();
  });

  it('explains wrong credentials and clears the password', async () => {
    startSignedOut();
    mocked.login.mockRejectedValue(new ApiError(401, 'Invalid email or password.'));
    renderAt('/login');

    await type(/^Email/, 'demo.user@example.org');
    await type(/^Password/, 'wrong passphrase');
    submit('Sign in');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The email address or password is not correct.'
    );
    expect(screen.getByLabelText(/^Password/)).toHaveValue('');
  });

  it('says how long to wait when rate limited', async () => {
    startSignedOut();
    mocked.login.mockRejectedValue(new ApiError(429, 'Too many', 125));
    renderAt('/login');

    await type(/^Email/, 'demo.user@example.org');
    await type(/^Password/, 'whatever passphrase');
    submit('Sign in');

    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 3 minutes.');
  });

  it('explains a slow sign-in, and drops the note when it ends', async () => {
    startSignedOut();
    let fail!: () => void;
    mocked.login.mockImplementation(
      () =>
        new Promise<void>((_, reject) => {
          fail = () => reject(new ApiError(401, 'Invalid email or password.'));
        })
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderAt('/login');
      await type(/^Email/, 'demo.user@example.org');
      await type(/^Password/, 'wrong passphrase');
      submit('Sign in');
      await waitFor(() => expect(mocked.login).toHaveBeenCalled());
      expect(screen.queryByText(/taking a little longer/)).not.toBeInTheDocument();

      act(() => vi.advanceTimersByTime(3000));
      expect(await screen.findByText(/taking a little longer/)).toBeInTheDocument();

      act(() => fail());
      expect(await screen.findByRole('alert')).toHaveTextContent(
        'The email address or password is not correct.'
      );
      expect(screen.queryByText(/taking a little longer/)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('asks for email and password before calling the server', async () => {
    startSignedOut();
    renderAt('/login');
    await screen.findByRole('heading', { name: 'Sign in' });

    submit('Sign in');

    expect(await screen.findByText('Enter your email address.')).toBeInTheDocument();
    expect(mocked.login).not.toHaveBeenCalled();
  });

  it('offers single sign-on when enabled, keeping the destination', async () => {
    startSignedOut();
    options(true);
    renderAt('/login?next=%2Fsearch');

    const sso = await screen.findByRole('link', { name: 'Sign in with University SSO' });

    expect(sso).toHaveAttribute('href', '/api/v1/auth/oidc/login?next=%2Fsearch');
  });

  it('hides single sign-on when not configured', async () => {
    startSignedOut();
    renderAt('/login');
    await screen.findByRole('heading', { name: 'Sign in' });

    expect(screen.queryByRole('link', { name: /University SSO/ })).not.toBeInTheDocument();
  });

  it.each([
    ['account_exists', 'already exists'],
    ['sso_cancelled', 'was cancelled'],
    ['something_unexpected', 'did not complete'],
  ])('explains single sign-on error %s', async (code, text) => {
    startSignedOut();
    renderAt(`/login?sso_error=${code}`);

    expect(await screen.findByRole('alert')).toHaveTextContent(text);
  });

  it('skips the form when already signed in', async () => {
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([STUDENT]);

    renderAt('/login?next=%2Fsearch');

    expect(await screen.findByRole('heading', { name: 'Search' })).toBeInTheDocument();
  });
});

describe('forgotten password', () => {
  it('always shows the same confirmation', async () => {
    mocked.requestPasswordReset.mockResolvedValue();
    renderAt('/forgot-password');

    await type(/^Email/, ' someone@example.org ');
    submit('Send reset link');

    expect(await screen.findByRole('status')).toHaveTextContent('a reset link is on its way');
    expect(mocked.requestPasswordReset).toHaveBeenCalledWith('someone@example.org');
  });

  it('explains rate limiting', async () => {
    mocked.requestPasswordReset.mockRejectedValue(new ApiError(429, 'Too many', 30));
    renderAt('/forgot-password');

    await type(/^Email/, 'someone@example.org');
    submit('Send reset link');

    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 1 minute.');
  });
});

describe('reset password', () => {
  it('needs the link from the email', async () => {
    renderAt('/reset-password');

    expect(await screen.findByRole('alert')).toHaveTextContent('needs the link');
  });

  it('checks the new password, then sets it with the token', async () => {
    mocked.confirmPasswordReset.mockResolvedValue();
    renderAt('/reset-password#token=abc123');

    await type(/^New password/, 'short');
    await type(/^Repeat new password/, 'short');
    submit('Save new password');
    expect(await screen.findByText('Use at least 12 characters.')).toBeInTheDocument();

    await type(/^New password/, 'a brand new passphrase');
    await type(/^Repeat new password/, 'a different passphrase');
    submit('Save new password');
    expect(await screen.findByText('The passwords do not match.')).toBeInTheDocument();
    expect(mocked.confirmPasswordReset).not.toHaveBeenCalled();

    await type(/^Repeat new password/, 'a brand new passphrase');
    submit('Save new password');

    expect(await screen.findByRole('status')).toHaveTextContent('signed out everywhere');
    expect(mocked.confirmPasswordReset).toHaveBeenCalledWith('abc123', 'a brand new passphrase');
  });

  it('explains an expired link and offers a new one', async () => {
    mocked.confirmPasswordReset.mockRejectedValue(new ApiError(400, 'expired'));
    renderAt('/reset-password#token=old');

    await type(/^New password/, 'a brand new passphrase');
    await type(/^Repeat new password/, 'a brand new passphrase');
    submit('Save new password');

    expect(await screen.findByRole('alert')).toHaveTextContent('not valid or has expired');
    expect(screen.getByRole('link', { name: 'Request a new link' })).toHaveAttribute(
      'href',
      '/forgot-password'
    );
  });

  it('explains a password the server refuses', async () => {
    mocked.confirmPasswordReset.mockRejectedValue(new ApiError(422, 'Password must not be...'));
    renderAt('/reset-password#token=abc');

    await type(/^New password/, 'demo.user@example.org');
    await type(/^Repeat new password/, 'demo.user@example.org');
    submit('Save new password');

    expect(await screen.findByRole('alert')).toHaveTextContent('not allowed');
  });
});

describe('account', () => {
  function signedIn(hasPassword = true) {
    mocked.fetchMe.mockResolvedValue({ ...testUser, has_password: hasPassword });
    mocked.fetchMyRoles.mockResolvedValue([STUDENT]);
  }

  it('changes the password', async () => {
    signedIn();
    mocked.changePassword.mockResolvedValue();
    renderAt('/account');

    await type(/^Current password/, 'a long enough passphrase');
    await type(/^New password/, 'a brand new passphrase');
    await type(/^Repeat new password/, 'a brand new passphrase');
    submit('Change password');

    expect(await screen.findByRole('status')).toHaveTextContent('Your password has been changed');
    expect(mocked.changePassword).toHaveBeenCalledWith(
      'a long enough passphrase',
      'a brand new passphrase'
    );
    await waitFor(() => expect(screen.getByLabelText(/^Current password/)).toHaveValue(''));
  });

  it('explains a wrong current password', async () => {
    signedIn();
    mocked.changePassword.mockRejectedValue(new ApiError(400, 'Current password is incorrect.'));
    renderAt('/account');

    await type(/^Current password/, 'not my passphrase');
    await type(/^New password/, 'a brand new passphrase');
    await type(/^Repeat new password/, 'a brand new passphrase');
    submit('Change password');

    expect(await screen.findByRole('alert')).toHaveTextContent('current password is not correct');
  });

  it('tells SSO users their password is managed by their organisation', async () => {
    signedIn(false);
    renderAt('/account');

    expect(await screen.findByText(/managed there/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^Current password/)).not.toBeInTheDocument();
  });
});

describe('safeNext', () => {
  it.each([
    ['/search', '/search'],
    ['/a?b=c#d', '/a?b=c#d'],
    [null, '/'],
    ['', '/'],
    ['search', '/'],
    ['//evil.example.com', '/'],
    ['/\\evil.example.com', '/'],
    ['https://evil.example.com', '/'],
    ['/ok\r\nheader', '/'],
  ])('%s -> %s', (target, expected) => {
    expect(safeNext(target)).toBe(expected);
  });
});
