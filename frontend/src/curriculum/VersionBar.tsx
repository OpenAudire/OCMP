import { useState } from 'react';
import { Button, Group, Paper, Stack, Text } from '@mantine/core';
import {
  IconArchive,
  IconArrowBackUp,
  IconArrowsDiff,
  IconCopyPlus,
  IconSend,
  IconTrash,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { ProgrammeSummary, VersionStructure } from '../api/types';
import { comparePath } from './paths';
import { CopyForwardDialog, DeleteVersionDialog, StatusDialog } from './VersionDialogs';
import { STATUS_ACTIONS, versionLabel, type StatusAction } from './versions';
import classes from './VersionBar.module.css';

const ACTION_ICONS = {
  publish: IconSend,
  unpublish: IconArrowBackUp,
  archive: IconArchive,
  unarchive: IconSend,
} as const;

interface VersionBarProps {
  structure: VersionStructure;
  /** The programme with the versions the user may see (for compare and delete). */
  programme: ProgrammeSummary | null;
  /** Say what a status change did. */
  onNotice: (message: string) => void;
}

/**
 * The open version's status, with publish, copy forward, compare and delete for the
 * people who may use them (the structure's flags; the API checks every change).
 */
export function VersionBar({ structure, programme, onNotice }: VersionBarProps) {
  const { t, i18n } = useTranslation();
  const version = structure.version;
  const [dialog, setDialog] = useState<StatusAction | 'copy' | 'delete' | null>(null);
  const close = () => setDialog(null);

  const date = version.published_at
    ? new Intl.DateTimeFormat(i18n.language, { dateStyle: 'long' }).format(
        new Date(version.published_at)
      )
    : '';
  const others = programme?.versions.filter((v) => v.id !== version.id) ?? [];
  const nextVersion = others.find((v) => v.id === version.based_on_id) ?? others[0] ?? null;
  // Returning a published version to draft needs more than publishing (and a reason).
  const statusActions = structure.can_change_status
    ? STATUS_ACTIONS[version.status].filter(
        ({ action }) => action !== 'unpublish' || structure.can_unpublish
      )
    : [];

  const buttons = [
    ...statusActions.map(({ action }) => {
      const Icon = ACTION_ICONS[action];
      return (
        <Button
          key={action}
          variant={action === 'publish' ? 'filled' : 'default'}
          leftSection={<Icon size={18} aria-hidden />}
          onClick={() => setDialog(action)}
        >
          {t(`curriculum.versions.action.${action}`)}
        </Button>
      );
    }),
  ];
  if (structure.can_copy_forward) {
    buttons.push(
      <Button
        key="copy"
        variant="default"
        leftSection={<IconCopyPlus size={18} aria-hidden />}
        onClick={() => setDialog('copy')}
      >
        {t('curriculum.versions.action.copyForward')}
      </Button>
    );
  }
  if (!structure.partial && others.length > 0) {
    buttons.push(
      <Button
        key="compare"
        variant="default"
        component={Link}
        to={comparePath(version.id)}
        leftSection={<IconArrowsDiff size={18} aria-hidden />}
      >
        {t('curriculum.versions.action.compare')}
      </Button>
    );
  }
  if (structure.can_copy_forward && version.status === 'draft') {
    buttons.push(
      <Button
        key="delete"
        variant="default"
        leftSection={<IconTrash size={18} aria-hidden />}
        onClick={() => setDialog('delete')}
      >
        {t('curriculum.versions.action.delete')}
      </Button>
    );
  }

  return (
    <Paper
      withBorder
      component="section"
      aria-label={t('curriculum.versions.label', { version: versionLabel(t, version) })}
      className={classes.bar}
    >
      <Stack gap={4} className={classes.text}>
        <Text fw={600}>{versionLabel(t, version)}</Text>
        <Text size="sm" c="dimmed">
          {t(`curriculum.versions.status.${version.status}`, { date })}
        </Text>
      </Stack>
      {buttons.length > 0 && (
        <Group gap="sm" role="group" aria-label={t('curriculum.versions.actions')}>
          {buttons}
        </Group>
      )}
      {statusActions.map(({ action, to }) => (
        <StatusDialog
          key={action}
          opened={dialog === action}
          version={version}
          action={action}
          to={to}
          onClose={close}
          onDone={(message) => {
            close();
            onNotice(message);
          }}
        />
      ))}
      {structure.can_copy_forward && (
        <CopyForwardDialog opened={dialog === 'copy'} version={version} onClose={close} />
      )}
      {structure.can_copy_forward && version.status === 'draft' && (
        <DeleteVersionDialog
          opened={dialog === 'delete'}
          version={version}
          nextVersionId={nextVersion?.id ?? null}
          onClose={close}
        />
      )}
    </Paper>
  );
}
