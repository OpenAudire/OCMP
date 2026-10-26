/** Addresses in the curriculum section. */
export const CURRICULUM_PATH = '/curriculum';

export function versionPath(versionId: string, item?: string): string {
  const path = `${CURRICULUM_PATH}/versions/${versionId}`;
  return item ? `${path}?item=${encodeURIComponent(item)}` : path;
}

/** Compares a version with another one (`base`, or the default choice). */
export function comparePath(versionId: string, base?: string): string {
  const path = `${CURRICULUM_PATH}/versions/${versionId}/compare`;
  return base ? `${path}?base=${encodeURIComponent(base)}` : path;
}

/** Findings of the objective quality checker for every objective the user sees. */
export function qualityPath(versionId: string): string {
  return `${CURRICULUM_PATH}/versions/${versionId}/quality`;
}
