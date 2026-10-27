import { useState } from 'react';
import { Anchor, Button, Paper, Text, Title } from '@mantine/core';
import { IconPlus, IconSitemap, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';

import { isApiError } from '../api/client';
import { fetchFrameworkLibrary, queryKeys } from '../api/endpoints';
import type { FrameworkSummary } from '../api/types';
import { NoAccessPage } from '../pages/StatusPages';
import { SuccessNotice } from '../pages/SuccessNotice';
import { Page } from '../ui/Page';
import { EmptyState, ErrorState, LoadingState } from '../ui/States';
import { DeleteFrameworkDialog } from './DeleteFrameworkDialog';
import classes from './Frameworks.module.css';

/** The versions of one framework (same key): the active one stands for the group. */
interface Group {
  key: string;
  versions: FrameworkSummary[];
  main: FrameworkSummary;
}

function groupByKey(frameworks: FrameworkSummary[]): Group[] {
  const groups = new Map<string, FrameworkSummary[]>();
  for (const framework of frameworks) {
    groups.set(framework.key, [...(groups.get(framework.key) ?? []), framework]);
  }
  return [...groups.entries()].map(([key, versions]) => ({
    key,
    versions,
    main: versions.find((v) => v.status === 'active') ?? versions[0],
  }));
}

function StatusChip({ status }: { status: FrameworkSummary['status'] }) {
  const { t } = useTranslation();
  return (
    <span className={classes.status} data-status={status}>
      {t(`frameworks.status.${status}`)}
    </span>
  );
}

function Meta({ framework }: { framework: FrameworkSummary }) {
  const { t } = useTranslation();
  if (framework.item_count === 0) return <>{t('frameworks.library.empty')}</>;
  return (
    <>
      {t('frameworks.library.meta', {
        version: framework.version_label,
        items: t('frameworks.library.items', { count: framework.item_count }),
        levels: t('frameworks.library.levels', { count: framework.level_count }),
      })}
    </>
  );
}

function Cards({
  groups,
  selected,
  onPick,
}: {
  groups: Group[];
  selected: string;
  onPick: (key: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className={classes.cards} aria-label={t('frameworks.library.listLabel')}>
      {groups.map((group) => (
        <li key={group.key}>
          <button
            type="button"
            className={classes.card}
            aria-pressed={group.key === selected}
            onClick={() => onPick(group.key)}
          >
            <span className={classes.cardTop}>
              <span className={classes.kind}>{t(`frameworks.profile.${group.main.profile}`)}</span>
              <StatusChip status={group.main.status} />
            </span>
            <span className={classes.cardName}>{group.main.name}</span>
            <span className={classes.cardMeta}>
              <Meta framework={group.main} />
              {group.versions.length > 1 && (
                <>
                  {' · '}
                  {t('frameworks.library.versions', { count: group.versions.length })}
                </>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Details({
  group,
  canManage,
  onDelete,
}: {
  group: Group;
  canManage: boolean;
  onDelete: (framework: FrameworkSummary) => void;
}) {
  const { t } = useTranslation();
  const { main } = group;
  const stats: [number, string][] = [
    [main.item_count, t('frameworks.library.statItems')],
    [main.top_level_count, t('frameworks.library.statGroups')],
    [main.level_count, t('frameworks.library.statLevels')],
    [group.versions.length, t('frameworks.library.statVersions')],
  ];
  return (
    <Paper
      withBorder
      className={classes.details}
      component="section"
      aria-label={t('frameworks.library.detailsLabel')}
    >
      <div>
        <div className={classes.eyebrow}>{t(`frameworks.profile.${main.profile}`)}</div>
        <Title order={2} size="h3">
          {main.name}
        </Title>
        {main.description && <p className={classes.about}>{main.description}</p>}
      </div>
      <ul className={classes.stats} aria-label={t('frameworks.library.stats')}>
        {stats.map(([number, label]) => (
          <li key={label} className={classes.stat}>
            <span className={classes.statNumber}>{number.toLocaleString()}</span>
            <span className={classes.statLabel}>{label}</span>
          </li>
        ))}
      </ul>
      <dl className={classes.facts}>
        <div>
          <dt>{t('frameworks.library.publisher')}</dt>
          <dd>{main.publisher}</dd>
        </div>
        {main.url && (
          <div>
            <dt>{t('frameworks.library.website')}</dt>
            <dd>
              <Anchor href={main.url} target="_blank" rel="noopener noreferrer" size="sm">
                {main.url}
              </Anchor>
            </dd>
          </div>
        )}
      </dl>
      <div>
        <div className={classes.eyebrow}>{t('frameworks.library.licence')}</div>
        <p className={classes.licence}>{main.licence_note || t('frameworks.library.noLicence')}</p>
      </div>
      <div>
        <div className={classes.eyebrow}>{t('frameworks.library.versionsTitle')}</div>
        <ul className={classes.versions}>
          {group.versions.map((version) => (
            <li key={version.id} className={classes.version}>
              <span className={classes.versionName}>
                {t('frameworks.library.versionLine', { version: version.version_label })}
              </span>
              <StatusChip status={version.status} />
              <Text size="sm" c="dimmed">
                {t('frameworks.library.items', { count: version.item_count })}
              </Text>
              <span className={classes.versionActions}>
                <Button
                  component={Link}
                  to={`/frameworks/${version.id}`}
                  variant="default"
                  aria-label={t('frameworks.library.browseLabel', {
                    name: version.name,
                    version: version.version_label,
                  })}
                >
                  {t('frameworks.library.browse')}
                </Button>
                {canManage && (
                  <Button
                    variant="default"
                    color="red"
                    leftSection={<IconTrash size={16} aria-hidden="true" />}
                    aria-label={t('frameworks.library.deleteLabel', {
                      name: version.name,
                      version: version.version_label,
                    })}
                    onClick={() => onDelete(version)}
                  >
                    {t('frameworks.library.delete')}
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Paper>
  );
}

/** `/frameworks`: the framework library. */
export function LibraryPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const library = useQuery({ queryKey: queryKeys.frameworks, queryFn: fetchFrameworkLibrary });
  const [deleting, setDeleting] = useState<FrameworkSummary | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (library.isPending) {
    return (
      <Page title={t('nav.frameworks')} description={t('frameworks.intro')}>
        <LoadingState skeletons={3} />
      </Page>
    );
  }
  if (library.isError) {
    if (isApiError(library.error, 403)) return <NoAccessPage />;
    return (
      <Page title={t('nav.frameworks')} description={t('frameworks.intro')}>
        <ErrorState
          title={t('frameworks.library.loadErrorTitle')}
          body={t('frameworks.library.loadErrorBody')}
          actions={<Button onClick={() => void library.refetch()}>{t('frameworks.retry')}</Button>}
        />
      </Page>
    );
  }

  const { frameworks, can_manage: canManage } = library.data;
  const groups = groupByKey(frameworks);
  const selected = groups.find((g) => g.key === params.get('framework')) ?? groups[0];
  const importLink = canManage && (
    <Button component={Link} to="/import" leftSection={<IconPlus size={18} aria-hidden="true" />}>
      {t('frameworks.import')}
    </Button>
  );

  return (
    <Page title={t('nav.frameworks')} description={t('frameworks.intro')}>
      {importLink && <div>{importLink}</div>}
      {notice && <SuccessNotice>{notice}</SuccessNotice>}
      {groups.length === 0 ? (
        <EmptyState
          icon={IconSitemap}
          title={t('frameworks.library.emptyTitle')}
          body={t(
            canManage ? 'frameworks.library.emptyBody' : 'frameworks.library.emptyBodyReader'
          )}
        />
      ) : (
        <div className={classes.layout}>
          <Cards
            groups={groups}
            selected={selected.key}
            onPick={(key) =>
              setParams(
                (previous) => {
                  const next = new URLSearchParams(previous);
                  next.set('framework', key);
                  return next;
                },
                { replace: true }
              )
            }
          />
          <Details group={selected} canManage={canManage} onDelete={setDeleting} />
        </div>
      )}
      {canManage && (
        <Paper withBorder className={classes.note}>
          <Title order={2} size="h4">
            {t('frameworks.library.templatesTitle')}
          </Title>
          <Text size="sm">{t('frameworks.library.templatesBody')}</Text>
          <div>
            <Button component={Link} to="/import" variant="default">
              {t('frameworks.library.templatesLink')}
            </Button>
          </div>
        </Paper>
      )}
      {deleting && (
        <DeleteFrameworkDialog
          framework={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={(framework) => {
            setDeleting(null);
            setNotice(
              t('frameworks.library.deleted', {
                name: framework.name,
                version: framework.version_label,
              })
            );
          }}
        />
      )}
    </Page>
  );
}
