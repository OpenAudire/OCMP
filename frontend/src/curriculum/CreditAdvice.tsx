import { IconAlertTriangle, IconCircleCheck, IconInfoCircle } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { HoursStatus, ModuleHours } from '../api/types';
import { useNumber } from './useNumber';
import classes from './CreditAdvice.module.css';

/**
 * The state of a check as an icon and words, never colour alone: teal when it fits, ochre
 * when it needs attention (ADR 026), plain when there is nothing to compare.
 */
export function StatusLine({
  tone,
  children,
}: {
  tone: 'good' | 'attention' | 'neutral';
  children: ReactNode;
}) {
  const Icon =
    tone === 'good' ? IconCircleCheck : tone === 'attention' ? IconAlertTriangle : IconInfoCircle;
  return (
    <span className={classes.status} data-tone={tone}>
      <Icon size={16} aria-hidden className={classes.icon} />
      <span>{children}</span>
    </span>
  );
}

function hoursTone(status: HoursStatus): 'good' | 'attention' | 'neutral' {
  if (status === 'ok') return 'good';
  return status === 'no_credits' ? 'neutral' : 'attention';
}

/** "Planned hours match the credits" or what differs, in words. */
export function HoursStatusLine({ hours }: { hours: ModuleHours }) {
  const { t } = useTranslation();
  const number = useNumber();
  return (
    <StatusLine tone={hoursTone(hours.status)}>
      {hours.status === 'no_credits'
        ? t('curriculum.credits.status.no_credits')
        : hours.difference_percent === null
          ? t(`curriculum.credits.status.${hours.status === 'ok' ? 'ok_zero' : 'zero'}`, {
              planned: number(hours.planned_hours),
            })
        : t(`curriculum.credits.status.${hours.status}`, {
            planned: number(hours.planned_hours),
            expected: number(hours.expected_hours ?? 0),
            percent: number(Math.abs(Number(hours.difference_percent ?? 0)), 0),
          })}
    </StatusLine>
  );
}
