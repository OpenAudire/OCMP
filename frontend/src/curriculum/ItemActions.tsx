import { isValidElement, useState, type ReactNode } from 'react';
import { Button, Group } from '@mantine/core';
import {
  IconArrowDown,
  IconArrowUp,
  IconCopy,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import type { VersionStructure } from '../api/types';
import { CopyDialog } from './CopyDialog';
import { DeleteDialog, type DeleteTarget } from './DeleteDialog';
import { nounsFor, type EditResult } from './editing';
import { EventDialog } from './EventDialog';
import { ModuleDialog } from './ModuleDialog';
import { PhaseDialog } from './PhaseDialog';
import { canRearrange, isMovable, type Placement } from './reorder';
import type { TreeItem } from './treeModel';

type Dialog =
  | 'addPhase'
  | 'editPhase'
  | 'addModule'
  | 'editModule'
  | 'addEvent'
  | 'editEvent'
  | 'copy'
  | 'delete';

interface ItemActionsProps {
  item: TreeItem;
  structure: VersionStructure;
  onSaved: (result: EditResult) => void;
  /** Where the item sits among its siblings; null for the programme and groups. */
  placement: Placement | null;
  /** Move the item to `position` among its siblings; `focusNotice` when the pressed
   * button becomes unavailable (first or last place). */
  onMove: (position: number, focusNotice: boolean) => void;
  moving: boolean;
}

function ActionButton({
  icon,
  onClick,
  disabled,
  children,
}: {
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <Button variant="default" leftSection={icon} onClick={onClick} disabled={disabled}>
      {children}
    </Button>
  );
}

/**
 * Add, change and delete buttons for the selected item, as far as the user may change
 * it (from the structure's `can_edit` flags; the API checks every change itself).
 */
export function ItemActions({
  item,
  structure,
  onSaved,
  placement,
  onMove,
  moving,
}: ItemActionsProps) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const versionId = structure.version.id;
  const close = () => setDialog(null);
  const saved = (result: EditResult) => {
    setDialog(null);
    onSaved(result);
  };
  const common = { versionId, onClose: close, onSaved: saved };

  const button = (open: Dialog, icon: ReactNode, label: string) => (
    <ActionButton key={open} icon={icon} onClick={() => setDialog(open)}>
      {label}
    </ActionButton>
  );
  const add = (noun: string, open: Dialog) =>
    button(open, <IconPlus size={18} aria-hidden />, t('curriculum.edit.add', { noun }));
  const edit = (noun: string, open: Dialog) =>
    button(open, <IconPencil size={18} aria-hidden />, t('curriculum.edit.edit', { noun }));
  const remove = (noun: string) =>
    button('delete', <IconTrash size={18} aria-hidden />, t('curriculum.edit.delete', { noun }));

  const buttons: ReactNode[] = [];
  let dialogs: ReactNode = null;
  let deleteTarget: DeleteTarget | null = null;

  switch (item.kind) {
    case 'programme':
    case 'longitudinal':
      if (structure.can_edit) {
        if (item.kind === 'programme') buttons.push(add(nouns.phase, 'addPhase'));
        buttons.push(add(nouns.module, 'addModule'));
      }
      dialogs = (
        <>
          <PhaseDialog opened={dialog === 'addPhase'} {...common} />
          <ModuleDialog
            opened={dialog === 'addModule'}
            structure={structure}
            phaseId={item.kind === 'programme' ? (structure.phases[0]?.id ?? null) : null}
            onClose={close}
            onSaved={saved}
          />
        </>
      );
      break;
    case 'phase':
      if (structure.can_edit) {
        buttons.push(
          edit(nouns.phase, 'editPhase'),
          add(nouns.module, 'addModule'),
          remove(nouns.phase)
        );
        deleteTarget = { kind: 'phase', phase: item.phase };
      }
      dialogs = (
        <>
          <PhaseDialog opened={dialog === 'editPhase'} phase={item.phase} {...common} />
          <ModuleDialog
            opened={dialog === 'addModule'}
            structure={structure}
            phaseId={item.phase.id}
            onClose={close}
            onSaved={saved}
          />
        </>
      );
      break;
    case 'module':
      if (item.module.can_edit) {
        buttons.push(edit(nouns.module, 'editModule'), add(nouns.session, 'addEvent'));
      }
      if (structure.can_edit) {
        buttons.push(remove(nouns.module));
        deleteTarget = { kind: 'module', module: item.module, phase: item.phase };
      }
      dialogs = (
        <>
          <ModuleDialog
            opened={dialog === 'editModule'}
            structure={structure}
            module={item.module}
            onClose={close}
            onSaved={saved}
          />
          <EventDialog
            opened={dialog === 'addEvent'}
            module={item.module}
            phase={item.phase}
            {...common}
          />
        </>
      );
      break;
    case 'event':
      if (item.event.can_edit) buttons.push(edit(nouns.session, 'editEvent'));
      if (item.module.can_edit) {
        buttons.push(remove(nouns.session));
        deleteTarget = {
          kind: 'event',
          event: item.event,
          module: item.module,
          phase: item.phase,
        };
      }
      dialogs = (
        <EventDialog
          opened={dialog === 'editEvent'}
          module={item.module}
          phase={item.phase}
          event={item.event}
          {...common}
        />
      );
      break;
  }

  // Move up and down (the keyboard and single-pointer way to reorder), and copy.
  const rearrange = isMovable(item) && canRearrange(item, structure);
  const extra: ReactNode[] = [];
  if (rearrange) {
    const term = item.kind === 'event' ? 'learning_event' : item.kind;
    extra.push(
      button(
        'copy',
        <IconCopy size={18} aria-hidden />,
        t('curriculum.copy.open', { noun: nouns.noun(term) })
      )
    );
  }
  if (rearrange && placement && placement.count > 1) {
    const { index, count } = placement;
    // Not disabled while a move runs: that would take focus away from the button.
    const moveTo = (position: number) => {
      if (!moving) onMove(position, position === 0 || position === count - 1);
    };
    extra.push(
      <ActionButton
        key="up"
        icon={<IconArrowUp size={18} aria-hidden />}
        disabled={index === 0}
        onClick={() => moveTo(index - 1)}
      >
        {t('curriculum.reorder.up')}
      </ActionButton>,
      <ActionButton
        key="down"
        icon={<IconArrowDown size={18} aria-hidden />}
        disabled={index >= count - 1}
        onClick={() => moveTo(index + 1)}
      >
        {t('curriculum.reorder.down')}
      </ActionButton>
    );
  }
  // Delete stays last.
  const deleteAt = buttons.findIndex((node) => isValidElement(node) && node.key === 'delete');
  buttons.splice(deleteAt < 0 ? buttons.length : deleteAt, 0, ...extra);

  if (buttons.length === 0) return null;
  return (
    <>
      <Group gap="sm" role="group" aria-label={t('curriculum.edit.actions')}>
        {buttons}
      </Group>
      {dialogs}
      {rearrange && isMovable(item) && (
        <CopyDialog
          opened={dialog === 'copy'}
          structure={structure}
          item={item}
          onClose={close}
          onSaved={saved}
        />
      )}
      {deleteTarget && (
        <DeleteDialog opened={dialog === 'delete'} target={deleteTarget} {...common} />
      )}
    </>
  );
}
