import { useEffect, useRef } from 'react';
import { Checkbox, NumberInput, Skeleton, Stack, Text } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { isApiError } from '../api/client';
import {
  changeVersionStatus,
  copyForward,
  deleteVersion,
  fetchCopyForwardPreview,
  queryKeys,
} from '../api/endpoints';
import type { CopyForwardPreview, CurriculumVersion, VersionStatus } from '../api/types';
import { DialogForm, EditDialog } from './EditDialog';
import { editErrorMessage, nounsFor } from './editing';
import { CURRICULUM_PATH, versionPath } from './paths';
import {
  useRefreshVersions,
  versionName,
  type NoticeState,
  type StatusAction,
} from './versions';
import classes from './VersionBar.module.css';

interface StatusDialogProps {
  opened: boolean;
  version: CurriculumVersion;
  action: StatusAction;
  to: VersionStatus;
  onClose: () => void;
  onDone: (message: string) => void;
}

function StatusForm({ version, action, to, onClose, onDone }: Omit<StatusDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const refresh = useRefreshVersions();
  const run = useMutation({
    mutationFn: () => changeVersionStatus(version.id, to),
    onSuccess: async (saved) => {
      await refresh(version.id);
      onDone(t(`curriculum.versions.done.${action}`, { year: saved.academic_year }));
    },
  });
  const error = run.isError
    ? editErrorMessage(t, run.error, t('curriculum.versions.errors.status', nouns))
    : null;
  return (
    <DialogForm
      submitLabel={t(`curriculum.versions.action.${action}`)}
      error={error}
      busy={run.isPending}
      onSubmit={(event) => {
        event.preventDefault();
        run.mutate();
      }}
      onClose={onClose}
    >
      <Text>{t(`curriculum.versions.confirm.${action}`)}</Text>
      <Text size="sm" c="dimmed">
        {t('curriculum.versions.confirm.note')}
      </Text>
    </DialogForm>
  );
}

/** Confirms publishing, returning to draft, archiving or publishing again. */
export function StatusDialog({ opened, ...props }: StatusDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t(`curriculum.versions.confirm.${props.action}Title`, {
        version: versionName(t, props.version),
      })}
    >
      <StatusForm {...props} />
    </EditDialog>
  );
}

interface CopyForwardDialogProps {
  opened: boolean;
  version: CurriculumVersion;
  onClose: () => void;
}

interface CopyValues {
  year: number | string;
  roles: string[];
}

