import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as endpoints from '../api/endpoints';
import type {
  AdminUser,
  ApiTokenInfo,
  Institution,
  PermissionInfo,
  ProgrammeSummary,
  RoleAssignment,
  RoleInfo,
} from '../api/types';
import { ApiError } from '../api/client';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { Permission } from '../session/permissions';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchProgrammes: vi.fn(),
  fetchReviewCount: vi.fn(),
  fetchUsers: vi.fn(),
  createUser: vi.fn(),
  fetchUser: vi.fn(),
  updateUser: vi.fn(),
  deleteUser: vi.fn(),
  fetchUserAssignments: vi.fn(),
  fetchRoles: vi.fn(),
  fetchPermissions: vi.fn(),
  createRole: vi.fn(),
  updateRole: vi.fn(),
  deleteRole: vi.fn(),
  createAssignment: vi.fn(),
  deleteAssignment: vi.fn(),
  fetchApiTokens: vi.fn(),
  createApiToken: vi.fn(),
  revokeApiToken: vi.fn(),
  fetchUserApiTokens: vi.fn(),
  updateInstitutionSettings: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

const person = (over: Partial<AdminUser> = {}): AdminUser => ({
  id: 'u2',
  email: 'thandi@example.org',
  display_name: 'Thandi Nkosi',
  is_active: true,
  last_login_at: '2026-11-04T09:30:00Z',
  created_at: '2026-10-01T08:00:00Z',
  has_password: true,
  ...over,
});

const programmes: ProgrammeSummary[] = [
  {
    id: 'p1',
    code: 'BHS',
    name: 'BSc Health Sciences',
    faculty_id: 'f1',
    faculty_name: 'Faculty of Health Sciences',
    status: 'active',
    versions: [],
  },
];

const roles: RoleInfo[] = [
  {
    id: 'r1',
    key: 'curriculum_office',
    name: 'Curriculum office',
    description: 'Runs the curriculum.',
    is_system: true,
    permissions: ['curriculum.view', 'curriculum.edit'],
    scope_types: ['instance', 'faculty'],
    requires_expiry: false,
  },
  {
    id: 'r2',
    key: 'programme_director',
    name: 'Programme director',
    description: '',
    is_system: true,
    permissions: ['curriculum.view'],
    scope_types: ['programme'],
    requires_expiry: false,
  },
  {
    id: 'r3',
    key: 'visiting',
    name: 'Visiting reviewer',
    description: 'Temporary.',
    is_system: false,
    permissions: ['reports.view'],
    scope_types: ['programme'],
    requires_expiry: true,
  },
];

const permissions: PermissionInfo[] = [
  { key: 'curriculum.view', implies: ['curriculum.view_published'] },
  { key: 'reports.view', implies: [] },
];

const assignment: RoleAssignment = {
  id: 'a1',
  user_id: 'u2',
  role: { key: 'curriculum_office', name: 'Curriculum office', permissions: [] },
  scope_type: 'faculty',
  scope_id: 'f1',
  expires_at: null,
  created_at: '2026-10-02T08:00:00Z',
};

const token = (over: Partial<ApiTokenInfo> = {}): ApiTokenInfo => ({
  id: 't1',
  name: 'Nightly export',
  token_prefix: 'ocmp_AbCd12',
  scopes: ['read'],
  created_at: '2026-11-01T08:00:00Z',
  expires_at: '2027-02-01T08:00:00Z',
  last_used_at: null,
  revoked_at: null,
  state: 'active',
  ...over,
});

function signInAs(...keys: string[]) {
  mocked.fetchMyRoles.mockResolvedValue([role('platform_admin', keys)]);
}

beforeEach(() => {
  vi.resetAllMocks();
  void i18n.changeLanguage('en');
  applyTerminology(i18n, {});
  mocked.fetchMe.mockResolvedValue(testUser);
  signInAs(
    Permission.UsersManage,
    Permission.RolesManage,
    Permission.SettingsManage,
    Permission.CurriculumView,
    Permission.CurriculumViewPublished
  );
  mocked.fetchInstitution.mockResolvedValue(testInstitution);
  mocked.fetchProgrammes.mockResolvedValue(programmes);
  mocked.fetchReviewCount.mockResolvedValue({ waiting: 0 } as never);
  mocked.fetchUsers.mockResolvedValue({ items: [person(), person({ id: 'u3', display_name: 'Sipho', email: 'sipho@example.org', is_active: false, last_login_at: null })], total: 2 });
  mocked.fetchUser.mockResolvedValue(person());
  mocked.fetchUserAssignments.mockResolvedValue([assignment]);
  mocked.fetchRoles.mockResolvedValue(roles);
  mocked.fetchPermissions.mockResolvedValue(permissions);
  mocked.fetchApiTokens.mockResolvedValue([]);
  mocked.fetchUserApiTokens.mockResolvedValue([token()]);
});

