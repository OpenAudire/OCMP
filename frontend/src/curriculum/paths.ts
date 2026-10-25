/** Addresses in the curriculum section. */
export const CURRICULUM_PATH = '/curriculum';

export function versionPath(versionId: string, item?: string): string {
  const path = `${CURRICULUM_PATH}/versions/${versionId}`;
  return item ? `${path}?item=${encodeURIComponent(item)}` : path;
}
