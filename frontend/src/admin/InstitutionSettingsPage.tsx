import { useState } from 'react';
import { Alert, Button, NumberInput, Paper, Stack, Switch, Text, TextInput, Title } from '@mantine/core';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { queryKeys, updateInstitutionSettings } from '../api/endpoints';
import type { Institution, SettingsUpdate, Term, TermOverride } from '../api/types';
import { useInstitution } from '../institution/useInstitution';
import { SuccessNotice } from '../pages/SuccessNotice';
import { Page } from '../ui/Page';
import { LoadingState } from '../ui/States';
import classes from './Admin.module.css';

type PolicySection = 'mapping' | 'credits' | 'quality' | 'coverage' | 'explorer';

interface FieldDef {
  key: string;
  kind: 'int' | 'float' | 'bool';
  min?: number;
  max?: number;
  /** A blank box means "not set" (null). */
  nullable?: boolean;
}

// The ranges are the server's (services/policies.py); the server checks them again.
const SECTIONS: { key: PolicySection; fields: FieldDef[] }[] = [
  {
    key: 'mapping',
    fields: [
      { key: 'four_eyes', kind: 'bool' },
      { key: 'second_review_for_rejects', kind: 'bool' },
      { key: 'bulk_accept_min_percent', kind: 'int', min: 50, max: 100 },
      { key: 'bulk_accept_max_links', kind: 'int', min: 1, max: 1000 },
      { key: 'ai_min_coverage', kind: 'int', min: 1, max: 5 },
      { key: 'ai_prefer_specific_item', kind: 'bool' },
    ],
  },
  {
    key: 'credits',
    fields: [
      { key: 'hours_per_credit', kind: 'int', min: 1, max: 100 },
      { key: 'tolerance_percent', kind: 'int', min: 0, max: 100 },
      { key: 'credits_per_year', kind: 'int', min: 1, max: 10000 },
      { key: 'min_exit_level_credits', kind: 'int', min: 0, max: 10000, nullable: true },
    ],
  },
  { key: 'quality', fields: [{ key: 'near_duplicate_min_percent', kind: 'int', min: 85, max: 100 }] },
  {
    key: 'coverage',
    fields: [
      { key: 'multiple_match_n', kind: 'int', min: 1, max: 20 },
      { key: 'subordinate_min_percent', kind: 'int', min: 1, max: 100 },
      { key: 'weighted_low_percent', kind: 'int', min: 1, max: 100 },
      { key: 'repeat_min_sessions', kind: 'int', min: 2, max: 100 },
      { key: 'repeat_spread', kind: 'float', min: 0, max: 5 },
    ],
  },
  { key: 'explorer', fields: [{ key: 'show_competency_view', kind: 'bool' }] },
];

const TERMS: Term[] = [
  'programme',
  'curriculum_version',
  'phase',
  'module',
  'learning_event',
  'objective',
  'framework',
  'framework_item',
];

type Values = Record<string, number | boolean | string | null>;

function saveError(t: TFunction, error: unknown): string {
  if (isApiError(error, 422, 409) && error.message) {
    return t('admin.settings.saveFailed', { detail: error.message });
  }
  if (isApiError(error, 403)) return t('curriculum.edit.errors.forbidden');
  return t('curriculum.edit.errors.generic');
}

/** One block of settings with its own Save: only that section is sent. */
function SettingsCard({
  titleKey,
  helpKey,
  id,
  onSave,
  children,
  busy,
  error,
  saved,
  disabled,
}: {
  titleKey: string;
  helpKey: string;
  id: string;
  onSave: () => void;
  children: React.ReactNode;
  busy: boolean;
  error: string | null;
  saved: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Paper withBorder component="section" aria-labelledby={id} className={classes.card}>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSave();
        }}
      >
        <Stack gap="md">
          <div>
            <Title order={2} id={id} className={classes.sectionTitle}>
              {t(titleKey)}
            </Title>
            <Text size="sm" c="dimmed">
              {t(helpKey)}
            </Text>
          </div>
          {children}
          {error && (
            <Alert color="red" role="alert">
              {error}
            </Alert>
          )}
          {saved && <SuccessNotice>{t('admin.settings.saved')}</SuccessNotice>}
          <Button type="submit" loading={busy} disabled={disabled} w="fit-content">
            {t('admin.settings.save')}
          </Button>
        </Stack>
      </form>
    </Paper>
  );
}

function useSectionSave(onDone?: () => void) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const mutation = useMutation({
    mutationFn: (changes: SettingsUpdate) => updateInstitutionSettings(changes),
    onMutate: () => setSaved(false),
    onSuccess: (institution: Institution) => {
      queryClient.setQueryData(queryKeys.institution, institution);
      setSaved(true);
      onDone?.();
    },
  });
  return { mutation, saved };
}

