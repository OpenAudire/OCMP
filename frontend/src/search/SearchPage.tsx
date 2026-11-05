import { useState, type FormEvent } from 'react';
import {
  Alert,
  Badge,
  Button,
  Collapse,
  Group,
  NativeSelect,
  Paper,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconAdjustments, IconSearch } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';

import { fetchSearchFilters, fetchWhereTaught, queryKeys, searchVersion } from '../api/endpoints';
import type {
  SearchGroup,
  SearchHit,
  SearchKind,
  SearchResponse,
  TaughtIn,
  WhereTaughtResponse,
} from '../api/types';
import { defaultVersionId, rememberedVersion, rememberVersion, useProgrammes } from '../curriculum/currentVersion';
import { versionPath } from '../curriculum/paths';
import { versionLabel } from '../curriculum/versions';
import { Permission } from '../session/permissions';
import { useSession } from '../session/useSession';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import { hitPath } from './hitPath';
import { filtersFrom, hasFilters, type SearchFilters } from './searchParams';
import classes from './SearchPage.module.css';

const KIND_ORDER: SearchKind[] = ['objective', 'event', 'module', 'framework_item'];

function placeOf(t: TFunction, hit: SearchHit): string {
  if (hit.kind === 'framework_item') {
    return [hit.code, hit.framework_name].filter(Boolean).join(' · ');
  }
  const parts = [
    hit.phase_name,
    hit.module_code ? `${hit.module_code} ${hit.module_name ?? ''}`.trim() : null,
    hit.kind !== 'event' && hit.event_title ? hit.event_title : null,
    hit.week !== null && hit.week !== undefined ? t('search.week', { week: hit.week }) : null,
  ];
  const place = parts.filter(Boolean).join(' · ');
  if (hit.kind === 'objective' && !place) return t('search.programmeOutcome');
  return place;
}

function MatchedBy({ by }: { by: string[] }) {
  const { t } = useTranslation();
  return (
    <>
      {by.map((name) => (
        <Badge key={name} variant="light" color="gray" size="sm">
          {t(`search.matchedBy.${name}`)}
        </Badge>
      ))}
    </>
  );
}

function HitItem({ versionId, hit }: { versionId: string; hit: SearchHit }) {
  const { t } = useTranslation();
  const { data: session } = useSession();
  const place = placeOf(t, hit);
  // Staff who read drafts open the builder; everyone else opens the explorer.
  const explorer = !session?.permissions.has(Permission.CurriculumView);
  return (
    <li className={classes.hit}>
      <Link to={hitPath(versionId, hit, explorer)} className={classes.hitTitle}>
        {hit.title}
      </Link>
      {place && (
        <Text size="sm" c="dimmed">
          {place}
        </Text>
      )}
      {hit.kind === 'framework_item' && hit.detail && (
        <Text size="sm" className={classes.detail}>
          {hit.detail}
        </Text>
      )}
      <Group gap={6}>
        <MatchedBy by={hit.matched_by} />
        {hit.kind === 'objective' && hit.domain && (
          <Badge variant="outline" color="gray" size="sm">
            {t(`curriculum.domain.${hit.domain}`)}
          </Badge>
        )}
      </Group>
    </li>
  );
}

function Groups({ versionId, groups }: { versionId: string; groups: SearchGroup[] }) {
  const { t } = useTranslation();
  const shown = KIND_ORDER.map((kind) => groups.find((g) => g.kind === kind)).filter(
    (g): g is SearchGroup => g !== undefined && g.hits.length > 0
  );
  return (
    <Stack gap="lg">
      {shown.map((group) => (
        <section key={group.kind} aria-labelledby={`group-${group.kind}`}>
          <Title order={2} id={`group-${group.kind}`} className={classes.groupTitle}>
            {t(`search.kinds.${group.kind}`, { count: group.hits.length })}
          </Title>
          <ul className={classes.hits}>
            {group.hits.map((hit) => (
              <HitItem key={hit.id} versionId={versionId} hit={hit} />
            ))}
          </ul>
          {group.more && (
            <Text size="sm" c="dimmed">
              {t('search.more')}
            </Text>
          )}
        </section>
      ))}
    </Stack>
  );
}

function Notices({ result }: { result: Pick<SearchResponse, 'notice' | 'words' | 'mode'> }) {
  const { t } = useTranslation();
  return (
    <Stack gap="xs">
      {result.notice && (
        <Alert color="gray" variant="light">
          {t(`search.notice.${result.notice}`)}
        </Alert>
      )}
      {result.words === 'some' && (
        <Alert color="ochre" variant="light">
          {t('search.someWords')}
        </Alert>
      )}
    </Stack>
  );
}

