import { Checkbox, NativeSelect, Paper, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import type { WorkspaceObjective } from '../api/types';
import { whereText, type Filters } from './filters';
import classes from './Mapping.module.css';

interface ObjectiveListProps {
  all: WorkspaceObjective[];
  shown: WorkspaceObjective[];
  filters: Filters;
  onFilters: (filters: Filters) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function needsLook(objective: WorkspaceObjective): boolean {
  return objective.links.some((l) => l.status !== 'accepted' || l.needs_recheck);
}

/** The left pane: filters, and the objectives as a list of buttons. */
export function ObjectiveList({
  all,
  shown,
  filters,
  onFilters,
  selectedId,
  onSelect,
}: ObjectiveListProps) {
  const { t } = useTranslation();
  const modules = new Map<string, string>();
  const phases = new Map<string, string>();
  for (const o of all) {
    if (o.module_id) modules.set(o.module_id, `${o.module_code ?? ''} ${o.module_name ?? ''}`.trim());
    if (o.phase_id && o.phase_name) phases.set(o.phase_id, o.phase_name);
  }
  const objectiveNoun = (count: number) => t('terms.objective', { count });
  const moduleNoun = t('terms.module', { count: 1 }).toLocaleLowerCase();
  const hasProgramme = all.some((o) => o.level === 'programme');

  return (
    <Paper withBorder className={classes.pane} component="section" aria-labelledby="objectives-title">
      <h2 id="objectives-title" className={classes.paneHeading}>
        {objectiveNoun(2)}
      </h2>
      <NativeSelect
        label={t('mapping.filters.module', { module: t('terms.module', { count: 1 }) })}
        value={filters.module}
        onChange={(event) => onFilters({ ...filters, module: event.currentTarget.value })}
        data={[
          { value: '', label: t('mapping.filters.allModules', { modules: t('terms.module', { count: 2 }).toLocaleLowerCase() }) },
          ...(hasProgramme ? [{ value: 'programme', label: t('mapping.where.programme') }] : []),
          ...[...modules].map(([value, label]) => ({ value, label })),
        ]}
      />
      {phases.size > 0 && (
        <NativeSelect
          label={t('mapping.filters.phase', { phase: t('terms.phase', { count: 1 }) })}
          value={filters.phase}
          onChange={(event) => onFilters({ ...filters, phase: event.currentTarget.value })}
          data={[
            {
              value: '',
              label: t('mapping.filters.allPhases', {
                phases: t('terms.phase', { count: 2 }).toLocaleLowerCase(),
              }),
            },
            ...[...phases].map(([value, label]) => ({ value, label })),
          ]}
        />
      )}
      <Checkbox
        label={t('mapping.filters.unlinked')}
        checked={filters.unlinkedOnly}
        onChange={(event) => onFilters({ ...filters, unlinkedOnly: event.currentTarget.checked })}
      />
      <Text role="status" size="sm" c="dimmed">
        {t('mapping.filters.count', { shown: shown.length, total: all.length, noun: objectiveNoun(all.length).toLocaleLowerCase() })}
      </Text>
      {shown.length === 0 ? (
        <Text size="sm">
          {t(all.length === 0 ? 'mapping.list.none' : 'mapping.list.noMatch', {
            module: moduleNoun,
            objectives: objectiveNoun(2).toLocaleLowerCase(),
          })}
        </Text>
      ) : (
        <ul className={classes.list} aria-label={objectiveNoun(2)}>
          {shown.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                className={classes.objective}
                aria-current={o.id === selectedId || undefined}
                onClick={() => onSelect(o.id)}
              >
                <span>{o.text}</span>
                <span className={classes.where}>{whereText(t, o)}</span>
                <span className={classes.chips}>
                  <span className={classes.chip} data-tone={o.links.length > 0 ? 'good' : undefined}>
                    {t('mapping.list.links', { count: o.links.length })}
                  </span>
                  {needsLook(o) && (
                    <span className={classes.chip} data-tone="attention">
                      {t('mapping.list.needsLook')}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Paper>
  );
}
