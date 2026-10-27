import { IconAlertTriangle } from '@tabler/icons-react';
import type { Ref } from 'react';
import { useTranslation } from 'react-i18next';

import type { ReviewLink } from '../api/types';
import { confidenceLevel, objectiveWhere } from './format';
import classes from './Review.module.css';

export function Confidence({ value }: { value: number | null }) {
  const { t } = useTranslation();
  if (value === null) {
    return <span className={classes.confidence}>{t('review.confidence.none')}</span>;
  }
  const percent = Math.round(value * 100);
  return (
    <span className={classes.confidence}>
      <span className={classes.confBar} aria-hidden="true">
        <span
          className={classes.confFill}
          data-level={confidenceLevel(value)}
          style={{ width: `${percent}%` }}
        />
      </span>
      <span>
        <strong>{percent}%</strong> {t('review.confidence.word')}
      </span>
    </span>
  );
}

interface ReviewCardProps {
  link: ReviewLink;
  selected: boolean;
  onSelect: () => void;
  buttonRef?: Ref<HTMLButtonElement>;
}

/** One suggestion in the list: the objective, the item it may fit and how sure the source is. */
export function ReviewCard({ link, selected, onSelect, buttonRef }: ReviewCardProps) {
  const { t } = useTranslation();
  return (
    <li>
      <button
        type="button"
        className={classes.card}
        aria-current={selected ? 'true' : undefined}
        onClick={onSelect}
        ref={buttonRef}
      >
        <span className={classes.cardHead}>
          <span>{objectiveWhere(t, link)}</span>
          <span className={classes.chip} data-tone={link.stage === 'first' ? undefined : 'attention'}>
            {t(`review.stage.chip.${link.stage}`)}
          </span>
        </span>
        <span className={classes.objectiveText}>{link.objective.text}</span>
        <span className={classes.target}>
          <span aria-hidden="true">→ </span>
          <span className={classes.code}>{link.item.code}</span> {link.item.title}
        </span>
        <Confidence value={link.confidence} />
        {(link.needs_recheck || link.needs_discussion) && (
          <span className={classes.cardHead}>
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
          </span>
        )}
      </button>
    </li>
  );
}
