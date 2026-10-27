import { Button, Menu } from '@mantine/core';
import { IconCheck, IconChevronDown } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { findVersion, rememberVersion, useProgrammes } from './currentVersion';
import { versionPath } from './paths';
import classes from './VersionSwitcher.module.css';

/**
 * The programme and version being viewed (header of the builder mockup). Opens a
 * menu of every programme with its visible versions, newest first.
 */
export function VersionSwitcher({
  versionId,
  pathFor = versionPath,
}: {
  versionId: string;
  /** Where choosing a version goes; the builder by default. */
  pathFor?: (versionId: string) => string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: programmes } = useProgrammes();
  const current = programmes ? findVersion(programmes, versionId) : null;
  if (!programmes || !current) return null;

  const open = (id: string) => {
    rememberVersion(id);
    navigate(pathFor(id));
  };

  return (
    <Menu position="bottom-start" withinPortal withInitialFocusPlaceholder={false}>
      <Menu.Target>
        <Button
          variant="default"
          rightSection={<IconChevronDown size={16} aria-hidden="true" />}
          className={classes.target}
        >
          <span className={classes.targetText}>
            {t('curriculum.switcher.current', {
              programme: current.programme.name,
              version: t('curriculum.versionLabel', {
                year: current.version.academic_year,
                status: t(`curriculum.versionStatus.${current.version.status}`),
              }),
            })}
          </span>
        </Button>
      </Menu.Target>
      <Menu.Dropdown className={classes.dropdown}>
        {programmes.map((programme) => (
          <div key={programme.id} role="group" aria-label={programme.name}>
            {/* The group's name already says it to screen readers. */}
            <Menu.Label aria-hidden="true">{programme.name}</Menu.Label>
            {programme.versions.map((version) => {
              const selected = version.id === versionId;
              return (
                <Menu.Item
                  key={version.id}
                  aria-current={selected || undefined}
                  leftSection={
                    <IconCheck
                      size={16}
                      aria-hidden="true"
                      style={{ visibility: selected ? 'visible' : 'hidden' }}
                    />
                  }
                  onClick={() => open(version.id)}
                >
                  {t('curriculum.versionLabel', {
                    year: version.academic_year,
                    status: t(`curriculum.versionStatus.${version.status}`),
                  })}
                </Menu.Item>
              );
            })}
          </div>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
