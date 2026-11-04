import type { SearchHit } from '../api/types';
import { versionPath } from '../curriculum/paths';
import { ROOT_ID } from '../curriculum/treeModel';

/** Where a hit opens: the session or module in the builder, or the framework item. */
export function hitPath(versionId: string, hit: SearchHit): string {
  if (hit.kind === 'framework_item' && hit.framework_id) {
    return `/frameworks/${hit.framework_id}?item=${hit.id}`;
  }
  if (hit.kind === 'event') return versionPath(versionId, `event:${hit.id}`);
  if (hit.kind === 'module') return versionPath(versionId, `module:${hit.id}`);
  if (hit.event_id) return versionPath(versionId, `event:${hit.event_id}`);
  if (hit.module_id) return versionPath(versionId, `module:${hit.module_id}`);
  return versionPath(versionId, ROOT_ID);
}
