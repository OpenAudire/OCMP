import { Button, Paper, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import type { WorkspaceLink, WorkspaceObjective } from '../api/types';
import { COVERAGE_LEVELS } from './scale';
import { whereText } from './filters';
import classes from './Mapping.module.css';

/** Coverage as five segments and in words, so the number is never only a colour. */
export function CoverageMeter({ coverage }: { coverage: number | null }) {
  const { t } = useTranslation();
  if (coverage === null) {
    return <span>{t('mapping.coverage.unknown')}</span>;
  }
  return (
    <span className={classes.coverageRow}>
      <span className={classes.meter} aria-hidden="true">
        {COVERAGE_LEVELS.filter((level) => level > 0).map((level) => (
          <span key={level} className={classes.segment} data-on={level <= coverage} />
        ))}
      </span>
      <span>
        {t('mapping.coverage.value', {
          value: coverage,
          label: t(`mapping.coverage.levels.${coverage}`),
        })}
      </span>
    </span>
  );
}

interface LinkCardProps {
  link: WorkspaceLink;
  canEdit: boolean;
  canReview: boolean;
  onEdit: (link: WorkspaceLink) => void;
  onRemove: (link: WorkspaceLink) => void;
  onRecheck: (link: WorkspaceLink) => void;
  onShowItem: (link: WorkspaceLink) => void;
}

function LinkCard({
  link,
  canEdit,
  canReview,
  onEdit,
  onRemove,
  onRecheck,
  onShowItem,
}: LinkCardProps) {
  const { t } = useTranslation();
  const name = `${link.item_code} ${link.item_title}`;
  return (
    <li className={classes.linkCard}>
      <Text className={classes.linkTitle}>
        <span className={classes.code}>{link.item_code}</span> {link.item_title}
        <br />
        <Text span size="xs" c="dimmed">
          {link.framework_name} {link.framework_version_label}
        </Text>
      </Text>
      <CoverageMeter coverage={link.coverage} />
      <div className={classes.chips}>
        <span className={classes.chip} data-tone={link.status === 'accepted' ? 'good' : 'attention'}>
          {t(`frameworks.item.linkStatus.${link.status}`)}
        </span>
        <span className={classes.chip}>
          {link.depth_match
            ? t(`mapping.depth.chip.${link.depth_match}`)
            : t('mapping.depth.unknown')}
        </span>
        {link.accept_method === 'bulk' && (
          <span className={classes.chip} data-tone="attention">
            <IconAlertTriangle size={14} aria-hidden="true" />
            {t('review.acceptedInBulk')}
          </span>
        )}
        {link.needs_recheck && (
          <span className={classes.chip} data-tone="attention">
            <IconAlertTriangle size={14} aria-hidden="true" />
            {t('frameworks.item.recheck')}
          </span>
        )}
        {link.needs_discussion && (
          <span className={classes.chip} data-tone="attention">
            <IconAlertTriangle size={14} aria-hidden="true" />
            {t('frameworks.item.discussion')}
          </span>
        )}
      </div>
      {link.rationale && <p className={classes.reason}>{link.rationale}</p>}
      <div className={classes.actions}>
        <Button
          variant="default"
          size="sm"
          onClick={() => onShowItem(link)}
          aria-label={t('mapping.links.showItem', { name })}
        >
          {t('mapping.links.show')}
        </Button>
        {canEdit && (
          <>
            <Button
              variant="default"
              size="sm"
              onClick={() => onEdit(link)}
              aria-label={t('mapping.links.editLabel', { name })}
            >
              {t('mapping.links.edit')}
            </Button>
            <Button
              variant="default"
              size="sm"
              color="red"
              onClick={() => onRemove(link)}
              aria-label={t('mapping.links.removeLabel', { name })}
            >
              {t('mapping.links.remove')}
            </Button>
          </>
        )}
        {canReview && link.needs_recheck && link.status === 'accepted' && (
          <Button
            size="sm"
            onClick={() => onRecheck(link)}
            aria-label={t('mapping.links.recheckLabel', { name })}
          >
            {t('mapping.links.recheck')}
          </Button>
        )}
      </div>
    </li>
  );
}

interface ObjectiveLinksProps {
  objective: WorkspaceObjective | null;
  editable: boolean;
  onEdit: (link: WorkspaceLink) => void;
  onRemove: (link: WorkspaceLink) => void;
  onRecheck: (link: WorkspaceLink) => void;
  onShowItem: (link: WorkspaceLink) => void;
}

/** The middle pane: the selected objective and the framework items it is linked to. */
export function ObjectiveLinks({ objective, editable, ...actions }: ObjectiveLinksProps) {
  const { t } = useTranslation();
  return (
    <Paper withBorder className={classes.pane} component="section" aria-labelledby="links-title">
      <h2 id="links-title" className={classes.paneHeading}>
        {t('mapping.links.title')}
      </h2>
      {!objective ? (
        <Text>{t('mapping.links.select')}</Text>
      ) : (
        <>
          <p className={classes.selectedText}>{objective.text}</p>
          <Text size="sm" c="dimmed">
            {whereText(t, objective)}
          </Text>
          {objective.links.length === 0 ? (
            <Text>{t('mapping.links.none')}</Text>
          ) : (
            <ul className={classes.list} aria-label={t('mapping.links.list')}>
              {objective.links.map((link) => (
                <LinkCard
                  key={link.id}
                  link={link}
                  canEdit={editable && objective.can_edit}
                  canReview={editable && objective.can_review}
                  {...actions}
                />
              ))}
            </ul>
          )}
          {!objective.can_edit && <Text size="sm">{t('mapping.links.cannotEdit')}</Text>}
        </>
      )}
    </Paper>
  );
}
