import { useId, useState } from 'react';
import { ActionIcon } from '@mantine/core';
import { IconHelp } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { COVERAGE_LEVELS, DEPTH_CHOICES } from './scale';
import classes from './Mapping.module.css';

/** The levels of the scale and the depth choices, defined (the help text of the controls). */
export function ScaleDefinitions() {
  const { t } = useTranslation();
  return (
    <>
      <dl aria-label={t('mapping.help.coverageList')}>
        {COVERAGE_LEVELS.map((level) => (
          <div key={level}>
            <dt>{t('mapping.coverage.level', { value: level })}</dt>
            <dd>{t(`mapping.coverage.levels.${level}`)}</dd>
          </div>
        ))}
      </dl>
      <dl aria-label={t('mapping.help.depthList')}>
        {DEPTH_CHOICES.map((depth) => (
          <div key={depth}>
            <dt>{t(`mapping.depth.names.${depth}`)}</dt>
            <dd>{t(`mapping.depth.definitions.${depth}`)}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

/**
 * The "?" beside coverage and depth (brief, section 11). It opens a block with the help
 * text and the definitions; a button with `aria-expanded`, so it works by keyboard, touch
 * and screen reader alike.
 */
export function MappingHelp() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div>
      <ActionIcon
        variant="default"
        size={44}
        radius="xl"
        aria-label={t('mapping.help.button')}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        <IconHelp size={20} aria-hidden="true" />
      </ActionIcon>
      {open && (
        <div id={id} className={classes.helpBox} role="region" aria-label={t('mapping.help.title')}>
          <p style={{ margin: 0 }}>{t('mapping.help.text')}</p>
          <ScaleDefinitions />
        </div>
      )}
    </div>
  );
}