function SessionRow({ versionId, row }: { versionId: string; row: TaughtIn }) {
  const { t } = useTranslation();
  const { data: session } = useSession();
  const explorer = !session?.permissions.has(Permission.CurriculumView);
  let target: string;
  if (explorer) {
    target = `/explorer/modules/${row.module_id}${row.event_id ? `?session=${row.event_id}` : ''}`;
  } else {
    target = row.event_id
      ? versionPath(versionId, `event:${row.event_id}`)
      : versionPath(versionId, `module:${row.module_id}`);
  }
  const place = [
    row.phase_name,
    `${row.module_code} ${row.module_name}`,
    row.week !== null ? t('search.week', { week: row.week }) : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <li className={classes.hit}>
      <Link to={target} className={classes.hitTitle}>
        {row.event_title ?? t('search.moduleLevel', { code: row.module_code })}
      </Link>
      <Text size="sm" c="dimmed">
        {place}
      </Text>
      <Group gap={6}>
        {row.why.map((why) => (
          <Badge key={why} variant="light" color="gray" size="sm">
            {why.startsWith('framework ')
              ? t('search.why.framework', { code: why.slice('framework '.length) })
              : t(`search.why.${why}`)}
          </Badge>
        ))}
      </Group>
      {row.objectives.length > 0 && (
        <ul className={classes.objectives}>
          {row.objectives.map((objective) => (
            <li key={objective.id}>
              <Text size="sm">{objective.text}</Text>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function WhereTaught({ versionId, found }: { versionId: string; found: WhereTaughtResponse }) {
  const { t } = useTranslation();
  const empty = found.sessions.length === 0 && found.modules.length === 0;
  return (
    <Stack gap="lg">
      <Notices result={found} />
      {empty && <Text>{t('search.whereNone', { query: found.query })}</Text>}
      {found.sessions.length > 0 && (
        <section aria-labelledby="where-sessions">
          <Title order={2} id="where-sessions" className={classes.groupTitle}>
            {t('search.whereSessions', { count: found.sessions.length })}
          </Title>
          <Text size="sm" c="dimmed">
            {t('search.whereOrder')}
          </Text>
          <ol className={classes.hits}>
            {found.sessions.map((row) => (
              <SessionRow key={row.event_id} versionId={versionId} row={row} />
            ))}
          </ol>
          {found.more && (
            <Text size="sm" c="dimmed">
              {t('search.more')}
            </Text>
          )}
        </section>
      )}
      {found.modules.length > 0 && (
        <section aria-labelledby="where-modules">
          <Title order={2} id="where-modules" className={classes.groupTitle}>
            {t('search.whereModules', { count: found.modules.length })}
          </Title>
          <ul className={classes.hits}>
            {found.modules.map((row) => (
              <SessionRow key={row.module_id} versionId={versionId} row={row} />
            ))}
          </ul>
        </section>
      )}
      {found.framework_items.length > 0 && (
        <section aria-labelledby="where-items">
          <Title order={2} id="where-items" className={classes.groupTitle}>
            {t('search.whereItems')}
          </Title>
          <ul className={classes.hits}>
            {found.framework_items.map((hit) => (
              <HitItem key={hit.id} versionId={versionId} hit={hit} />
            ))}
          </ul>
        </section>
      )}
    </Stack>
  );
}

function FilterPanel({
  versionId,
  filters,
  onChange,
}: {
  versionId: string;
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
}) {
  const { t } = useTranslation();
  const options = useQuery({
    queryKey: queryKeys.searchFilters(versionId),
    queryFn: () => fetchSearchFilters(versionId),
  });
  if (options.isLoading) return <LoadingState />;
  if (!options.data) return null;
  const o = options.data;
  const choice = (key: keyof SearchFilters, label: string, items: { id: string; label: string }[]) =>
    items.length === 0 ? null : (
      <NativeSelect
        key={key}
        label={label}
        value={(filters[key] as string) ?? ''}
        onChange={(event) => onChange({ ...filters, [key]: event.currentTarget.value || undefined })}
        data={[{ value: '', label: t('search.anything') }, ...items.map((i) => ({ value: i.id, label: i.label }))]}
      />
    );
  const tagValues = o.tag_lists.flatMap((list) =>
    list.values.map((value) => ({ id: value.id, label: `${list.name}: ${value.label}` }))
  );
  return (
    <div className={classes.filterGrid}>
      {choice('phase', t('search.filters.phase'), o.phases)}
      {choice('module', t('search.filters.module'), o.modules)}
      {choice('format', t('search.filters.format'), o.formats)}
      {choice('tag', t('search.filters.tag'), tagValues)}
      {choice('framework', t('search.filters.framework'), o.frameworks)}
      {choice('level', t('search.filters.level'), o.taxonomy_levels)}
      <NativeSelect
        label={t('search.filters.domain')}
        value={filters.domain ?? ''}
        onChange={(event) =>
          onChange({ ...filters, domain: event.currentTarget.value || undefined })
        }
        data={[
          { value: '', label: t('search.anything') },
          ...o.domains.map((d) => ({ value: d, label: t(`curriculum.domain.${d}`) })),
        ]}
      />
    </div>
  );
}

/** `/search`: words and meaning across a version's objectives, sessions, modules and the
 * framework, with filters, and "Where do we teach this?" in the order things are taught. */
export function SearchPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const programmes = useProgrammes();
  const query = params.get('q') ?? '';
  const view = params.get('view') === 'where' ? 'where' : 'results';
  const filters = filtersFrom(params);
  const versions = (programmes.data ?? []).flatMap((p) =>
    p.versions.map((v) => ({ value: v.id, label: `${p.code} · ${versionLabel(t, v)}` }))
  );
  const versionId =
    params.get('version') ??
    (programmes.data ? defaultVersionId(programmes.data, rememberedVersion()) : null);
  // What is typed but not yet searched; until then the box shows the search in the address.
  const [draft, setDraft] = useState<string | null>(null);
  const text = draft ?? query;
  const [open, setOpen] = useState(hasFilters(filters));

  const update = (changes: Record<string, string | string[] | undefined>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      next.delete(key);
      if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
      else if (value) next.set(key, value);
    }
    setParams(next, { replace: false });
  };
  const setFilters = (next: SearchFilters) =>
    update({
      phase: next.phase,
      module: next.module,
      format: next.format,
      tag: next.tag,
      framework: next.framework,
      level: next.level,
      domain: next.domain,
    });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    update({ q: text.trim() || undefined, version: versionId ?? undefined });
    setDraft(null);
  };

  const ready = versionId !== null && query.trim().length >= 2;
  const results = useQuery({
    queryKey: queryKeys.search(versionId ?? '', query, filters, 'results'),
    queryFn: () => searchVersion(versionId as string, query, filters),
    enabled: ready && view === 'results',
  });
  const where = useQuery({
    queryKey: queryKeys.search(versionId ?? '', query, filters, 'where'),
    queryFn: () => fetchWhereTaught(versionId as string, query, filters),
    enabled: ready && view === 'where',
  });
  const active = view === 'results' ? results : where;
  const total =
    view === 'results'
      ? (results.data?.groups ?? []).reduce((n, g) => n + g.hits.length, 0)
      : 0;

  return (
    <Page title={t('search.title')} description={t('search.description')}>
      <Stack gap="lg">
        <Paper withBorder className={classes.card}>
          <form role="search" onSubmit={submit} className={classes.form}>
            <TextInput
              label={t('search.queryLabel')}
              value={text}
              onChange={(event) => setDraft(event.currentTarget.value)}
              maxLength={200}
              leftSection={<IconSearch size={18} aria-hidden />}
              data-autofocus
            />
            {versions.length > 1 && (
              <NativeSelect
                label={t('search.versionLabel')}
                value={versionId ?? ''}
                onChange={(event) => {
                  rememberVersion(event.currentTarget.value);
                  update({ version: event.currentTarget.value });
                }}
                data={versions}
              />
            )}
            <Group>
              <Button type="submit">{t('search.submit')}</Button>
              <Button
                variant="default"
                leftSection={<IconAdjustments size={18} aria-hidden />}
                aria-expanded={open}
                aria-controls="search-filters"
                onClick={() => setOpen((v) => !v)}
              >
                {hasFilters(filters)
                  ? t('search.filtersOn')
                  : t('search.filters.title')}
              </Button>
            </Group>
          </form>
          <Collapse expanded={open} id="search-filters">
            {versionId && (
              <FilterPanel versionId={versionId} filters={filters} onChange={setFilters} />
            )}
          </Collapse>
        </Paper>

        <SegmentedControl
          aria-label={t('search.viewLabel')}
          value={view}
          onChange={(value) => update({ view: value === 'where' ? 'where' : undefined })}
          data={[
            { value: 'results', label: t('search.view.results') },
            { value: 'where', label: t('search.view.where') },
          ]}
        />

        {!ready && <Text c="dimmed">{t('search.start')}</Text>}
        {ready && active.isLoading && <LoadingState />}
        {ready && active.isError && (
          <ErrorState
            title={t('search.errorTitle')}
            body={t('search.errorBody')}
          />
        )}
        {ready && view === 'results' && results.data && (
          <Stack gap="md" aria-live="polite">
            <Notices result={results.data} />
            {results.data.left_out.length > 0 && (
              <Alert color="gray" variant="light">
                {t('search.leftOut', {
                  kinds: results.data.left_out
                    .map((kind) => t(`search.kindsPlural.${kind}`))
                    .join(', '),
                })}
              </Alert>
            )}
            {total === 0 ? (
              <Text>{t('search.none', { query: results.data.query })}</Text>
            ) : (
              <Groups versionId={versionId as string} groups={results.data.groups} />
            )}
          </Stack>
        )}
        {ready && view === 'where' && where.data && (
          <WhereTaught versionId={versionId as string} found={where.data} />
        )}
      </Stack>
    </Page>
  );
}