describe('Admin: people', () => {
  it('lists people with their status and last sign-in, and links to each', async () => {
    renderAt('/admin/users');

    expect(await screen.findByRole('heading', { level: 1, name: 'People' })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Thandi Nkosi' })).toHaveAttribute('href', '/admin/users/u2');
    expect(screen.getByText('Can sign in')).toBeInTheDocument();
    expect(screen.getByText('Cannot sign in')).toBeInTheDocument();
    expect(screen.getByText('Never')).toBeInTheDocument();
    expect(screen.getByText('1 to 2 of 2')).toBeInTheDocument();
  });

  it('searches and starts again from the first page', async () => {
    renderAt('/admin/users');
    await screen.findByRole('link', { name: 'Thandi Nkosi' });

    fireEvent.change(screen.getByLabelText('Search people'), { target: { value: 'thandi' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(mocked.fetchUsers).toHaveBeenLastCalledWith('thandi', 0, 25));
  });

  it('adds a person with an email, a name and a password', async () => {
    mocked.createUser.mockResolvedValue(person({ id: 'u9' }));
    renderAt('/admin/users');
    await screen.findByRole('link', { name: 'Thandi Nkosi' });

    fireEvent.click(screen.getByRole('button', { name: 'Add a person' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Email address/), { target: { value: 'new@example.org' } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: 'New Person' } });
    fireEvent.change(within(dialog).getByLabelText(/^Password/), { target: { value: 'a long passphrase 42' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add person' }));

    await waitFor(() =>
      expect(mocked.createUser).toHaveBeenCalledWith({
        email: 'new@example.org',
        display_name: 'New Person',
        password: 'a long passphrase 42',
      })
    );
  });

  it('shows the server reason when an account cannot be made', async () => {
    mocked.createUser.mockRejectedValue(
      new ApiError(422, 'Password must be at least 12 characters long.')
    );
    renderAt('/admin/users');
    await screen.findByRole('link', { name: 'Thandi Nkosi' });
    fireEvent.click(screen.getByRole('button', { name: 'Add a person' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/Email address/), { target: { value: 'x@example.org' } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: 'X' } });
    fireEvent.change(within(dialog).getByLabelText(/^Password/), { target: { value: 'short' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add person' }));

    expect(await within(dialog).findByRole('alert')).toBeInTheDocument();
  });

  it('is closed to people without the permission', async () => {
    signInAs(Permission.CurriculumView);

    renderAt('/admin/users');

    expect(await screen.findByText(/do not have access|no access|permission/i)).toBeInTheDocument();
    expect(mocked.fetchUsers).not.toHaveBeenCalled();
  });
});

describe('Admin: one person', () => {
  it('shows the roles by place and gives a new one at a programme', async () => {
    mocked.createAssignment.mockResolvedValue({ ...assignment, id: 'a2' });
    renderAt('/admin/users/u2');

    expect(await screen.findByRole('heading', { level: 1, name: 'Thandi Nkosi' })).toBeInTheDocument();
    const roleSection = (await screen.findByRole('heading', { level: 2, name: 'Roles' })).closest('section') as HTMLElement;
    expect(await within(roleSection).findByText('Faculty: Faculty of Health Sciences')).toBeInTheDocument();

    await within(roleSection).findByRole('option', { name: 'Programme director' });
    fireEvent.change(within(roleSection).getByLabelText('Role'), { target: { value: 'programme_director' } });
    expect(within(roleSection).getByRole('option', { name: 'A programme' })).toBeInTheDocument();
    fireEvent.click(within(roleSection).getByRole('button', { name: 'Give the role' }));

    await waitFor(() =>
      expect(mocked.createAssignment).toHaveBeenCalledWith({
        user_id: 'u2',
        role_key: 'programme_director',
        scope_type: 'programme',
        scope_id: 'p1',
        expires_at: null,
      })
    );
  });

  it('needs an end date for a role that asks for one', async () => {
    renderAt('/admin/users/u2');
    const roleSection = (await screen.findByRole('heading', { level: 2, name: 'Roles' })).closest('section') as HTMLElement;
    await within(roleSection).findByText('Faculty: Faculty of Health Sciences');

    await within(roleSection).findByRole('option', { name: 'Visiting reviewer' });
    fireEvent.change(within(roleSection).getByLabelText('Role'), { target: { value: 'visiting' } });

    expect(within(roleSection).getByRole('button', { name: 'Give the role' })).toBeDisabled();
    fireEvent.change(within(roleSection).getByLabelText('Ends on (required for this role)'), {
      target: { value: '2027-03-01' },
    });
    expect(within(roleSection).getByRole('button', { name: 'Give the role' })).toBeEnabled();
  });

  it('removes a role after asking', async () => {
    mocked.deleteAssignment.mockResolvedValue(undefined);
    renderAt('/admin/users/u2');
    fireEvent.click(await screen.findByRole('button', { name: 'Remove the role Curriculum office' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove' }));

    await waitFor(() => expect(mocked.deleteAssignment).toHaveBeenCalledWith('a1'));
  });

  it('deactivates after asking and says what happens', async () => {
    mocked.updateUser.mockResolvedValue(person({ is_active: false }));
    renderAt('/admin/users/u2');
    fireEvent.click(await screen.findByRole('button', { name: 'Deactivate' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/signed out everywhere/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }));

    await waitFor(() => expect(mocked.updateUser).toHaveBeenCalledWith('u2', { is_active: false }));
  });

  it('cannot deactivate or delete your own account', async () => {
    mocked.fetchUser.mockResolvedValue(person({ id: testUser.id }));
    renderAt(`/admin/users/${testUser.id}`);

    expect(await screen.findByRole('button', { name: 'Deactivate' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Delete account' })).toBeDisabled();
  });

  it("lists the person's tokens so an administrator can revoke one", async () => {
    mocked.revokeApiToken.mockResolvedValue(undefined);
    renderAt('/admin/users/u2');

    fireEvent.click(await screen.findByRole('button', { name: 'Revoke the token Nightly export' }));

    await waitFor(() => expect(mocked.revokeApiToken).toHaveBeenCalledWith('t1'));
  });

  it('says so when the person is not found', async () => {
    mocked.fetchUser.mockRejectedValue(new ApiError(404, 'Not found.'));

    renderAt('/admin/users/nobody');

    expect(await screen.findByText('This person was not found')).toBeInTheDocument();
  });
});

describe('Admin: roles', () => {
  it('lists built-in and own roles; built-in ones are read only', async () => {
    renderAt('/admin/roles');

    expect(await screen.findByText('Visiting reviewer')).toBeInTheDocument();
    expect(screen.getAllByText('Built in')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Delete the role Visiting reviewer' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete the role Curriculum office' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'View the role Curriculum office' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/built-in role/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Name/)).toHaveAttribute('readonly');
  });

  it('makes a role from a key, a name, places and permissions', async () => {
    mocked.createRole.mockResolvedValue(roles[2]);
    renderAt('/admin/roles');
    await screen.findByText('Visiting reviewer');

    fireEvent.click(screen.getByRole('button', { name: 'Make a role' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Key/), { target: { value: 'observer' } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: 'Observer' } });
    fireEvent.click(within(dialog).getByLabelText('reports.view'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Make a role' }));

    await waitFor(() =>
      expect(mocked.createRole).toHaveBeenCalledWith({
        key: 'observer',
        name: 'Observer',
        description: '',
        permissions: ['reports.view'],
        scope_types: ['instance'],
        requires_expiry: false,
      })
    );
  });

  it('deletes an own role after asking', async () => {
    mocked.deleteRole.mockResolvedValue(undefined);
    renderAt('/admin/roles');
    fireEvent.click(await screen.findByRole('button', { name: 'Delete the role Visiting reviewer' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(mocked.deleteRole).toHaveBeenCalledWith('visiting'));
  });
});

describe('Admin: institution settings', () => {
  const institution: Institution = {
    ...testInstitution,
    mapping: { four_eyes: false, second_review_for_rejects: false, bulk_accept_min_percent: 80, bulk_accept_max_links: 200, ai_min_coverage: 1, ai_prefer_specific_item: true },
    credits: { hours_per_credit: 10, tolerance_percent: 10, credits_per_year: 120, min_exit_level_credits: null },
    coverage: { multiple_match_n: 3, subordinate_min_percent: 50, weighted_low_percent: 40, repeat_min_sessions: 4, repeat_spread: 1.5 },
  };

  beforeEach(() => {
    mocked.fetchInstitution.mockResolvedValue(institution);
    mocked.updateInstitutionSettings.mockImplementation(async () => institution);
  });

  it('saves one block at a time with the whole block', async () => {
    renderAt('/admin/settings');
    const section = (await screen.findByRole('heading', { level: 2, name: 'Credits and notional hours' })).closest('section') as HTMLElement;

    fireEvent.change(within(section).getByLabelText(/Tolerance/), { target: { value: '15' } });
    fireEvent.click(within(section).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(mocked.updateInstitutionSettings).toHaveBeenCalledWith({
        credits: { hours_per_credit: 10, tolerance_percent: 15, credits_per_year: 120, min_exit_level_credits: null },
      })
    );
    expect(await within(section).findByText('Saved.')).toBeInTheDocument();
  });

  it('has the student competency view off until it is switched on', async () => {
    renderAt('/admin/settings');
    const section = (await screen.findByRole('heading', { level: 2, name: 'Student explorer' })).closest('section') as HTMLElement;
    const toggle = within(section).getByRole('switch', { name: /where this year builds each competency/ });
    expect(toggle).not.toBeChecked();

    fireEvent.click(toggle);
    fireEvent.click(within(section).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(mocked.updateInstitutionSettings).toHaveBeenCalledWith({
        explorer: { show_competency_view: true },
      })
    );
  });

  it('keeps a switch in the block it belongs to', async () => {
    renderAt('/admin/settings');
    const section = (await screen.findByRole('heading', { level: 2, name: 'Mapping and review' })).closest('section') as HTMLElement;

    fireEvent.click(within(section).getByRole('switch', { name: /Second review for accepted links/ }));
    fireEvent.click(within(section).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(mocked.updateInstitutionSettings).toHaveBeenCalledWith({
        mapping: expect.objectContaining({ four_eyes: true, second_review_for_rejects: false }),
      })
    );
  });

  it('sends the terms with both words filled in and keeps the existing ones', async () => {
    renderAt('/admin/settings');
    const section = (await screen.findByRole('heading', { level: 2, name: 'Words for curriculum things' })).closest('section') as HTMLElement;
    const phase = within(
      within(section).getByText('Phase', { selector: 'legend' }).closest('fieldset') as HTMLElement
    );

    fireEvent.change(phase.getByLabelText('Singular'), { target: { value: 'Block' } });
    expect(await within(section).findByText(/both the singular and the plural/)).toBeInTheDocument();
    fireEvent.change(phase.getByLabelText('Plural'), { target: { value: 'Blocks' } });
    fireEvent.click(within(section).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(mocked.updateInstitutionSettings).toHaveBeenCalledWith({
        // The institution's existing words stay; the new pair is added.
        terminology: {
          module: { singular: 'Course', plural: 'Courses' },
          phase: { singular: 'Block', plural: 'Blocks' },
        },
      })
    );
  });

  it("shows the server's reason when a value is refused", async () => {
    mocked.updateInstitutionSettings.mockRejectedValue(
      new ApiError(422, 'tolerance_percent: must be at most 100')
    );
    renderAt('/admin/settings');
    const section = (await screen.findByRole('heading', { level: 2, name: 'Credits and notional hours' })).closest('section') as HTMLElement;

    fireEvent.click(within(section).getByRole('button', { name: 'Save' }));

    expect(await within(section).findByRole('alert')).toBeInTheDocument();
  });
});

describe('Account: API tokens', () => {
  it('makes a token, shows it once and never lists it', async () => {
    mocked.createApiToken.mockResolvedValue({ ...token(), token: 'ocmp_SECRETSECRETSECRET' });
    renderAt('/account');
    fireEvent.click(await screen.findByRole('button', { name: 'Make a token' }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: 'Nightly export' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Make token' }));

    await waitFor(() =>
      expect(mocked.createApiToken).toHaveBeenCalledWith({
        name: 'Nightly export',
        scopes: ['read'],
        days: 90,
      })
    );
    const shown = await screen.findByTestId('new-token');
    expect(shown).toHaveTextContent('ocmp_SECRETSECRETSECRET');
    expect(screen.getByText(/shown only this once/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'I have copied it' }));
    await waitFor(() => expect(screen.queryByTestId('new-token')).not.toBeInTheDocument());
  });

  it('lists tokens by name and start only, with their state, and revokes one', async () => {
    mocked.fetchApiTokens.mockResolvedValue([
      token(),
      token({ id: 't2', name: 'Old', state: 'expired' }),
    ]);
    mocked.revokeApiToken.mockResolvedValue(undefined);
    renderAt('/account');

    expect(await screen.findByText('Nightly export')).toBeInTheDocument();
    expect(screen.getAllByText('ocmp_AbCd12…').length).toBeGreaterThan(0);
    expect(screen.getByText('Expired')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Revoke the token Old' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Revoke the token Nightly export' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke' }));

    await waitFor(() => expect(mocked.revokeApiToken).toHaveBeenCalledWith('t1'));
  });
});
