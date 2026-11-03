import { useState } from 'react';
import { Button, Stack, Text } from '@mantine/core';
import { IconCopy } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import type { NearDuplicate } from '../api/types';
import { DialogForm, EditDialog } from './EditDialog';
import { placeOf } from './nearDuplicates';
import classes from './NearDuplicateFlag.module.css';

interface NearDuplicateFlagProps {
  /** The wording of the objective the card shows. */
  text: string;
  /** Close matches, most similar first; never empty. */
  matches: NearDuplicate[];
}

/**
 * The note under an objective that reads almost like another one of its version and level.
 * Advice only: repeating on purpose is allowed. Ochre with an icon and words, never colour
 * alone (ADR 026). "Compare" shows the wordings side by side.
 */
export function NearDuplicateFlag({ text, matches }: NearDuplicateFlagProps) {
  const { t } = useTranslation();
  const [comparing, setComparing] = useState(false);
  const [first, ...others] = matches;
  if (!first) return null;
  return (
    <div className={classes.flag} role="group" aria-label={t('curriculum.nearDuplicate.label')}>
      <IconCopy size={18} aria-hidden className={classes.icon} />
      <span className={classes.text}>
        <strong>{t('curriculum.nearDuplicate.label')}</strong>{' '}
        {t('curriculum.nearDuplicate.body', { where: placeOf(t, first), percent: first.percent })}
        {others.length > 0 && ` ${t('curriculum.nearDuplicate.more', { count: others.length })}`}
      </span>
      <Button size="compact-md" variant="default" onClick={() => setComparing(true)}>
        {t('curriculum.nearDuplicate.compare')}
      </Button>
      <EditDialog
        opened={comparing}
        title={t('curriculum.nearDuplicate.compareTitle')}
        onClose={() => setComparing(false)}
      >
        <DialogForm submitLabel="" error={null} busy={false} onClose={() => setComparing(false)}>
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              {t('curriculum.nearDuplicate.compareHelp')}
            </Text>
            <section aria-label={t('curriculum.nearDuplicate.thisOne')} className={classes.wording}>
              <Text size="sm" fw={600}>
                {t('curriculum.nearDuplicate.thisOne')}
              </Text>
              <Text>{text}</Text>
            </section>
            {matches.map((match) => (
              <section
                key={match.objective_id}
                aria-label={placeOf(t, match)}
                className={classes.wording}
              >
                <Text size="sm" fw={600}>
                  {t('curriculum.nearDuplicate.otherOne', {
                    where: placeOf(t, match),
                    percent: match.percent,
                  })}
                </Text>
                <Text>{match.text}</Text>
              </section>
            ))}
          </Stack>
        </DialogForm>
      </EditDialog>
    </div>
  );
}
