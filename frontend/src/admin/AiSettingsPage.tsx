import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Group,
  NativeSelect,
  Paper,
  Radio,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm, type FormRulesRecord, type UseFormReturnType } from '@mantine/form';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconPlugConnected,
  IconPower,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { isApiError } from '../api/client';
import { fetchAiSettings, queryKeys, testAiConnection, updateAiSettings } from '../api/endpoints';
import type {
  AiConnectionTest,
  AiDataLocation,
  AiProvider,
  AiProviderKind,
  AiSettings,
} from '../api/types';
import { SuccessNotice } from '../pages/SuccessNotice';
import { Page } from '../ui/Page';
import { ErrorState, LoadingState } from '../ui/States';
import {
  isDecimal,
  isWholeNumber,
  needsAcknowledgement,
  PROVIDER_KINDS,
  toUpdate,
  toValues,
  type AiValues,
  type RealProviderKind,
} from './aiForm';
import classes from './AiSettingsPage.module.css';

const LOCATIONS: AiDataLocation[] = ['local', 'south_africa', 'outside_south_africa'];

/** The error of a refused save: the server's reason (it is specific), or a general line. */
function saveErrorMessage(t: TFunction, error: unknown): string {
  if (isApiError(error, 422, 409) && error.message) {
    return t('admin.ai.saveFailed', { detail: error.message });
  }
  if (isApiError(error, 403)) return t('curriculum.edit.errors.forbidden');
  return t('curriculum.edit.errors.generic');
}

/**
 * A date as day, month name, year, in the UTC calendar day the server stored. The locale is
 * explicit (English is written day first) so the text does not depend on the machine's own
 * locale or time zone.
 */
