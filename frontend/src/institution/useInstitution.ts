import { createContext, useContext } from 'react';

import type { Feature, Institution } from '../api/types';

export const InstitutionContext = createContext<Institution | null>(null);

/** The institution's settings, or null before sign-in or before first-run setup. */
export function useInstitution(): Institution | null {
  return useContext(InstitutionContext);
}

/** Whether the institution's profiles enable a feature (e.g. the health profile's reports). */
export function useFeature(feature: Feature): boolean {
  return useInstitution()?.features.includes(feature) ?? false;
}
