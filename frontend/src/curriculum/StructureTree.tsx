import { useRef, useState, type KeyboardEvent } from 'react';
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { visibleNodes, type TreeNode, type VisibleNode } from './treeModel';
import classes from './StructureTree.module.css';

interface StructureTreeProps {
  root: TreeNode;
  label: string;
  selectedId: string;
  expanded: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string, open: boolean) => void;
}

function NodeLabel({ node }: { node: TreeNode }) {
  const { t } = useTranslation();
  const { item } = node;
  switch (item.kind) {
    case 'programme':
      return <span className={classes.name}>{item.structure.programme.name}</span>;
    case 'phase':
      return (
        <>
          <span className={classes.name}>{item.phase.name}</span>
          <span className={classes.meta}>
            {t('curriculum.tree.count', {
              count: item.phase.modules.length,
              noun: t('terms.module', { count: item.phase.modules.length }).toLocaleLowerCase(),
            })}
          </span>
        </>
      );
    case 'longitudinal':
      return <span className={classes.name}>{t('curriculum.tree.longitudinal')}</span>;
    case 'module':
      return (
        <>
          <span className={classes.name}>
            <span className={classes.code}>{item.module.code}</span> {item.module.name}
          </span>
          <span className={classes.meta}>
            {t('curriculum.tree.count', {
              count: item.module.events.length,
              noun: t('terms.learning_event', {
                count: item.module.events.length,
              }).toLocaleLowerCase(),
            })}
          </span>
        </>
      );
    case 'event':
      return (
        <>
          <span className={classes.name}>{item.event.title}</span>
          {item.event.week !== null && (
            <span className={classes.meta}>
              {t('curriculum.tree.week', { week: item.event.week })}
            </span>
          )}
        </>
      );
  }
}

/**
 * The curriculum structure as an ARIA tree (single selection). One item is in the tab
 * order; arrow keys move, Right and Left open and close, Home and End jump, Enter or
 * Space selects. Items are rendered flat with aria-level so each one's name is its own
 * label only.
 */
export function StructureTree({
  root,
  label,
  selectedId,
  expanded,
  onSelect,
  onToggle,
}: StructureTreeProps) {
  const rows = visibleNodes(root, expanded);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLLIElement>());

  // The item in the tab order: the focused one while it is visible, else the selected
  // one, else the root.
  const tabStop =
    rows.find((row) => row.node.id === focusedId)?.node.id ??
    rows.find((row) => row.node.id === selectedId)?.node.id ??
    root.id;

  const focus = (id: string) => {
    setFocusedId(id);
    refs.current.get(id)?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLLIElement>, row: VisibleNode, index: number) => {
    const { node } = row;
    const isOpen = expanded.has(node.id);
    const hasChildren = node.children.length > 0;
    let handled = true;
    switch (event.key) {
      case 'ArrowDown':
        if (index < rows.length - 1) focus(rows[index + 1].node.id);
        break;
      case 'ArrowUp':
        if (index > 0) focus(rows[index - 1].node.id);
        break;
      case 'ArrowRight':
        if (hasChildren && !isOpen) onToggle(node.id, true);
        else if (hasChildren) focus(node.children[0].id);
        break;
      case 'ArrowLeft':
        if (hasChildren && isOpen) onToggle(node.id, false);
        else if (row.parentId) focus(row.parentId);
        break;
      case 'Home':
        focus(rows[0].node.id);
        break;
      case 'End':
        focus(rows[rows.length - 1].node.id);
        break;
      case 'Enter':
      case ' ':
        onSelect(node.id);
        break;
      default:
        handled = false;
    }
    if (handled) event.preventDefault();
  };

  return (
    <ul role="tree" aria-label={label} className={classes.tree}>
      {rows.map((row, index) => {
        const { node } = row;
        const hasChildren = node.children.length > 0;
        const isOpen = expanded.has(node.id);
        const selected = node.id === selectedId;
        return (
          <li
            key={node.id}
            ref={(element) => {
              if (element) refs.current.set(node.id, element);
              else refs.current.delete(node.id);
            }}
            role="treeitem"
            aria-level={row.level}
            aria-posinset={row.posInSet}
            aria-setsize={row.setSize}
            aria-expanded={hasChildren ? isOpen : undefined}
            aria-selected={selected}
            tabIndex={node.id === tabStop ? 0 : -1}
            className={classes.item}
            data-kind={node.item.kind}
            style={{
              paddingInlineStart: `calc(${row.level - 1} * 16px + 8px)`,
            }}
            onFocus={() => setFocusedId(node.id)}
            onKeyDown={(event) => onKeyDown(event, row, index)}
            onClick={() => {
              onSelect(node.id);
              if (hasChildren && !isOpen) onToggle(node.id, true);
            }}
          >
            <span
              className={classes.toggle}
              aria-hidden="true"
              onClick={(event) => {
                if (!hasChildren) return;
                event.stopPropagation();
                onToggle(node.id, !isOpen);
              }}
            >
              {hasChildren &&
                (isOpen ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />)}
            </span>
            <span className={classes.label}>
              <NodeLabel node={node} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}
