import { useState, type ReactNode } from 'react';
import { Button, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';
import { IconPencil, IconPlus, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import {
  fetchLearningEvent,
  fetchModule,
  fetchProgramme,
  fetchProgrammeOutcomes,
  fetchTaxonomyScales,
  queryKeys,
} from '../api/endpoints';
import type {
  Objective,
  StructureEvent,
  StructureModule,
  StructurePhase,
  VersionStructure,
} from '../api/types';
import { objectiveNoun, type EditResult, type ObjectiveOwner } from './editing';
import { ObjectiveDeleteDialog, ObjectiveDialog } from './ObjectiveDialog';
import type { TreeItem } from './treeModel';
import classes from './ItemDetails.module.css';

function useNumber() {
  const { i18n } = useTranslation();
  return (value: number | string, digits = 1) =>
    new Intl.NumberFormat(i18n.language, {
      maximumFractionDigits: digits,
    }).format(Number(value));
}

/** Label and value pairs; values left out (null) are not shown. */
function Facts({ items }: { items: [string, ReactNode | null][] }) {
  const shown = items.filter(([, value]) => value !== null && value !== '');
  if (shown.length === 0) return null;
  return (
    <dl className={classes.facts}>
      {shown.map(([label, value]) => (
        <div key={label} className={classes.fact}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Header({ context, title }: { context?: string; title: ReactNode }) {
  return (
    <Stack gap={6}>
      {context && (
        <Text size="sm" c="dimmed">
          {context}
        </Text>
      )}
      <Title order={2} className={classes.title}>
        {title}
      </Title>
    </Stack>
  );
}

function Description({ text }: { text: string }) {
  return text ? <Text className={classes.description}>{text}</Text> : null;
}

interface ObjectivesProps {
  title: string;
  emptyText: string;
  objectives: Objective[] | undefined;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
  /** Who owns the objectives; with `canEdit` the list offers Add, Edit and Delete. */
  owner: ObjectiveOwner;
  versionId: string;
  canEdit: boolean;
  onSaved: (result: EditResult) => void;
}

/** A short form of the text for button names, so each button is told apart. */
function excerpt(text: string): string {
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

function Objectives({
  title,
  emptyText,
  objectives,
  isPending,
  isError,
  onRetry,
  owner,
  versionId,
  canEdit,
  onSaved,
}: ObjectivesProps) {
  const { t } = useTranslation();
  const noun = objectiveNoun(t, owner);
  const [dialog, setDialog] = useState<'add' | 'edit' | 'delete' | null>(null);
  // The objective being changed; kept while the dialog closes so it does not flash.
  const [current, setCurrent] = useState<Objective | null>(null);
  const open = (kind: 'edit' | 'delete', objective: Objective) => {
    setCurrent(objective);
    setDialog(kind);
  };
  const scales = useQuery({
    queryKey: queryKeys.taxonomyScales,
    queryFn: fetchTaxonomyScales,
    enabled: (objectives ?? []).some((objective) => objective.taxonomy_level_id !== null),
  });
  const levelNames = new Map(
    (scales.data ?? []).flatMap((scale) =>
      scale.levels.map((level) => [level.id, `${scale.name}: ${level.name}`] as const)
    )
  );
  const close = () => setDialog(null);
  const saved = (result: EditResult) => {
    setDialog(null);
    onSaved(result);
  };
  const common = { versionId, owner, onClose: close, onSaved: saved };
  return (
    <Paper withBorder className={classes.card} component="section" aria-label={title}>
      <Group justify="space-between" gap="sm">
        <Title order={3} className={classes.sectionTitle}>
          {title}
        </Title>
        {canEdit && (
          <Button
            variant="default"
            leftSection={<IconPlus size={18} aria-hidden />}
            onClick={() => setDialog('add')}
          >
            {t('curriculum.edit.add', { noun })}
          </Button>
        )}
      </Group>
      {isPending ? (
        <Stack gap={10} aria-busy="true">
          <Text role="status" size="sm" c="dimmed">
            {t('states.loading')}
          </Text>
          <Skeleton height={56} radius={12} />
          <Skeleton height={56} radius={12} />
        </Stack>
      ) : isError ? (
        <Group gap="sm" role="alert">
          <Text size="sm">{t('curriculum.details.objectivesError')}</Text>
          <Button size="compact-md" variant="default" onClick={onRetry}>
            {t('pages.retry')}
          </Button>
        </Group>
      ) : !objectives || objectives.length === 0 ? (
        <Text c="dimmed">{emptyText}</Text>
      ) : (
        <ol className={classes.objectives}>
          {objectives.map((objective) => (
            <li key={objective.id} className={classes.objective}>
              <Text className={classes.objectiveText}>{objective.text}</Text>
              <Group gap={6}>
                <span className={classes.chip}>
                  {objective.domain
                    ? t(`curriculum.domain.${objective.domain}`)
                    : t('curriculum.domain.none')}
                </span>
                {objective.taxonomy_level_id && levelNames.has(objective.taxonomy_level_id) && (
                  <span className={classes.chip}>{levelNames.get(objective.taxonomy_level_id)}</span>
                )}
                <span className={classes.chip}>
                  {t(`curriculum.objectiveStatus.${objective.status}`)}
                </span>
                {objective.parent_ids.length > 0 && (
                  <span className={classes.chip} data-tone="brand">
                    {t('curriculum.details.linkedUp', {
                      count: objective.parent_ids.length,
                    })}
                  </span>
                )}
              </Group>
              {canEdit && (
                <Group gap="sm">
                  <Button
                    variant="default"
                    leftSection={<IconPencil size={18} aria-hidden />}
                    aria-label={t('curriculum.objectives.editOne', {
                      noun,
                      text: excerpt(objective.text),
                    })}
                    onClick={() => open('edit', objective)}
                  >
                    {t('curriculum.edit.edit', { noun })}
                  </Button>
                  <Button
                    variant="default"
                    leftSection={<IconTrash size={18} aria-hidden />}
                    aria-label={t('curriculum.objectives.deleteOne', {
                      noun,
                      text: excerpt(objective.text),
                    })}
                    onClick={() => open('delete', objective)}
                  >
                    {t('curriculum.edit.delete', { noun })}
                  </Button>
                </Group>
              )}
            </li>
          ))}
        </ol>
      )}
      {canEdit && (
        <>
          <ObjectiveDialog opened={dialog === 'add'} {...common} />
          {current && (
            <>
              <ObjectiveDialog opened={dialog === 'edit'} objective={current} {...common} />
              <ObjectiveDeleteDialog opened={dialog === 'delete'} objective={current} {...common} />
            </>
          )}
        </>
      )}
    </Paper>
  );
}

function ProgrammeDetails({
  structure,
  onSaved,
}: {
  structure: VersionStructure;
  onSaved: (result: EditResult) => void;
}) {
  const { t } = useTranslation();
  const number = useNumber();
  const programme = useQuery({
    queryKey: queryKeys.programme(structure.programme.id),
    queryFn: () => fetchProgramme(structure.programme.id),
  });
  const outcomes = useQuery({
    queryKey: queryKeys.programmeOutcomes(structure.version.id),
    queryFn: () => fetchProgrammeOutcomes(structure.version.id),
    enabled: !structure.partial,
  });
  const data = programme.data;
  const code = <span className={classes.mono}>{structure.programme.code}</span>;
  return (
    <>
      <Paper withBorder className={classes.card}>
        <Header title={structure.programme.name} />
        <Facts
          items={[
            [t('curriculum.details.code'), code],
            [
              t('terms.curriculum_version', { count: 1 }),
              t('curriculum.versionLabel', {
                year: structure.version.academic_year,
                status: t(`curriculum.versionStatus.${structure.version.status}`),
              }),
            ],
            [t('curriculum.details.qualification'), data?.qualification_type?.name ?? null],
            [t('curriculum.details.nqfExitLevel'), data?.nqf_exit_level ?? null],
            [
              t('curriculum.details.totalCredits'),
              data?.total_credits != null ? number(data.total_credits) : null,
            ],
            [
              t('curriculum.details.minimumDuration'),
              data?.minimum_duration_years != null
                ? t('curriculum.details.years', {
                    count: Number(data.minimum_duration_years),
                    value: number(data.minimum_duration_years),
                  })
                : null,
            ],
            [t('curriculum.details.saqaId'), data?.saqa_id ?? null],
            [t('curriculum.details.faculty'), data?.faculty_name ?? null],
          ]}
        />
        {programme.isError && (
          <Text size="sm" c="dimmed" role="alert">
            {t('curriculum.details.programmeError')}
          </Text>
        )}
      </Paper>
      {!structure.partial && (
        <Objectives
          title={t('curriculum.details.programmeOutcomes', {
            programme: t('terms.programme', { count: 1 }),
          })}
          emptyText={t('curriculum.details.noOutcomes')}
          objectives={outcomes.data}
          isPending={outcomes.isPending}
          isError={outcomes.isError}
          onRetry={() => void outcomes.refetch()}
          owner={{ kind: 'programme' }}
          versionId={structure.version.id}
          canEdit={structure.can_edit_outcomes}
          onSaved={onSaved}
        />
      )}
    </>
  );
}

function sumCredits(modules: StructureModule[]): number | null {
  const values = modules.filter((m) => m.credits !== null).map((m) => Number(m.credits));
  return values.length ? values.reduce((a, b) => a + b, 0) : null;
}

function GroupDetails({
  title,
  kind,
  modules,
}: {
  title: string;
  kind: string | null;
  modules: StructureModule[];
}) {
  const { t } = useTranslation();
  const number = useNumber();
  const credits = sumCredits(modules);
  const events = modules.reduce((total, m) => total + m.events.length, 0);
  return (
    <Paper withBorder className={classes.card}>
      <Header title={title} />
      <Facts
        items={[
          [t('curriculum.details.kind'), kind],
          [t('terms.module', { count: 2 }), number(modules.length)],
          [t('terms.learning_event', { count: 2 }), number(events)],
          [t('curriculum.details.credits'), credits !== null ? number(credits) : null],
        ]}
      />
    </Paper>
  );
}

function ModuleDetails({
  module,
  phase,
  versionId,
  onSaved,
}: {
  module: StructureModule;
  phase: StructurePhase | null;
  versionId: string;
  onSaved: (result: EditResult) => void;
}) {
  const { t } = useTranslation();
  const number = useNumber();
  const detail = useQuery({
    queryKey: queryKeys.module(module.id),
    queryFn: () => fetchModule(module.id),
    enabled: !module.context_only,
  });
  const data = detail.data;
  const context = phase?.name ?? t('curriculum.tree.longitudinal');
  return (
    <>
      <Paper withBorder className={classes.card}>
        <Header
          context={context}
          title={
            <>
              <span className={classes.mono}>{module.code}</span> {module.name}
            </>
          }
        />
        {module.context_only ? (
          <Text c="dimmed">
            {t('curriculum.details.contextOnly', {
              sessions: t('terms.learning_event', {
                count: 2,
              }).toLocaleLowerCase(),
              module: t('terms.module', { count: 1 }).toLocaleLowerCase(),
            })}
          </Text>
        ) : (
          <>
            <Facts
              items={[
                [
                  t('curriculum.details.credits'),
                  module.credits !== null ? number(module.credits) : null,
                ],
                [t('curriculum.details.nqfLevel'), module.nqf_level],
                [t('terms.learning_event', { count: 2 }), number(module.events.length)],
                [
                  t('curriculum.details.contactTime'),
                  data
                    ? t('curriculum.details.hours', {
                        value: number(data.contact_minutes / 60),
                      })
                    : null,
                ],
                [
                  t('curriculum.details.selfStudy'),
                  data
                    ? t('curriculum.details.hours', {
                        value: number(data.self_study_minutes / 60),
                      })
                    : null,
                ],
              ]}
            />
            {data && <Description text={data.description} />}
          </>
        )}
      </Paper>
      {!module.context_only && (
        <Objectives
          title={t('curriculum.details.moduleOutcomes', {
            module: t('terms.module', { count: 1 }),
          })}
          emptyText={t('curriculum.details.noOutcomes')}
          objectives={data?.outcomes}
          isPending={detail.isPending}
          isError={detail.isError}
          onRetry={() => void detail.refetch()}
          owner={{ kind: 'module', module }}
          versionId={versionId}
          canEdit={data?.can_edit_objectives ?? false}
          onSaved={onSaved}
        />
      )}
    </>
  );
}

function EventDetails({
  event,
  module,
  phase,
  versionId,
  onSaved,
}: {
  event: StructureEvent;
  module: StructureModule;
  phase: StructurePhase | null;
  versionId: string;
  onSaved: (result: EditResult) => void;
}) {
  const { t } = useTranslation();
  const number = useNumber();
  const detail = useQuery({
    queryKey: queryKeys.learningEvent(event.id),
    queryFn: () => fetchLearningEvent(event.id),
  });
  const context = [
    phase?.name ?? t('curriculum.tree.longitudinal'),
    `${module.code} ${module.name}`,
  ].join(' › ');
  return (
    <>
      <Paper withBorder className={classes.card}>
        <Header context={context} title={event.title} />
        <Facts
          items={[
            [t('curriculum.details.format'), event.format ?? t('curriculum.details.notSet')],
            [
              t('curriculum.details.contactTime'),
              t('curriculum.details.minutes', {
                value: number(event.contact_minutes, 0),
              }),
            ],
            [
              t('curriculum.details.selfStudy'),
              t('curriculum.details.minutes', {
                value: number(event.self_study_minutes, 0),
              }),
            ],
            [t('curriculum.details.week'), event.week],
          ]}
        />
        {detail.data && <Description text={detail.data.description} />}
      </Paper>
      <Objectives
        title={t('curriculum.details.objectives')}
        emptyText={t('curriculum.details.noObjectives')}
        objectives={detail.data?.objectives}
        isPending={detail.isPending}
        isError={detail.isError}
        onRetry={() => void detail.refetch()}
        owner={{ kind: 'event', event, module }}
        versionId={versionId}
        canEdit={detail.data?.can_edit_objectives ?? false}
        onSaved={onSaved}
      />
    </>
  );
}

/** Details of the item selected in the structure tree, with its objectives. */
export function ItemDetails({
  item,
  structure,
  onSaved,
}: {
  item: TreeItem;
  structure: VersionStructure;
  onSaved: (result: EditResult) => void;
}) {
  const { t } = useTranslation();
  switch (item.kind) {
    case 'programme':
      return <ProgrammeDetails structure={item.structure} onSaved={onSaved} />;
    case 'phase':
      return (
        <GroupDetails
          title={item.phase.name}
          kind={t(`curriculum.phaseKind.${item.phase.kind}`)}
          modules={item.phase.modules}
        />
      );
    case 'longitudinal':
      return (
        <GroupDetails
          title={t('curriculum.tree.longitudinal')}
          kind={null}
          modules={item.modules}
        />
      );
    case 'module':
      return (
        <ModuleDetails
          module={item.module}
          phase={item.phase}
          versionId={structure.version.id}
          onSaved={onSaved}
        />
      );
    case 'event':
      return (
        <EventDetails
          event={item.event}
          module={item.module}
          phase={item.phase}
          versionId={structure.version.id}
          onSaved={onSaved}
        />
      );
  }
}
