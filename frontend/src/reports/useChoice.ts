import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router';

import { fetchFrameworkLibrary, queryKeys } from '../api/endpoints';
import type { CoverageMethod } from '../api/types';
import { defaultVersionId, rememberedVersion, useProgrammes } from '../curriculum/currentVersion';

export const METHODS: CoverageMethod[] = ['single', 'multiple', 'subordinate', 'weighted'];

export interface Choice {
  versionId: string | null;
  frameworkId: string | null;
  method: CoverageMethod;
}

/** The version, framework and method of a report, kept in the address so a report can be shared.
 * The version is the one last opened and the framework the first one in use until chosen. */
export function useChoice(): Choice & { set: (changes: Record<string, string>) => void } {
  const [params, setParams] = useSearchParams();
  const programmes = useProgrammes();
  const library = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });
  const versionId =
    params.get('version') ??
    (programmes.data ? defaultVersionId(programmes.data, rememberedVersion()) : null);
  const usable = (library.data?.frameworks ?? []).filter((f) => f.status !== 'draft');
  const frameworkId = params.get('framework') ?? usable[0]?.id ?? null;
  const asked = params.get('method');
  const method = METHODS.find((m) => m === asked) ?? 'single';
  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  };
  // Put the defaults in the address, so a copied link shows the same report.
  useEffect(() => {
    if (versionId && frameworkId && (!params.get('version') || !params.get('framework'))) {
      set({ version: versionId, framework: frameworkId });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId, frameworkId]);
  return { versionId, frameworkId, method, set };
}
