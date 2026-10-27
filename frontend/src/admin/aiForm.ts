import type {
  AiDataLocation,
  AiProvider,
  AiProviderKind,
  AiProviderUpdate,
  AiSettings,
  AiUpdate,
} from '../api/types';

export type RealProviderKind = Exclude<AiProviderKind, 'null'>;

export const PROVIDER_KINDS: RealProviderKind[] = ['anthropic', 'openai_compatible', 'ollama'];

export interface ProviderValues {
  model: string;
  baseUrl: string;
  location: AiDataLocation;
  temperature: string;
  inputPrice: string;
  outputPrice: string;
  /** Typed to replace the stored key; never filled from the server. */
  apiKey: string;
  clearKey: boolean;
}

export interface AiValues {
  provider: AiProviderKind;
  localOnly: boolean;
  onPersonalData: 'refuse' | 'redact';
  costCap: string;
  tokenCap: string;
  callCap: string;
  callsPerRun: string;
  maxOutput: string;
  /** The administrator read the warning about text leaving South Africa. */
  acknowledge: boolean;
  providers: Record<RealProviderKind, ProviderValues>;
}

function providerValues(provider: AiProvider): ProviderValues {
  return {
    model: provider.model ?? '',
    // A provider with a fixed address shows none; one that asks for it starts at the default.
    baseUrl: provider.base_url ?? (provider.base_url_mode === 'required' ? provider.default_base_url ?? '' : ''),
    location: provider.data_location,
    temperature: provider.temperature ?? '',
    inputPrice: provider.input_price_per_mtok ?? '',
    outputPrice: provider.output_price_per_mtok ?? '',
    apiKey: '',
    clearKey: false,
  };
}

export function toValues(settings: AiSettings): AiValues {
  const byKind = new Map(settings.providers.map((provider) => [provider.kind, provider]));
  const providers = {} as Record<RealProviderKind, ProviderValues>;
  for (const kind of PROVIDER_KINDS) {
    const provider = byKind.get(kind);
    if (provider) providers[kind] = providerValues(provider);
  }
  return {
    provider: settings.active_provider,
    localOnly: settings.local_only,
    onPersonalData: settings.on_personal_data,
    costCap: settings.budget.monthly_cost_cap ?? '',
    tokenCap: settings.budget.monthly_token_cap?.toString() ?? '',
    callCap: settings.budget.monthly_call_cap?.toString() ?? '',
    callsPerRun: settings.budget.max_calls_per_run.toString(),
    maxOutput: settings.budget.max_output_tokens.toString(),
    acknowledge: false,
    providers,
  };
}

const WHOLE_NUMBER = /^\d+$/;
const DECIMAL = /^\d+(\.\d{1,4})?$/;

export function isWholeNumber(value: string): boolean {
  return WHOLE_NUMBER.test(value.trim());
}

export function isDecimal(value: string): boolean {
  return DECIMAL.test(value.trim());
}

/** An empty field is "no limit"; otherwise the whole number. */
function capOrNull(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : Number(trimmed);
}

function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function providerChange(
  now: ProviderValues,
  before: ProviderValues,
  provider: AiProvider,
  chosen: boolean
): AiProviderUpdate | null {
  const change: AiProviderUpdate = {};
  if (now.model.trim() !== before.model.trim()) change.model = textOrNull(now.model);
  // The saved address, not the suggested one: a suggestion is only saved once it is chosen.
  const savedUrl = provider.base_url ?? '';
  if (provider.base_url_mode === 'required' && now.baseUrl.trim() !== savedUrl) {
    if (chosen || now.baseUrl.trim() !== before.baseUrl.trim()) {
      change.base_url = textOrNull(now.baseUrl);
    }
  }
  if (!provider.data_location_fixed && now.location !== before.location) {
    change.data_location = now.location;
  }
  if (now.temperature.trim() !== before.temperature.trim()) {
    change.temperature = textOrNull(now.temperature);
  }
  if (now.inputPrice.trim() !== before.inputPrice.trim()) {
    change.input_price_per_mtok = textOrNull(now.inputPrice);
  }
  if (now.outputPrice.trim() !== before.outputPrice.trim()) {
    change.output_price_per_mtok = textOrNull(now.outputPrice);
  }
  if (now.clearKey) change.clear_api_key = true;
  if (now.apiKey.trim() !== '') change.api_key = now.apiKey.trim();
  return Object.keys(change).length > 0 ? change : null;
}

/** The request for what changed since the settings were loaded. */
export function toUpdate(values: AiValues, settings: AiSettings): AiUpdate {
  const before = toValues(settings);
  const update: AiUpdate = {
    active_provider: values.provider,
    local_only: values.localOnly,
    on_personal_data: values.onPersonalData,
    monthly_cost_cap: textOrNull(values.costCap),
    monthly_token_cap: capOrNull(values.tokenCap),
    monthly_call_cap: capOrNull(values.callCap),
    max_calls_per_run: Number(values.callsPerRun),
    max_output_tokens: Number(values.maxOutput),
  };
  if (values.acknowledge) update.acknowledge_outside_south_africa = true;
  const providers: NonNullable<AiUpdate['providers']> = {};
  for (const provider of settings.providers) {
    const change = providerChange(
      values.providers[provider.kind],
      before.providers[provider.kind],
      provider,
      provider.kind === values.provider
    );
    if (change) providers[provider.kind] = change;
  }
  if (Object.keys(providers).length > 0) update.providers = providers;
  return update;
}

/** Whether the chosen provider sends text outside South Africa, as the form now stands. */
export function choosesOutsideSouthAfrica(values: AiValues): boolean {
  return values.provider !== 'null' && values.providers[values.provider].location === 'outside_south_africa';
}

/**
 * Whether the administrator must tick the acknowledgement: the chosen provider is outside
 * South Africa and the saved acknowledgement does not cover it (a different provider,
 * address or location than the saved ones).
 */
export function needsAcknowledgement(values: AiValues, settings: AiSettings): boolean {
  if (!choosesOutsideSouthAfrica(values) || values.provider === 'null') return false;
  if (!settings.acknowledgement.current || settings.active_provider !== values.provider) return true;
  const saved = toValues(settings).providers[values.provider];
  const now = values.providers[values.provider];
  return saved.baseUrl.trim() !== now.baseUrl.trim() || saved.location !== now.location;
}
