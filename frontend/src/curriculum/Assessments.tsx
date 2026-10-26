import { useState } from 'react';
import { Button, Group, Paper, Skeleton, Stack, Text, Title } from '@mantine/core';
import { IconPencil, IconPlus, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { fetchAssessableObjectives, queryKeys } from '../api/endpoints';
import type { Assessment, AssessmentItem } from '../api/types';
import { AssessmentDeleteDialog, AssessmentDialog, ItemDialog } from './AssessmentDialogs';
import { StatusLine } from './CreditAdvice';
import type { EditResult } from './editing';
import { useNumber } from './useNumber';
import classes from './Assessments.module.css';

interface AssessmentsProps {
  moduleId: string;
  versionId: string;
  assessments: Assessment[] | undefined;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
  canEdit: boolean;
  onSaved: (result: EditResult) => void;
}

type Dialog =
  | { kind: 'add' }
  | { kind: 'edit'; assessment: Assessment }
  | { kind: 'delete'; assessment: Assessment }
  | { kind: 'addItem'; assessment: Assessment }
  | { kind: 'editItem'; assessment: Assessment; item: AssessmentItem }
  | { kind: 'deleteItem'; assessment: Assessment; item: AssessmentItem };

function totalWeight(assessments: Assessment[]): number | null {
  const weights = assessments.filter((a) => a.weight !== null).map((a) => Number(a.weight));
  return weights.length ? weights.reduce((sum, weight) => sum + weight, 0) : null;
}

/** The assessments of a module, their items and the objectives each item assesses. */
export function Assessments({
  moduleId,
  versionId,
  assessments,
  isPending,
  isError,
  onRetry,
  canEdit,
  onSaved,
}: AssessmentsProps) {
  const { t } = useTranslation();
  const number = useNumber();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  // Kept while a dialog closes so it does not flash empty.
  const [last, setLast] = useState<Dialog | null>(null);
  const open = (next: Dialog) => {
    setLast(next);
    setDialog(next);
  };
  const close = () => setDialog(null);
  const saved = (result: EditResult) => {
    setDialog(null);
    onSaved(result);
  };
  const needsObjectives = (assessments ?? []).some((a) =>
    a.items.some((item) => item.objective_ids.length > 0)
  );
  const objectives = useQuery({
    queryKey: queryKeys.assessableObjectives(moduleId),
    queryFn: () => fetchAssessableObjectives(moduleId),
    enabled: needsObjectives,
  });
  const texts = new Map((objectives.data ?? []).map((o) => [o.id, o.text] as const));
  const common = { versionId, onClose: close, onSaved: saved };
  const title = t('curriculum.assessments.title');
  const weight = totalWeight(assessments ?? []);

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
            onClick={() => open({ kind: 'add' })}
          >
            {t('curriculum.assessments.addAssessment')}
          </Button>
        )}
      </Group>
      {isPending ? (
        <Stack gap={10} aria-busy="true">
          <Text role="status" size="sm" c="dimmed">
            {t('states.loading')}
          </Text>
          <Skeleton height={56} radius={12} />
        </Stack>
      ) : isError ? (
        <Group gap="sm" role="alert">
          <Text size="sm">{t('curriculum.assessments.loadError')}</Text>
          <Button size="compact-md" variant="default" onClick={onRetry}>
            {t('pages.retry')}
          </Button>
        </Group>
      ) : !assessments || assessments.length === 0 ? (
        <Text c="dimmed">{t('curriculum.assessments.none')}</Text>
      ) : (
        <>
          {weight !== null && (
            <StatusLine tone={Math.abs(weight - 100) < 0.05 ? 'good' : 'attention'}>
              {Math.abs(weight - 100) < 0.05
                ? t('curriculum.assessments.weightsOk')
                : t('curriculum.assessments.weightsOff', { total: number(weight) })}
            </StatusLine>
          )}
          <ul className={classes.list}>
            {assessments.map((assessment) => (
              <li key={assessment.id} className={classes.assessment}>
                <Title order={4} className={classes.name}>
                  {assessment.name}
                </Title>
                <Group gap={6}>
                  <span className={classes.chip}>
                    {assessment.method ?? t('curriculum.assessments.noMethod')}
                  </span>
                  {assessment.weight !== null && (
                    <span className={classes.chip}>
                      {t('curriculum.assessments.weightValue', {
                        value: number(assessment.weight),
                      })}
                    </span>
                  )}
                  {assessment.timing && <span className={classes.chip}>{assessment.timing}</span>}
                  {assessment.time_minutes > 0 && (
                    <span className={classes.chip}>
                      {t('curriculum.details.minutes', {
                        value: number(assessment.time_minutes, 0),
                      })}
                    </span>
                  )}
                </Group>
                {assessment.items.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    {t('curriculum.assessments.noItems')}
                  </Text>
                ) : (
                  <ul className={classes.items}>
                    {assessment.items.map((item) => (
                      <li key={item.id} className={classes.item}>
                        <Text className={classes.itemLabel}>
                          {item.label}
                          {item.marks !== null && (
                            <span className={classes.marks}>
                              {t('curriculum.assessments.marksValue', {
                                value: number(item.marks),
                              })}
                            </span>
                          )}
                        </Text>
                        {item.objective_ids.length === 0 ? (
                          <Text size="sm" c="dimmed">
                            {t('curriculum.assessments.assessesNothing')}
                          </Text>
                        ) : (
                          <div>
                            <Text size="sm" c="dimmed">
                              {t('curriculum.assessments.assessesCount', {
                                count: item.objective_ids.length,
                              })}
                            </Text>
                            <ul className={classes.links}>
                              {item.objective_ids.map((id) => (
                                <li key={id}>{texts.get(id) ?? '…'}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {canEdit && (
                          <Group gap="sm">
                            <Button
                              variant="default"
                              leftSection={<IconPencil size={18} aria-hidden />}
                              aria-label={t('curriculum.assessments.editItemOne', {
                                name: item.label,
                              })}
                              onClick={() => open({ kind: 'editItem', assessment, item })}
                            >
                              {t('curriculum.assessments.editItem')}
                            </Button>
                            <Button
                              variant="default"
                              leftSection={<IconTrash size={18} aria-hidden />}
                              aria-label={t('curriculum.assessments.deleteItemOne', {
                                name: item.label,
                              })}
                              onClick={() => open({ kind: 'deleteItem', assessment, item })}
                            >
                              {t('curriculum.assessments.deleteItem')}
                            </Button>
                          </Group>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {canEdit && (
                  <Group gap="sm">
                    <Button
                      variant="default"
                      leftSection={<IconPlus size={18} aria-hidden />}
                      aria-label={t('curriculum.assessments.addItemOne', { name: assessment.name })}
                      onClick={() => open({ kind: 'addItem', assessment })}
                    >
                      {t('curriculum.assessments.addItem')}
                    </Button>
                    <Button
                      variant="default"
                      leftSection={<IconPencil size={18} aria-hidden />}
                      aria-label={t('curriculum.assessments.editOne', { name: assessment.name })}
                      onClick={() => open({ kind: 'edit', assessment })}
                    >
                      {t('curriculum.assessments.editAssessment')}
                    </Button>
                    <Button
                      variant="default"
                      leftSection={<IconTrash size={18} aria-hidden />}
                      aria-label={t('curriculum.assessments.deleteOne', { name: assessment.name })}
                      onClick={() => open({ kind: 'delete', assessment })}
                    >
                      {t('curriculum.assessments.deleteAssessment')}
                    </Button>
                  </Group>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {canEdit && (
        <>
          <AssessmentDialog opened={dialog?.kind === 'add'} moduleId={moduleId} {...common} />
          {last && last.kind === 'edit' && (
            <AssessmentDialog
              opened={dialog?.kind === 'edit'}
              moduleId={moduleId}
              assessment={last.assessment}
              {...common}
            />
          )}
          {last && last.kind === 'delete' && (
            <AssessmentDeleteDialog
              opened={dialog?.kind === 'delete'}
              target={{ kind: 'assessment', assessment: last.assessment }}
              {...common}
            />
          )}
          {last && last.kind === 'addItem' && (
            <ItemDialog
              opened={dialog?.kind === 'addItem'}
              moduleId={moduleId}
              assessment={last.assessment}
              {...common}
            />
          )}
          {last && last.kind === 'editItem' && (
            <ItemDialog
              opened={dialog?.kind === 'editItem'}
              moduleId={moduleId}
              assessment={last.assessment}
              item={last.item}
              {...common}
            />
          )}
          {last && last.kind === 'deleteItem' && (
            <AssessmentDeleteDialog
              opened={dialog?.kind === 'deleteItem'}
              target={{ kind: 'item', item: last.item }}
              {...common}
            />
          )}
        </>
      )}
    </Paper>
  );
}
