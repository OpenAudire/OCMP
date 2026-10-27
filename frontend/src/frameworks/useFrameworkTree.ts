import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchFrameworkItems } from '../api/endpoints';
import type { FrameworkItemDetail, FrameworkTreeItem } from '../api/types';

/** How many siblings one request brings, and how many around an item that is revealed. */
export const PAGE_SIZE = 100;
const REVEAL_BEFORE = 20;
const REVEAL_SIZE = 50;

export const ROOT = 'root';

/** A run of siblings that has been loaded: `offset` is where it starts among `total`. */
export interface Window {
  offset: number;
  total: number;
  items: FrameworkTreeItem[];
}

export type Windows = Record<string, Window>;

/** One line of the tree as shown: an item, or a button that loads more siblings. */
export type TreeRow =
  | {
      kind: 'item';
      key: string;
      item: FrameworkTreeItem;
      level: number;
      posInSet: number;
      setSize: number;
      parentKey: string;
    }
  | { kind: 'earlier' | 'more'; key: string; level: number; parentKey: string; remaining: number };

/** The rows to show, in reading order, for the windows loaded and the items opened. */
export function treeRows(windows: Windows, expanded: ReadonlySet<string>): TreeRow[] {
  const rows: TreeRow[] = [];
  const walk = (parentKey: string, level: number) => {
    const window = windows[parentKey];
    if (!window) return;
    if (window.offset > 0) {
      rows.push({
        kind: 'earlier',
        key: `earlier:${parentKey}`,
        level,
        parentKey,
        remaining: window.offset,
      });
    }
    window.items.forEach((item, index) => {
      rows.push({
        kind: 'item',
        key: item.id,
        item,
        level,
        posInSet: window.offset + index + 1,
        setSize: window.total,
        parentKey,
      });
      if (expanded.has(item.id)) walk(item.id, level + 1);
    });
    const shown = window.offset + window.items.length;
    if (shown < window.total) {
      rows.push({
        kind: 'more',
        key: `more:${parentKey}`,
        level,
        parentKey,
        remaining: window.total - shown,
      });
    }
  };
  walk(ROOT, 1);
  return rows;
}

function holds(window: Window | undefined, index: number): boolean {
  return !!window && index >= window.offset && index < window.offset + window.items.length;
}

/**
 * The windows of a framework's tree that have been loaded, the items opened and the loading
 * state. Children are read when an item is opened, so a big framework costs one request per
 * opened item (ADR 038). Opening an item in the middle of a long list loads only the siblings
 * around it.
 */
export function useFrameworkTree(frameworkId: string) {
  // Windows loaded after the first one (opened items, "Show more", revealed items) and, once
  // they exist, a replacement for the top level. The first top-level window is a query.
  const [loaded, setLoaded] = useState<Windows>({});
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [loading, setLoading] = useState(0);
  const [failed, setFailed] = useState(false);
  const windowsRef = useRef<Windows>({});

  const top = useQuery({
    queryKey: ['frameworks', frameworkId, 'top-level'],
    queryFn: () => fetchFrameworkItems(frameworkId, { offset: 0, limit: PAGE_SIZE }),
    staleTime: 0,
    gcTime: 0,
  });
  const windows = useMemo<Windows>(
    () => ({
      ...(top.data
        ? { [ROOT]: { offset: top.data.offset, total: top.data.total, items: top.data.items } }
        : {}),
      ...loaded,
    }),
    [top.data, loaded]
  );
  useEffect(() => {
    windowsRef.current = windows;
  }, [windows]);

  const run = useCallback(async <T>(work: () => Promise<T>): Promise<T | undefined> => {
    setLoading((n) => n + 1);
    try {
      return await work();
    } catch {
      setFailed(true);
      return undefined;
    } finally {
      setLoading((n) => n - 1);
    }
  }, []);

  /** Load a run of siblings and join it to what is there, or replace it. */
  const load = useCallback(
    async (parentKey: string, offset: number, limit: number, mode: 'replace' | 'join') => {
      const page = await run(() =>
        fetchFrameworkItems(frameworkId, {
          parentId: parentKey === ROOT ? null : parentKey,
          offset,
          limit,
        })
      );
      if (!page) return;
      const current = windowsRef.current[parentKey];
      let next: Window = { offset: page.offset, total: page.total, items: page.items };
      if (mode === 'join' && current) {
        const start = Math.min(current.offset, page.offset);
        const known = new Map<number, FrameworkTreeItem>();
        current.items.forEach((item, i) => known.set(current.offset + i, item));
        page.items.forEach((item, i) => known.set(page.offset + i, item));
        const items: FrameworkTreeItem[] = [];
        for (let i = start; known.has(i); i += 1) items.push(known.get(i)!);
        next = { offset: start, total: page.total, items };
      }
      windowsRef.current = { ...windowsRef.current, [parentKey]: next };
      setLoaded((previous) => ({ ...previous, [parentKey]: next }));
    },
    [frameworkId, run]
  );

  const open = useCallback(
    (id: string) => {
      setExpanded((prev) => new Set(prev).add(id));
      if (!windowsRef.current[id]) void load(id, 0, PAGE_SIZE, 'replace');
    },
    [load]
  );

  const close = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const showMore = useCallback(
    (parentKey: string) => {
      const window = windowsRef.current[parentKey];
      if (window) void load(parentKey, window.offset + window.items.length, PAGE_SIZE, 'join');
    },
    [load]
  );

  const showEarlier = useCallback(
    (parentKey: string) => {
      const window = windowsRef.current[parentKey];
      if (!window) return;
      const offset = Math.max(0, window.offset - PAGE_SIZE);
      void load(parentKey, offset, window.offset - offset, 'join');
    },
    [load]
  );

  /** Open the tree down to an item: every item above it, with the siblings around each. */
  const reveal = useCallback(
    async (detail: FrameworkItemDetail) => {
      const steps = [
        ...detail.path.map((a) => ({ id: a.id, index: a.sibling_index })),
        { id: detail.id, index: detail.sibling_index },
      ];
      let parentKey = ROOT;
      const opened: string[] = [];
      for (const step of steps) {
        if (!holds(windowsRef.current[parentKey], step.index)) {
          await load(parentKey, Math.max(0, step.index - REVEAL_BEFORE), REVEAL_SIZE, 'replace');
          if (!holds(windowsRef.current[parentKey], step.index)) return false;
        }
        if (step.id === detail.id) break;
        opened.push(step.id);
        parentKey = step.id;
      }
      setExpanded((prev) => new Set([...prev, ...opened]));
      return true;
    },
    [load]
  );

  const has = useCallback(
    (id: string) => Object.values(windows).some((w) => w.items.some((item) => item.id === id)),
    [windows]
  );

  return {
    windows,
    expanded,
    rows: treeRows(windows, expanded),
    loading: loading > 0 || top.isFetching,
    failed: failed || top.isError,
    open,
    close,
    showMore,
    showEarlier,
    reveal,
    has,
  };
}