function CopyForwardFields({
  version,
  preview,
  onClose,
}: Omit<CopyForwardDialogProps, 'opened'> & { preview: CopyForwardPreview }) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const navigate = useNavigate();
  const refresh = useRefreshVersions();
  // The form appears after the preview loads, when the dialog has already taken focus.
  const yearRef = useRef<HTMLInputElement>(null);
  useEffect(() => yearRef.current?.focus(), []);
  const copyable = preview.role_assignments.filter((row) => row.skip_reason === null);
  const skipped = preview.role_assignments.filter((row) => row.skip_reason !== null);
  const form = useForm<CopyValues>({
    initialValues: { year: preview.academic_year, roles: copyable.map((row) => row.id) },
    validate: {
      year: (value) => {
        const year = Number(value);
        if (value === '' || !Number.isInteger(year) || year < 1900 || year > 2200) {
          return t('curriculum.versions.copy.yearRange');
        }
        return preview.taken_years.includes(year) ? t('curriculum.versions.copy.yearTaken') : null;
      },
    },
  });
  const run = useMutation({
    mutationFn: (values: CopyValues) => copyForward(version.id, Number(values.year), values.roles),
    onSuccess: async (created) => {
      await refresh(version.id);
      const state: NoticeState = {
        notice: t('curriculum.versions.copy.done', {
          year: created.academic_year,
          source: versionName(t, version),
        }),
      };
      navigate(versionPath(created.id), { state });
    },
  });
  const error = run.isError
    ? editErrorMessage(
        t,
        run.error,
        t('curriculum.versions.errors.yearTaken', {
          programme: t('terms.programme', { count: 1 }).toLocaleLowerCase(),
        })
      )
    : null;

  const counts: [string, number][] = [
    [t('terms.phase', { count: 2 }), preview.phases],
    [t('terms.module', { count: 2 }), preview.modules],
    [t('terms.learning_event', { count: 2 }), preview.learning_events],
    [t('terms.objective', { count: 2 }), preview.objectives],
    [t('curriculum.versions.copy.frameworkLinks'), preview.mappings],
  ];

  return (
    <DialogForm
      submitLabel={t('curriculum.versions.copy.submit')}
      error={error}
      busy={run.isPending}
      onSubmit={form.onSubmit((values) => run.mutate(values))}
      onClose={onClose}
    >
      <NumberInput
        label={t('curriculum.versions.copy.year')}
        description={t('curriculum.versions.copy.yearHint', {
          years: preview.taken_years.join(', '),
        })}
        required
        allowDecimal={false}
        allowNegative={false}
        min={1900}
        max={2200}
        ref={yearRef}
        {...form.getInputProps('year')}
      />
      <Stack gap={6}>
        <Text>{t('curriculum.versions.copy.includes')}</Text>
        <dl className={classes.counts} aria-label={t('curriculum.versions.copy.counts')}>
          {counts.map(([label, value]) => (
            <div key={label} className={classes.count}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <Text size="sm" c="dimmed">
          {t('curriculum.versions.copy.notIncluded')}
        </Text>
      </Stack>
      {!preview.can_copy_roles ? (
        <Text size="sm">
          {t('curriculum.versions.copy.cannotCopyRoles', {
            programme: t('terms.programme', { count: 1 }).toLocaleLowerCase(),
          })}
        </Text>
      ) : preview.role_assignments.length === 0 ? (
        <Text size="sm" c="dimmed">
          {t('curriculum.versions.copy.noRoles', nouns)}
        </Text>
      ) : (
        <Stack gap="xs">
          {copyable.length > 0 && (
            <Checkbox.Group
              label={t('curriculum.versions.copy.roles')}
              description={t('curriculum.versions.copy.rolesHint', nouns)}
              {...form.getInputProps('roles')}
            >
              <Stack gap={0} mt="xs">
                {copyable.map((row) => (
                  <Checkbox
                    key={row.id}
                    value={row.id}
                    classNames={{ root: classes.option }}
                    label={t('curriculum.versions.copy.roleOption', {
                      name: row.user_name,
                      role: row.role_name,
                      item: row.item,
                    })}
                  />
                ))}
              </Stack>
            </Checkbox.Group>
          )}
          {skipped.length > 0 && (
            <section aria-labelledby="copy-skipped">
              <Text id="copy-skipped" size="sm" fw={600}>
                {t('curriculum.versions.copy.skipped')}
              </Text>
              <ul className={classes.skipped}>
                {skipped.map((row) => (
                  <li key={row.id}>
                    <Text size="sm">
                      {t('curriculum.versions.copy.skippedItem', {
                        name: row.user_name,
                        role: row.role_name,
                        item: row.item,
                        reason: t(`curriculum.versions.copy.reason.${row.skip_reason}`),
                      })}
                    </Text>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </Stack>
      )}
    </DialogForm>
  );
}

function CopyForwardForm({ version, onClose }: Omit<CopyForwardDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const preview = useQuery({
    queryKey: queryKeys.copyForward(version.id),
    queryFn: () => fetchCopyForwardPreview(version.id),
    staleTime: 0,
  });
  if (preview.isPending) {
    return (
      <Stack gap="sm" aria-busy="true">
        <Text role="status" size="sm" c="dimmed">
          {t('curriculum.versions.copy.loading')}
        </Text>
        <Skeleton height={44} radius={8} />
        <Skeleton height={96} radius={8} />
      </Stack>
    );
  }
  if (preview.isError) {
    return (
      <DialogForm
        submitLabel=""
        error={t('curriculum.versions.copy.loadError')}
        busy={false}
        onClose={onClose}
      />
    );
  }
  return <CopyForwardFields version={version} preview={preview.data} onClose={onClose} />;
}

/** Copies a version to a new draft for another academic year. */
export function CopyForwardDialog({ opened, version, onClose }: CopyForwardDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={onClose}
      title={t('curriculum.versions.copy.title', { version: versionName(t, version) })}
    >
      <CopyForwardForm version={version} onClose={onClose} />
    </EditDialog>
  );
}

interface DeleteVersionDialogProps {
  opened: boolean;
  version: CurriculumVersion;
  /** Where to go afterwards: the version it was copied from, if still visible. */
  nextVersionId: string | null;
  onClose: () => void;
}

function DeleteVersionForm({
  version,
  nextVersionId,
  onClose,
}: Omit<DeleteVersionDialogProps, 'opened'>) {
  const { t } = useTranslation();
  const nouns = nounsFor(t);
  const navigate = useNavigate();
  const client = useQueryClient();
  const run = useMutation({
    mutationFn: () => deleteVersion(version.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.programmes });
      const state: NoticeState = {
        notice: t('curriculum.versions.delete.done', { version: versionName(t, version) }),
      };
      navigate(nextVersionId ? versionPath(nextVersionId) : CURRICULUM_PATH, { state });
      // Not refetched: the version is gone.
      client.removeQueries({ queryKey: ['curriculum-versions', version.id] });
    },
  });
  const error = run.isError
    ? isApiError(run.error, 409)
      ? t('curriculum.edit.errors.conflict')
      : editErrorMessage(t, run.error)
    : null;
  return (
    <DialogForm
      submitLabel={t('curriculum.versions.delete.submit')}
      error={error}
      busy={run.isPending}
      danger
      onSubmit={(event) => {
        event.preventDefault();
        run.mutate();
      }}
      onClose={onClose}
    >
      <Text>{t('curriculum.versions.delete.body', nouns)}</Text>
      <Text size="sm" c="dimmed">
        {t('curriculum.versions.delete.note')}
      </Text>
    </DialogForm>
  );
}

/** Deletes a draft version with everything in it. */
export function DeleteVersionDialog({ opened, ...props }: DeleteVersionDialogProps) {
  const { t } = useTranslation();
  return (
    <EditDialog
      opened={opened}
      onClose={props.onClose}
      title={t('curriculum.versions.delete.title', { version: versionName(t, props.version) })}
    >
      <DeleteVersionForm {...props} />
    </EditDialog>
  );
}
