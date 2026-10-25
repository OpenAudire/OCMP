import { useTranslation } from 'react-i18next';

import classes from './Wordmark.module.css';

/**
 * The two-tone product name: "Curriculum" / "in Context". `onDark` is for the sidebar;
 * otherwise it uses the page's ink and ochre text colours.
 */
export function Wordmark({ onDark = false, size = 'md' }: { onDark?: boolean; size?: 'sm' | 'md' }) {
  const { t } = useTranslation();
  return (
    <span
      className={classes.wordmark}
      data-on-dark={onDark || undefined}
      data-size={size}
      aria-label={t('app.title')}
      role="img"
    >
      <span className={classes.first} aria-hidden="true">
        {t('app.wordmarkFirst')}
      </span>
      <span className={classes.second} aria-hidden="true">
        {t('app.wordmarkSecond')}
      </span>
    </span>
  );
}
