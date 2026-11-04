/** The filters of the search screen, kept in the address so a search can be shared. */
export interface SearchFilters {
  phase?: string;
  module?: string;
  format?: string;
  /** One tag value (any list). */
  tag?: string;
  framework?: string;
  level?: string;
  domain?: string;
}

const KEYS: (keyof SearchFilters)[] = [
  'phase',
  'module',
  'format',
  'tag',
  'framework',
  'level',
  'domain',
];

export function filtersFrom(params: URLSearchParams): SearchFilters {
  const filters: SearchFilters = {};
  for (const key of KEYS) {
    const value = params.get(key);
    if (value) filters[key] = value;
  }
  return filters;
}

export function hasFilters(filters: SearchFilters): boolean {
  return KEYS.some((key) => Boolean(filters[key]));
}

/** The query string of the API for these filters (names as the API has them). */
export function filterParams(filters: SearchFilters): Record<string, string> {
  const out: Record<string, string> = {};
  if (filters.phase) out.phase_id = filters.phase;
  if (filters.module) out.module_id = filters.module;
  if (filters.format) out.format_id = filters.format;
  if (filters.tag) out.tag_id = filters.tag;
  if (filters.framework) out.framework_id = filters.framework;
  if (filters.level) out.taxonomy_level_id = filters.level;
  if (filters.domain) out.domain = filters.domain;
  return out;
}