function formatDate(value: string, language: string): string {
  const locale = language.startsWith('en') ? 'en-GB' : language;
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function providerName(t: TFunction, kind: AiProviderKind): string {
  return t(`admin.ai.provider.${kind}.name`);
}

// --- Status and the test button ----------------------------------------------------

function StatusCard({ settings, dirty }: { settings: AiSettings; dirty: boolean }) {
  const { t, i18n } = useTranslation();
  const [result, setResult] = useState<AiConnectionTest | null>(null);
  const test = useMutation({ mutationFn: testAiConnection, onSuccess: setResult });
  const { state, reasons, budget_message: budgetMessage } = settings.status;
  const active = settings.providers.find((p) => p.kind === settings.active_provider);
  const name = providerName(t, settings.active_provider);

  const headline =
    state === 'off'
      ? t('admin.ai.status.off')
      : state === 'ready'
        ? t('admin.ai.status.ready', { provider: name })
        : t('admin.ai.status.blocked', { provider: name });
  const Icon = state === 'ready' ? IconCircleCheck : state === 'blocked' ? IconAlertTriangle : IconPower;

  return (
    <Paper withBorder className={classes.card} component="section" aria-labelledby="ai-status">
      <div className={classes.header}>
        <Title order={2} id="ai-status" className={classes.sectionTitle}>
          {t('admin.ai.status.title')}
        </Title>
        <span className={classes.chip} data-tone={state === 'blocked' ? 'attention' : undefined}>
          <Icon size={16} aria-hidden />
          {headline}
        </span>
      </div>
      {state === 'off' && <Text>{t('admin.ai.status.offBody')}</Text>}
      {state === 'ready' && (
        <Text>{t('admin.ai.status.readyBody', { provider: name, model: active?.model ?? '' })}</Text>
      )}
      {state === 'blocked' && (
        <ul className={classes.reasons}>
          {reasons.map((reason) => (
            <li key={reason}>
              {reason === 'budget_exceeded' && budgetMessage
                ? budgetMessage
                : t(`admin.ai.status.reason.${reason}`)}
            </li>
          ))}
        </ul>
      )}
      <Text size="sm" c="dimmed">
        {t('admin.ai.usage', {
          calls: settings.usage.calls,
          tokens: settings.usage.tokens,
          cost: settings.usage.cost,
          date: formatDate(settings.usage.period_end, i18n.language),
        })}
      </Text>
      <div>
        <Button
          variant="default"
          leftSection={<IconPlugConnected size={18} aria-hidden />}
          loading={test.isPending}
          disabled={state === 'off' || dirty}
          onClick={() => {
            setResult(null);
            test.mutate();
          }}
        >
          {t('admin.ai.test.button')}
        </Button>
      </div>
      <Text size="sm" c="dimmed">
        {state === 'off'
          ? t('admin.ai.test.offNote')
          : dirty
            ? t('admin.ai.test.saveFirst')
            : t('admin.ai.test.note')}
      </Text>
      {result?.ok && (
        <SuccessNotice>
          {t('admin.ai.test.ok', {
            input: result.input_tokens,
            output: result.output_tokens,
            ms: result.duration_ms,
          })}
        </SuccessNotice>
      )}
      {result && !result.ok && (
        <Alert color="red">{t('admin.ai.test.failed', { message: result.message })}</Alert>
      )}
      {test.isError && <Alert color="red">{t('curriculum.edit.errors.generic')}</Alert>}
    </Paper>
  );
}

// --- One provider's settings -------------------------------------------------------

type FormApi = UseFormReturnType<AiValues, AiValues, FormRulesRecord<AiValues>>;

function ProviderFields({
  kind,
  provider,
  form,
}: {
  kind: RealProviderKind;
  provider: AiProvider;
  form: FormApi;
}) {
  const { t } = useTranslation();
  const path = `providers.${kind}` as const;
  const stored = provider.key_status;
  const keyHelp =
    stored === 'set'
      ? t('admin.ai.fields.apiKeySet')
      : stored === 'unreadable'
        ? t('admin.ai.fields.apiKeyUnreadable')
        : provider.key_mode === 'optional'
          ? t('admin.ai.fields.apiKeyOptional')
          : t('admin.ai.fields.apiKeyNotSet');

  return (
    <Stack gap="md">
      <TextInput
        label={t('admin.ai.fields.model')}
        description={t('admin.ai.fields.modelHelp')}
        list={`ai-models-${kind}`}
        autoComplete="off"
        {...form.getInputProps(`${path}.model`)}
      />
      {provider.suggested_models.length > 0 && (
        <datalist id={`ai-models-${kind}`}>
          {provider.suggested_models.map((model) => (
            <option key={model} value={model} />
          ))}
        </datalist>
      )}
      {provider.base_url_mode === 'required' && (
        <TextInput
          label={t('admin.ai.fields.baseUrl')}
          description={t(`admin.ai.fields.baseUrlHelp_${kind}`)}
          autoComplete="off"
          {...form.getInputProps(`${path}.baseUrl`)}
        />
      )}
      {provider.data_location_fixed ? (
        <Text size="sm">{t('admin.ai.fields.locationFixed', { place: t('admin.ai.location.outside_south_africa') })}</Text>
      ) : (
        <NativeSelect
          label={t('admin.ai.fields.location')}
          description={t('admin.ai.fields.locationHelp')}
          data={LOCATIONS.map((value) => ({ value, label: t(`admin.ai.location.${value}`) }))}
          {...form.getInputProps(`${path}.location`)}
        />
      )}
      {provider.key_mode !== 'none' && (
        <Stack gap="xs">
          <TextInput
            type="password"
            label={t('admin.ai.fields.apiKey')}
            description={keyHelp}
            autoComplete="new-password"
            spellCheck={false}
            {...form.getInputProps(`${path}.apiKey`)}
          />
          {stored !== 'not_set' && (
            <Checkbox
              label={t('admin.ai.fields.removeKey')}
              {...form.getInputProps(`${path}.clearKey`, { type: 'checkbox' })}
            />
          )}
        </Stack>
      )}
      <Group align="flex-start" grow>
        <TextInput
          label={t('admin.ai.fields.inputPrice')}
          inputMode="decimal"
          autoComplete="off"
          {...form.getInputProps(`${path}.inputPrice`)}
        />
        <TextInput
          label={t('admin.ai.fields.outputPrice')}
          inputMode="decimal"
          autoComplete="off"
          {...form.getInputProps(`${path}.outputPrice`)}
        />
      </Group>
      <Text size="sm" c="dimmed">
        {t('admin.ai.fields.pricesHelp')}
      </Text>
      <TextInput
        label={t('admin.ai.fields.temperature')}
        description={t('admin.ai.fields.temperatureHelp')}
        inputMode="decimal"
        autoComplete="off"
        {...form.getInputProps(`${path}.temperature`)}
      />
      {kind === 'openai_compatible' && (
        <Text size="sm" c="dimmed">
          {t('admin.ai.openaiNote')}
        </Text>
      )}
    </Stack>
  );
}

// --- The form ----------------------------------------------------------------------

function validate(t: TFunction, settings: AiSettings) {
  const required = t('curriculum.edit.required');
  const wholeOrEmpty = (value: string) =>
    value.trim() === '' || isWholeNumber(value) ? null : t('admin.ai.validation.whole');
  const wholeRequired = (value: string) =>
    value.trim() === ''
      ? required
      : isWholeNumber(value) && Number(value) >= 1
        ? null
        : t('admin.ai.validation.atLeastOne');
  const decimalOrEmpty = (value: string) =>
    value.trim() === '' || isDecimal(value) ? null : t('admin.ai.validation.decimal');

  const providerRules = Object.fromEntries(
    PROVIDER_KINDS.map((kind) => [
      kind,
      {
        inputPrice: decimalOrEmpty,
        outputPrice: decimalOrEmpty,
        temperature: (value: string) =>
          value.trim() === '' || (isDecimal(value) && Number(value) <= 2)
            ? null
            : t('admin.ai.validation.temperature'),
      },
    ])
  );
  return {
    costCap: decimalOrEmpty,
    tokenCap: wholeOrEmpty,
    callCap: wholeOrEmpty,
    callsPerRun: wholeRequired,
    maxOutput: wholeRequired,
    providers: providerRules,
    acknowledge: (value: boolean, values: AiValues) =>
      needsAcknowledgement(values, settings) && !value ? t('admin.ai.outside.required') : null,
  };
}

function AiSettingsForm({
  settings,
  saved,
  onSaved,
}: {
  settings: AiSettings;
  /** Kept above the form, which starts afresh from the saved settings after a save. */
  saved: boolean;
  onSaved: (saved: boolean) => void;
}) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const [failure, setFailure] = useState<string | null>(null);
  const savedRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (saved) savedRef.current?.focus();
  }, [saved]);

  const form = useForm<AiValues>({
    initialValues: toValues(settings),
    validate: validate(t, settings),
    validateInputOnBlur: false,
  });
  const save = useMutation({
    mutationFn: () => updateAiSettings(toUpdate(form.values, settings)),
    onMutate: () => {
      setFailure(null);
      onSaved(false);
    },
    onSuccess: (next) => {
      onSaved(true);
      client.setQueryData(queryKeys.aiSettings, next);
    },
    onError: (error) => setFailure(saveErrorMessage(t, error)),
  });

  const chosen = form.values.provider;
  const chosenProvider = settings.providers.find((p) => p.kind === chosen);
  const mustAcknowledge = needsAcknowledgement(form.values, settings);
  const outside =
    chosen !== 'null' && form.values.providers[chosen].location === 'outside_south_africa';

  return (
    <>
      <StatusCard settings={settings} dirty={form.isDirty()} />
      <form
        noValidate
        onSubmit={form.onSubmit(() => save.mutate())}
        className={classes.form}
        aria-label={t('admin.ai.title')}
      >
        {saved && (
          <div ref={savedRef} tabIndex={-1} className={classes.notice}>
            <SuccessNotice>{t('admin.ai.saved')}</SuccessNotice>
          </div>
        )}
        {failure && <Alert color="red">{failure}</Alert>}

        <Paper withBorder className={classes.card} component="section" aria-labelledby="ai-provider">
          <Title order={2} id="ai-provider" className={classes.sectionTitle}>
            {t('admin.ai.providerTitle')}
          </Title>
          <Text>{t('admin.ai.providerHelp')}</Text>
          <Radio.Group
            aria-labelledby="ai-provider"
            value={form.values.provider}
            onChange={(value) => form.setFieldValue('provider', value as AiProviderKind)}
          >
            <Stack gap="sm">
              {(['null', ...PROVIDER_KINDS] as AiProviderKind[]).map((kind) => (
                <Radio
                  key={kind}
                  value={kind}
                  label={providerName(t, kind)}
                  description={t(`admin.ai.provider.${kind}.about`)}
                />
              ))}
            </Stack>
          </Radio.Group>

          {chosen === 'null' && <Text>{t('admin.ai.provider.null.detail')}</Text>}
          {chosen !== 'null' && chosenProvider && (
            <section aria-labelledby="ai-provider-settings" className={classes.sub}>
              <Title order={3} id="ai-provider-settings" className={classes.subTitle}>
                {t('admin.ai.providerSettings', { provider: providerName(t, chosen) })}
              </Title>
              <ProviderFields kind={chosen} provider={chosenProvider} form={form} />
            </section>
          )}

          {outside && (
            <section aria-labelledby="ai-outside" className={classes.warning}>
              <Title order={3} id="ai-outside" className={classes.warningTitle}>
                <IconAlertTriangle size={20} aria-hidden />
                {t('admin.ai.outside.title')}
              </Title>
              <Text size="sm">{t('admin.ai.outside.body')}</Text>
              {settings.acknowledgement.acknowledged_at && !mustAcknowledge ? (
                <Text size="sm">
                  {t('admin.ai.outside.acknowledgedOn', {
                    date: formatDate(settings.acknowledgement.acknowledged_at, i18n.language),
                  })}
                </Text>
              ) : (
                <Checkbox
                  label={t('admin.ai.outside.acknowledge')}
                  {...form.getInputProps('acknowledge', { type: 'checkbox' })}
                />
              )}
            </section>
          )}
        </Paper>

        <Paper withBorder className={classes.card} component="section" aria-labelledby="ai-privacy">
          <Title order={2} id="ai-privacy" className={classes.sectionTitle}>
            {t('admin.ai.privacy.title')}
          </Title>
          <Text>{t('admin.ai.privacy.body')}</Text>
          <Switch
            label={t('admin.ai.privacy.localOnly')}
            description={t('admin.ai.privacy.localOnlyHelp')}
            {...form.getInputProps('localOnly', { type: 'checkbox' })}
          />
          <Radio.Group
            value={form.values.onPersonalData}
            onChange={(value) => form.setFieldValue('onPersonalData', value as 'refuse' | 'redact')}
            label={t('admin.ai.privacy.personalData')}
            description={t('admin.ai.privacy.personalDataHelp')}
          >
            <Stack gap="sm" mt="sm">
              <Radio value="refuse" label={t('admin.ai.privacy.refuse')} description={t('admin.ai.privacy.refuseHelp')} />
              <Radio value="redact" label={t('admin.ai.privacy.redact')} description={t('admin.ai.privacy.redactHelp')} />
            </Stack>
          </Radio.Group>
        </Paper>

        <Paper withBorder className={classes.card} component="section" aria-labelledby="ai-budget">
          <Title order={2} id="ai-budget" className={classes.sectionTitle}>
            {t('admin.ai.budget.title')}
          </Title>
          <Text>{t('admin.ai.budget.body')}</Text>
          <div className={classes.grid}>
            <TextInput
              label={t('admin.ai.budget.costCap')}
              description={t('admin.ai.budget.blankIsNone')}
              inputMode="decimal"
              autoComplete="off"
              {...form.getInputProps('costCap')}
            />
            <TextInput
              label={t('admin.ai.budget.tokenCap')}
              description={t('admin.ai.budget.blankIsNone')}
              inputMode="numeric"
              autoComplete="off"
              {...form.getInputProps('tokenCap')}
            />
            <TextInput
              label={t('admin.ai.budget.callCap')}
              description={t('admin.ai.budget.blankIsNone')}
              inputMode="numeric"
              autoComplete="off"
              {...form.getInputProps('callCap')}
            />
            <TextInput
              label={t('admin.ai.budget.callsPerRun')}
              description={t('admin.ai.budget.callsPerRunHelp')}
              inputMode="numeric"
              autoComplete="off"
              {...form.getInputProps('callsPerRun')}
            />
            <TextInput
              label={t('admin.ai.budget.maxOutput')}
              description={t('admin.ai.budget.maxOutputHelp')}
              inputMode="numeric"
              autoComplete="off"
              {...form.getInputProps('maxOutput')}
            />
          </div>
        </Paper>

        <Group>
          <Button type="submit" loading={save.isPending}>
            {t('admin.ai.save')}
          </Button>
          {form.isDirty() && (
            <Button variant="default" onClick={() => form.reset()} disabled={save.isPending}>
              {t('admin.ai.discard')}
            </Button>
          )}
        </Group>
      </form>
    </>
  );
}

/** Admin > AI settings: provider, privacy, budgets, keys (write-only) and a test button. */
export function AiSettingsPage() {
  const { t } = useTranslation();
  const settings = useQuery({ queryKey: queryKeys.aiSettings, queryFn: fetchAiSettings });
  const [saved, setSaved] = useState(false);
  const title = t('admin.ai.title');

  if (settings.isPending) {
    return (
      <Page title={title}>
        <LoadingState skeletons={2} />
      </Page>
    );
  }
  if (settings.isError) {
    return (
      <Page title={title}>
        <ErrorState
          title={t('admin.ai.loadErrorTitle')}
          body={t('admin.ai.loadErrorBody')}
          actions={<Button onClick={() => void settings.refetch()}>{t('pages.retry')}</Button>}
        />
      </Page>
    );
  }
  return (
    <Page title={title} description={t('admin.ai.description')}>
      <AiSettingsForm
        key={settings.dataUpdatedAt}
        settings={settings.data}
        saved={saved}
        onSaved={setSaved}
      />
    </Page>
  );
}
