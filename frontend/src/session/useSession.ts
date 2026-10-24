import { useQuery } from '@tanstack/react-query';

import { isApiError } from '../api/client';
import { fetchMe, fetchMyRoles, queryKeys } from '../api/endpoints';
import type { RoleAssignment, User } from '../api/types';
import { collectPermissions } from './permissions';

export interface Session {
  user: User;
  roles: RoleAssignment[];
  /** Permissions held at any scope (for deciding what to show). */
  permissions: ReadonlySet<string>;
}

/** Load the signed-in user; resolves to null when nobody is signed in. */
export async function loadSession(): Promise<Session | null> {
  try {
    const [user, roles] = await Promise.all([fetchMe(), fetchMyRoles()]);
    return { user, roles, permissions: collectPermissions(roles.flatMap((r) => r.role.permissions)) };
  } catch (error) {
    if (isApiError(error, 401)) return null;
    throw error;
  }
}

export function useSession() {
  return useQuery({ queryKey: queryKeys.session, queryFn: loadSession, retry: false });
}
