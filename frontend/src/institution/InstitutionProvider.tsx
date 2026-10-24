import { useEffect, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { fetchInstitution, queryKeys } from '../api/endpoints';
import type { Institution } from '../api/types';
import { applyTerminology } from './terminology';
import { InstitutionContext } from './useInstitution';

async function loadInstitution(): Promise<Institution | null> {
  try {
    return await fetchInstitution();
  } catch (error) {
    // 404: not set up yet (first-run wizard); 401: not signed in.
    if (isApiError(error, 401, 404)) return null;
    throw error;
  }
}

/**
 * Loads the institution once signed in, applies its terminology to the
 * translations, and makes its settings available to the app.
 */
export function InstitutionProvider({
  enabled,
  children,
}: {
  enabled: boolean;
  children: ReactNode;
}) {
  const { i18n } = useTranslation();
  const { data } = useQuery({
    queryKey: queryKeys.institution,
    queryFn: loadInstitution,
    enabled,
  });
  const institution = data ?? null;

  useEffect(() => {
    applyTerminology(i18n, institution?.terminology ?? {});
  }, [i18n, institution]);

  return <InstitutionContext.Provider value={institution}>{children}</InstitutionContext.Provider>;
}
