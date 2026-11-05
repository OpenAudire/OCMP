import { Badge, Paper, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { ExplorerSession } from '../api/types';
import classes from './Explorer.module.css';
import { minutesText } from './explorer';

/** One session: what it is called, where it sits and what it sets out to teach. */
export function SessionCard({
  session,
  showModule,
  highlighted,
}: {
  session: ExplorerSession;
  showModule?: boolean;
  highlighted?: boolean;
}) {
  const { t } = useTranslation();
  const time = minutesText(t, session);
  return (
    <Paper
      withBorder
      component="article"
      id={`session-${session.id}`}
      className={classes.session}
      data-highlighted={highlighted ? 'true' : undefined}
      aria-current={highlighted ? 'true' : undefined}
    >
      {showModule && (
        <Text size="sm" className={classes.moduleLine}>
          <Link to={`/explorer/modules/${session.module_id}`}>
            <span className={classes.code}>{session.module_code}</span> {session.module_name}
          </Link>
        </Text>
      )}
      <Title order={3} className={classes.sessionTitle}>
        {session.title}
      </Title>
      <div className={classes.chips}>
        {session.format && (
          <Badge variant="light" color="gray" size="md">
            {session.format}
          </Badge>
        )}
        {time && (
          <Text size="sm" c="dimmed">
            {time}
          </Text>
        )}
      </div>
      {session.description && <Text size="sm">{session.description}</Text>}
      {session.objectives.length > 0 ? (
        <>
          <Text size="sm" fw={600} className={classes.listLabel}>
            {t('explorer.objectives')}
          </Text>
          <ul className={classes.objectives}>
            {session.objectives.map((o) => (
              <li key={o.id}>{o.text}</li>
            ))}
          </ul>
        </>
      ) : (
        <Text size="sm" c="dimmed">
          {t('explorer.noObjectives')}
        </Text>
      )}
    </Paper>
  );
}