function PolicyCard({ section, institution }: { section: (typeof SECTIONS)[number]; institution: Institution }) {
  const { t } = useTranslation();
  const current = (institution[section.key] ?? {}) as Record<string, number | boolean | null>;
  const [values, setValues] = useState<Values>(() =>
    Object.fromEntries(section.fields.map((f) => [f.key, current[f.key] ?? (f.kind === 'bool' ? false : null)]))
  );
  const { mutation, saved } = useSectionSave();
  const set = (key: string, value: number | boolean | string | null) =>
    setValues((previous) => ({ ...previous, [key]: value }));

  return (
    <SettingsCard
      id={`settings-${section.key}`}
      titleKey={`admin.settings.${section.key}.title`}
      helpKey={`admin.settings.${section.key}.help`}
      busy={mutation.isPending}
      error={mutation.isError ? saveError(t, mutation.error) : null}
      saved={saved}
      onSave={() => {
        const body: Record<string, number | boolean | null> = {};
        for (const f of section.fields) {
          const value = values[f.key];
          body[f.key] =
            f.kind === 'bool'
              ? Boolean(value)
              : typeof value === 'number'
                ? value
                : f.nullable
                  ? null
                  : (current[f.key] as number);
        }
        mutation.mutate({ [section.key]: body } as SettingsUpdate);
      }}
    >
      {section.fields.map((f) => {
        const label = t(`admin.settings.${section.key}.${f.key}.label`);
        const help = t(`admin.settings.${section.key}.${f.key}.help`);
        if (f.kind === 'bool') {
          return (
            <Switch
              key={f.key}
              label={label}
              description={help}
              checked={Boolean(values[f.key])}
              onChange={(event) => set(f.key, event.currentTarget.checked)}
            />
          );
        }
        return (
          <NumberInput
            key={f.key}
            label={label}
            description={help}
            min={f.min}
            max={f.max}
            allowDecimal={f.kind === 'float'}
            decimalScale={f.kind === 'float' ? 1 : 0}
            allowNegative={false}
            value={typeof values[f.key] === 'number' ? (values[f.key] as number) : ''}
            onChange={(value) => set(f.key, typeof value === 'number' ? value : null)}
            maw={240}
          />
        );
      })}
    </SettingsCard>
  );
}

function TerminologyCard({ institution }: { institution: Institution }) {
  const { t } = useTranslation();
  const [words, setWords] = useState<Record<string, TermOverride>>(() =>
    Object.fromEntries(
      TERMS.map((term) => [term, institution.terminology[term] ?? { singular: '', plural: '' }])
    )
  );
  const { mutation, saved } = useSectionSave();
  const incomplete = TERMS.filter((term) => !!words[term].singular !== !!words[term].plural);
  return (
    <SettingsCard
      id="settings-terminology"
      titleKey="admin.settings.terminology.title"
      helpKey="admin.settings.terminology.help"
      busy={mutation.isPending}
      error={
        mutation.isError
          ? saveError(t, mutation.error)
          : incomplete.length > 0
            ? t('admin.settings.terminology.incomplete')
            : null
      }
      saved={saved}
      onSave={() => {
        if (incomplete.length > 0) return;
        const terminology: Partial<Record<Term, TermOverride>> = {};
        for (const term of TERMS) {
          const { singular, plural } = words[term];
          if (singular.trim() && plural.trim()) {
            terminology[term] = { singular: singular.trim(), plural: plural.trim() };
          }
        }
        mutation.mutate({ terminology });
      }}
    >
      <div className={classes.termGrid}>
        {TERMS.map((term) => (
          <fieldset key={term} className={classes.term}>
            <legend>{t(`terms.${term}_one`)}</legend>
            <TextInput
              label={t('admin.settings.terminology.singular')}
              placeholder={t(`terms.${term}_one`)}
              value={words[term].singular}
              maxLength={60}
              onChange={(event) => {
                const singular = event.currentTarget.value;
                setWords((w) => ({ ...w, [term]: { ...w[term], singular } }));
              }}
            />
            <TextInput
              label={t('admin.settings.terminology.plural')}
              placeholder={t(`terms.${term}_other`)}
              value={words[term].plural}
              maxLength={60}
              onChange={(event) => {
                const plural = event.currentTarget.value;
                setWords((w) => ({ ...w, [term]: { ...w[term], plural } }));
              }}
            />
          </fieldset>
        ))}
      </div>
    </SettingsCard>
  );
}

function ProfileCard({ institution }: { institution: Institution }) {
  const { t } = useTranslation();
  const [health, setHealth] = useState(institution.profiles.includes('health'));
  const [scale, setScale] = useState(institution.default_taxonomy_scale ?? '');
  const { mutation, saved } = useSectionSave();
  return (
    <SettingsCard
      id="settings-profiles"
      titleKey="admin.settings.profiles.title"
      helpKey="admin.settings.profiles.help"
      busy={mutation.isPending}
      error={mutation.isError ? saveError(t, mutation.error) : null}
      saved={saved}
      onSave={() =>
        mutation.mutate({
          profiles: health ? ['core', 'health'] : ['core'],
          default_taxonomy_scale: scale.trim() || null,
        })
      }
    >
      <Switch
        label={t('admin.settings.profiles.health')}
        description={t('admin.settings.profiles.healthHelp')}
        checked={health}
        onChange={(event) => setHealth(event.currentTarget.checked)}
      />
      <TextInput
        label={t('admin.settings.profiles.scale')}
        description={t('admin.settings.profiles.scaleHelp')}
        value={scale}
        maxLength={64}
        maw={320}
        onChange={(event) => setScale(event.currentTarget.value)}
      />
    </SettingsCard>
  );
}

/** Admin > Institution settings: terminology, profiles, and the policies behind mapping, credits,
 * quality checks and coverage. Each block saves on its own and the server checks every value. */
export function InstitutionSettingsPage() {
  const { t } = useTranslation();
  const institution = useInstitution();
  if (!institution) {
    return (
      <Page title={t('admin.settings.title')}>
        <LoadingState title={t('admin.settings.loading')} />
      </Page>
    );
  }
  return (
    <Page
      title={t('admin.settings.title')}
      description={t('admin.settings.description', { name: institution.name })}
    >
      <TerminologyCard institution={institution} />
      <ProfileCard institution={institution} />
      {SECTIONS.map((section) => (
        <PolicyCard key={section.key} section={section} institution={institution} />
      ))}
    </Page>
  );
}
