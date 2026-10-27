import { VisuallyHidden } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { activeNavKey, type NavItem } from './navigation';
import { Wordmark } from './Wordmark';
import classes from './Sidebar.module.css';

/** Above this many the badge reads "99+" (the exact number is on the queue itself). */
const MAX_SHOWN = 99;

interface SidebarProps {
  items: readonly NavItem[];
  pathname: string;
  /** Items waiting for attention, by nav key (the review queue count from Slice 1.13). */
  counts?: Partial<Record<string, number>>;
  institutionName?: string;
  onNavigate?: () => void;
}

/** The dark teal sidebar from the mockups: wordmark, icon navigation, institution. */
export function Sidebar({ items, pathname, counts = {}, institutionName, onNavigate }: SidebarProps) {
  const { t } = useTranslation();
  const active = activeNavKey(items, pathname);

  return (
    <div className={classes.sidebar}>
      <div className={classes.brand}>
        <Wordmark onDark />
      </div>
      <nav aria-label={t('layout.mainNavigation')}>
        <ul className={classes.list}>
          {items.map((item) => {
            const count = counts[item.key];
            return (
              <li key={item.key}>
                <Link
                  to={item.path}
                  className={classes.link}
                  data-sub={item.parent ? true : undefined}
                  aria-current={item.key === active ? 'page' : undefined}
                  onClick={onNavigate}
                >
                  <item.icon size={item.parent ? 18 : 20} stroke={1.8} aria-hidden="true" />
                  <span>{t(`nav.${item.key}`)}</span>
                  {count !== undefined && count > 0 && (
                    <>
                      <span className={classes.count} aria-hidden="true">
                        {count > MAX_SHOWN ? `${MAX_SHOWN}+` : count}
                      </span>
                      <VisuallyHidden>
                        {count > MAX_SHOWN
                          ? t('nav.waitingMany', { count: MAX_SHOWN })
                          : t('nav.waiting', { count })}
                      </VisuallyHidden>
                    </>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {institutionName && <div className={classes.institution}>{institutionName}</div>}
    </div>
  );
}
