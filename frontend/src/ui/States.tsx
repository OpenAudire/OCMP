import type { ReactNode } from 'react';
import { Paper, Progress, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, type TablerIcon } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import classes from './States.module.css';

/**
 * Empty, loading and error states (docs/mockups/States.dc.html). Each says what is
 * happening and offers the next step. Titles are h2: they sit inside a page.
 */

interface EmptyStateProps {
  icon: TablerIcon;
  title: string;
  body: ReactNode;
  /** Buttons or links, primary first. */
  actions?: ReactNode;
}

export function EmptyState({ icon: Icon, title, body, actions }: EmptyStateProps) {
  return (
    <Paper withBorder className={classes.card}>
      <span className={classes.tile} aria-hidden="true">
        <Icon size={30} stroke={1.8} />
      </span>
      <Title order={2}>{title}</Title>
      <Text c="dimmed" className={classes.body}>
        {body}
      </Text>
      {actions && <div className={classes.actions}>{actions}</div>}
    </Paper>
  );
}

interface LoadingStateProps {
  title?: string;
  /** Known progress: 0-100 with a label such as "46 of 112 objectives". */
  progress?: { value: number; label: string; detail?: string };
  /** What the person can do meanwhile. */
  note?: ReactNode;
  /** Placeholder cards that stand in for the content. */
  skeletons?: number;
}

export function LoadingState({ title, progress, note, skeletons = 2 }: LoadingStateProps) {
  const { t } = useTranslation();
  return (
    <Paper withBorder className={classes.card} aria-busy="true">
      {title && <Title order={2}>{title}</Title>}
      {progress ? (
        <Stack gap={8}>
          <div className={classes.progressText}>
            <span>{progress.label}</span>
            {progress.detail && <Text c="dimmed" span size="sm">{progress.detail}</Text>}
          </div>
          <Progress
            value={progress.value}
            size={10}
            radius={5}
            aria-label={title ?? t('states.loading')}
          />
        </Stack>
      ) : (
        <Text role="status" c="dimmed" size="sm">
          {t('states.loading')}
        </Text>
      )}
      <div aria-hidden="true" className={classes.skeletons}>
        {Array.from({ length: skeletons }, (_, index) => (
          <div key={index} className={classes.skeletonCard}>
            <span className={classes.skeleton} style={{ width: '40%', height: 10 }} />
            <span className={classes.skeleton} style={{ width: '90%', height: 14 }} />
            <span className={classes.skeleton} style={{ width: '65%', height: 14 }} />
          </div>
        ))}
      </div>
      {note && (
        <Text c="dimmed" size="sm" className={classes.note}>
          {note}
        </Text>
      )}
    </Paper>
  );
}

interface ErrorStateProps {
  title: string;
  /** What happened, and that nothing was lost when that is true. */
  body: ReactNode;
  /** Who can fix it, or how to carry on. */
  hint?: ReactNode;
  actions?: ReactNode;
}

export function ErrorState({ title, body, hint, actions }: ErrorStateProps) {
  return (
    <Paper withBorder className={classes.card} data-tone="warm" role="alert">
      <span className={classes.tile} aria-hidden="true">
        <IconAlertTriangle size={30} stroke={1.8} />
      </span>
      <Title order={2}>{title}</Title>
      <Text c="dimmed" className={classes.body}>
        {body}
      </Text>
      {hint && <div className={classes.hint}>{hint}</div>}
      {actions && <div className={classes.actions}>{actions}</div>}
    </Paper>
  );
}
