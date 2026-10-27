import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { IconChevronDown, IconChevronRight, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { ROOT, type TreeRow } from './useFrameworkTree';
import classes from './FrameworkTree.module.css';

interface FrameworkTreeProps {
  label: string;
  rows: TreeRow[];
  selectedId: string | null;
  expanded: ReadonlySet<string>;
  busy: boolean;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  onClose: (id: string) => void;
  onShowMore: (parentKey: string) => void;
  onShowEarlier: (parentKey: string) => void;
  /** Move focus to this item once it is in the tree (after "Show in tree"). */
  focusId?: string | null;
  onFocused?: () => void;
}

/**
 * A framework's items as an ARIA tree with one selected item. One row is in the tab order;
 * Up and Down move, Right opens an item or moves to its first child, Left closes it or moves
 * to its parent, Home and End jump, Enter or Space selects. Long lists of siblings arrive
 * in windows, and "Show more" and "Show earlier" rows (also tree items, so the keyboard
 * reaches them) load the rest. Rows are flat with aria-level, as in the curriculum tree.
 */
export function FrameworkTree({
  label,
  rows,
  selectedId,
  expanded,
  busy,
  onSelect,
  onOpen,
  onClose,
  onShowMore,
  onShowEarlier,
  focusId = null,
  onFocused,
}: FrameworkTreeProps) {
  const { t } = useTranslation();
  const [focusedKey, setFocusedKey] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLLIElement>());

  const tabStop =
    rows.find((row) => row.key === focusedKey)?.key ??
    rows.find((row) => row.key === selectedId)?.key ??
    rows[0]?.key;

  const focus = (key: string) => {
    setFocusedKey(key);
    refs.current.get(key)?.focus();
  };

  useEffect(() => {
    if (!focusId) return;
    const element = refs.current.get(focusId);
    if (element) {
      setFocusedKey(focusId);
      element.focus();
      onFocused?.();
    }
  }, [focusId, rows, onFocused]);

  const activate = (row: TreeRow) => {
    if (row.kind === 'item') onSelect(row.item.id);
    else if (row.kind === 'more') onShowMore(row.parentKey);
    else onShowEarlier(row.parentKey);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLLIElement>, row: TreeRow, index: number) => {
    const hasChildren = row.kind === 'item' && row.item.child_count > 0;
    const isOpen = row.kind === 'item' && expanded.has(row.item.id);
    let handled = true;
    switch (event.key) {
      case 'ArrowDown':
        if (index < rows.length - 1) focus(rows[index + 1].key);
        break;
      case 'ArrowUp':
        if (index > 0) focus(rows[index - 1].key);
        break;
      case 'ArrowRight':
        if (row.kind === 'item' && hasChildren && !isOpen) onOpen(row.item.id);
        else if (hasChildren && rows[index + 1]?.level === row.level + 1) {
          focus(rows[index + 1].key);
        }
        break;
      case 'ArrowLeft':
        if (row.kind === 'item' && hasChildren && isOpen) onClose(row.item.id);
        else if (row.parentKey !== ROOT) focus(row.parentKey);
        break;
      case 'Home':
        focus(rows[0].key);
        break;
      case 'End':
        focus(rows[rows.length - 1].key);
        break;
      case 'Enter':
      case ' ':
        activate(row);
        break;
      default:
        handled = false;
    }
    if (handled) event.preventDefault();
  };

  return (
    <ul role="tree" aria-label={label} aria-busy={busy || undefined} className={classes.tree}>
      {rows.map((row, index) => {
        const common = {
          ref: (element: HTMLLIElement | null) => {
            if (element) refs.current.set(row.key, element);
            else refs.current.delete(row.key);
          },
          role: 'treeitem' as const,
          'aria-level': row.level,
          tabIndex: row.key === tabStop ? 0 : -1,
          className: classes.item,
          style: { paddingInlineStart: `calc(${row.level - 1} * 16px + 8px)` },
          onFocus: () => setFocusedKey(row.key),
          onKeyDown: (event: KeyboardEvent<HTMLLIElement>) => onKeyDown(event, row, index),
        };
        if (row.kind !== 'item') {
          const earlier = row.kind === 'earlier';
          return (
            <li
              key={row.key}
              {...common}
              aria-selected={false}
              data-kind="more"
              onClick={() => activate(row)}
            >
              <span className={classes.toggle} aria-hidden="true">
                <IconPlus size={16} />
              </span>
              <span className={classes.label}>
                <span className={classes.name}>
                  {t(earlier ? 'frameworks.tree.earlier' : 'frameworks.tree.more', {
                    count: row.remaining,
                  })}
                </span>
              </span>
            </li>
          );
        }
        const { item } = row;
        const hasChildren = item.child_count > 0;
        const isOpen = expanded.has(item.id);
        return (
          <li
            key={row.key}
            {...common}
            aria-posinset={row.posInSet}
            aria-setsize={row.setSize}
            aria-expanded={hasChildren ? isOpen : undefined}
            aria-selected={item.id === selectedId}
            data-kind="item"
            onClick={() => {
              onSelect(item.id);
              if (hasChildren && !isOpen) onOpen(item.id);
            }}
          >
            <span
              className={classes.toggle}
              aria-hidden="true"
              onClick={(event) => {
                if (!hasChildren) return;
                event.stopPropagation();
                if (isOpen) onClose(item.id);
                else onOpen(item.id);
              }}
            >
              {hasChildren &&
                (isOpen ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />)}
            </span>
            <span className={classes.label}>
              <span className={classes.name}>
                <span className={classes.code}>{item.code}</span> {item.title}
              </span>
              {item.mapped_count > 0 && (
                <span className={classes.meta}>
                  {t('frameworks.tree.mapped', {
                    count: item.mapped_count,
                    noun: t('terms.objective', { count: item.mapped_count }).toLocaleLowerCase(),
                  })}
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
