import { Button, Text } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { checkObjectiveText } from '../api/endpoints';
import type {
  LevelSuggestion,
  ObjectiveDomain,
  QualityCheck,
  QualityFinding,
} from '../api/types';
import classes from './QualityPanel.module.css';

/** How long the wording must rest before it is checked. */
const CHECK_DELAY_MS = 600;

interface QualityPanelProps {
  /** The owner's checking address (see `checkPathFor`). */
  path: string;
  text: string;
  domain: ObjectiveDomain | null;
  taxonomyLevelId: string | null;
  /** Whether the objective links upward; null while that is not known. */
  hasLinks: boolean | null;
  /** Called when the person picks a suggested level. */
  onUseLevel: (suggestion: LevelSuggestion) => void;
}

/** "5 warnings and 2 notes" for the status line; a clean result says so. */
function summaryOf(t: TFunction, check: QualityCheck): string {
  const warnings = check.findings.filter((f) => f.severity === 'warning').length;
  const notes = check.findings.length - warnings;
  return check.findings.length === 0
    ? t('curriculum.quality.clean')
    : t('curriculum.quality.summary', { warnings, notes });
}

/** One finding: the severity is written out and has an icon, never colour alone. */
export function FindingItem({ finding }: { finding: QualityFinding }) {
  const { t } = useTranslation();
  const Icon = finding.severity === 'warning' ? IconAlertTriangle : IconInfoCircle;
  return (
    <li className={classes.finding}>
      <span className={classes.severity} data-severity={finding.severity}>
        <Icon size={14} aria-hidden className={classes.icon} />
        {t(`curriculum.quality.severity.${finding.severity}`)}
      </span>
      <span className={classes.text}>
        <span>{t(finding.message_key, finding.params)}</span>
        {finding.suggestion_key && (
          <Text span size="sm" c="dimmed">
            {t(finding.suggestion_key, finding.params)}
          </Text>
        )}
      </span>
    </li>
  );
}

/**
 * The live quality check under the wording: advisory only, never blocks saving. The
 * wording is checked after a short pause; the status line is a polite live region.
 */
export function QualityPanel({
  path,
  text,
  domain,
  taxonomyLevelId,
  hasLinks,
  onUseLevel,
}: QualityPanelProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const current = { text: text.trim(), domain, taxonomyLevelId, hasLinks };
  const [settled] = useDebouncedValue(current, CHECK_DELAY_MS);
  const waiting =
    settled.text !== current.text ||
    settled.domain !== current.domain ||
    settled.taxonomyLevelId !== current.taxonomyLevelId ||
    settled.hasLinks !== current.hasLinks;
  const check = useQuery({
    queryKey: [
      'objective-check',
      path,
      settled.text,
      settled.domain,
      settled.taxonomyLevelId,
      settled.hasLinks,
    ],
    queryFn: () =>
      checkObjectiveText(path, {
        text: settled.text,
        domain: settled.domain,
        taxonomy_level_id: settled.taxonomyLevelId,
        has_parent_links: settled.hasLinks,
      }),
    enabled: settled.text !== '',
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
  });

  let status: string;
  if (current.text === '') status = t('curriculum.quality.empty');
  else if (check.isError) status = t('curriculum.quality.unavailable');
  else if (waiting || check.isFetching || !check.data) status = t('curriculum.quality.checking');
  else status = summaryOf(t, check.data);

  const result = current.text === '' || check.isError ? null : (check.data ?? null);
  const suggestions = (result?.suggestions ?? []).filter(
    (s) => s.taxonomy_level_id !== taxonomyLevelId
  );

  return (
    <section aria-labelledby={headingId} className={classes.panel}>
      <Text fw={600} id={headingId}>
        {t('curriculum.quality.title')}
      </Text>
      <Text size="sm" c="dimmed">
        {t('curriculum.quality.advisory')}
      </Text>
      <p className={classes.status} role="status">
        {status}
      </p>
      {result && !waiting && result.findings.length > 0 && (
        <ul className={classes.list}>
          {result.findings.map((finding) => (
            <FindingItem key={finding.code} finding={finding} />
          ))}
        </ul>
      )}
      {result && !waiting && suggestions.length > 0 && (
        <div className={classes.levels}>
          <Text size="sm">
            {t('curriculum.quality.levelHint', { verb: result.detected_verb ?? '' })}
          </Text>
          <div className={classes.levelButtons}>
            {suggestions.map((suggestion) => (
              <Button
                key={suggestion.taxonomy_level_id}
                variant="default"
                onClick={() => onUseLevel(suggestion)}
              >
                {t('curriculum.quality.useLevel', {
                  level: suggestion.level_name,
                  scale: suggestion.scale_name,
                })}
              </Button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
