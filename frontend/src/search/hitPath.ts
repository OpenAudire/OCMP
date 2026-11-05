import type { SearchHit } from '../api/types';
import { versionPath } from '../curriculum/paths';
import { ROOT_ID } from '../curriculum/treeModel';

/**
 * Where a hit opens. Staff who read drafts open the session or module in the builder, or the
 * framework item. Everyone else (students, external reviewers) opens the module in the explorer,
 * with the session marked; a framework item has no page for them, so it opens the explorer.
 */
export function hitPath(versionId: string, hit: SearchHit, explorer = false): string {
  if (explorer) {
    if (hit.kind === 'module') return `/explorer/modules/${hit.id}`;
    const moduleId = hit.module_id ?? null;
    if (moduleId) {
      const session = hit.kind === 'event' ? hit.id : hit.event_id;
      return `/explorer/modules/${moduleId}${session ? `?session=${session}` : ''}`;
    }
    return '/explorer';
  }
  if (hit.kind === 'framework_item' && hit.framework_id) {
    return `/frameworks/${hit.framework_id}?item=${hit.id}`;
  }
  if (hit.kind === 'event') return versionPath(versionId, `event:${hit.id}`);
  if (hit.kind === 'module') return versionPath(versionId, `module:${hit.id}`);
  if (hit.event_id) return versionPath(versionId, `event:${hit.event_id}`);
  if (hit.module_id) return versionPath(versionId, `module:${hit.module_id}`);
  return versionPath(versionId, ROOT_ID);
}
