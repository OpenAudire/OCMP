import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import * as endpoints from '../api/endpoints';
import type { AiProvider, AiSettings } from '../api/types';
import i18n from '../i18n';
import { applyTerminology } from '../institution/terminology';
import { renderAt, role, testInstitution, testUser } from '../test/renderApp';
import { needsAcknowledgement, toUpdate, toValues } from './aiForm';

vi.mock('../api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/endpoints')>()),
  fetchMe: vi.fn(),
  fetchMyRoles: vi.fn(),
  fetchInstitution: vi.fn(),
  fetchAiSettings: vi.fn(),
  updateAiSettings: vi.fn(),
  testAiConnection: vi.fn(),
}));

const mocked = vi.mocked(endpoints);

function provider(overrides: Partial<AiProvider> & Pick<AiProvider, 'kind'>): AiProvider {
  return {
    model: null,
    base_url: null,
    data_location: 'outside_south_africa',
    data_location_fixed: false,
    outside_south_africa: true,
    is_local: false,
    temperature: null,
    input_price_per_mtok: null,
    output_price_per_mtok: null,
    key_mode: 'optional',
    key_status: 'not_set',
    key_set_at: null,
    base_url_mode: 'required',
    default_base_url: null,
    suggested_models: [],
    missing: [],
    ...overrides,
  };
}

const anthropic = provider({
  kind: 'anthropic',
  data_location_fixed: true,
  key_mode: 'required',
  base_url_mode: 'fixed',
  default_base_url: 'https://api.anthropic.com',
  suggested_models: ['claude-sonnet-5-5'],
  missing: ['model', 'api_key'],
});
const openai = provider({
  kind: 'openai_compatible',
  default_base_url: 'https://api.openai.com/v1',
  missing: ['model'],
});
const ollama = provider({
  kind: 'ollama',
  data_location: 'local',
  outside_south_africa: false,
  is_local: true,
  key_mode: 'none',
  missing: ['model', 'base_url'],
});

function settings(overrides: Partial<AiSettings> = {}): AiSettings {
  return {
    active_provider: 'null',
    local_only: true,
    on_personal_data: 'refuse',
    budget: {
      monthly_cost_cap: '10.00',
      monthly_token_cap: 2000000,
      monthly_call_cap: 2000,
      max_calls_per_run: 500,
      max_output_tokens: 1024,
    },
    acknowledgement: { acknowledged_at: null, current: false },
    usage: {
      period_start: '2026-10-01T00:00:00Z',
      period_end: '2026-11-01T00:00:00Z',
      calls: 0,
      tokens: 0,
      cost: '0',
    },
    status: { state: 'off', reasons: [], budget_message: null },
    providers: [anthropic, openai, ollama],
    encryption: { keys_stored_ok: true, rotation_needed: false },
    ...overrides,
  };
}

const readyOllama = settings({
  active_provider: 'ollama',
  status: { state: 'ready', reasons: [], budget_message: null },
  providers: [
    anthropic,
    openai,
    { ...ollama, model: 'llama-test', base_url: 'http://ollama:11434', missing: [] },
  ],
});

const userEvent = {
  click: (element: HTMLElement) => {
    fireEvent.click(element);
    return Promise.resolve();
  },
  type: (element: HTMLElement, text: string) => {
    fireEvent.change(element, { target: { value: text } });
    return Promise.resolve();
  },
  clear: (element: HTMLElement) => {
    fireEvent.change(element, { target: { value: '' } });
    return Promise.resolve();
  },
};

describe('AI settings: form logic', () => {
  it('sends only what changed, with the choices and limits', () => {
    const base = settings();
    const values = toValues(base);
    values.provider = 'ollama';
    values.providers.ollama.model = 'llama-test';
    values.providers.ollama.baseUrl = 'http://ollama:11434';
    values.tokenCap = '';

    expect(toUpdate(values, base)).toEqual({
      active_provider: 'ollama',
      local_only: true,
      on_personal_data: 'refuse',
      monthly_cost_cap: '10.00',
      monthly_token_cap: null,
      monthly_call_cap: 2000,
      max_calls_per_run: 500,
      max_output_tokens: 1024,
      providers: { ollama: { model: 'llama-test', base_url: 'http://ollama:11434' } },
    });
  });

  it('sends the key only when one was typed, and the removal only when asked', () => {
    const base = settings({ providers: [{ ...anthropic, key_status: 'set' }, openai, ollama] });
    const values = toValues(base);
    expect(toUpdate(values, base).providers).toBeUndefined();

    values.providers.anthropic.apiKey = '  sk-test  ';
    expect(toUpdate(values, base).providers).toEqual({ anthropic: { api_key: 'sk-test' } });

    values.providers.anthropic.apiKey = '';
    values.providers.anthropic.clearKey = true;
    expect(toUpdate(values, base).providers).toEqual({ anthropic: { clear_api_key: true } });
  });

  it('saves the suggested address only once its provider is chosen', () => {
    const base = settings();
    const values = toValues(base);
    expect(toUpdate(values, base).providers).toBeUndefined();

    values.provider = 'openai_compatible';
    values.providers.openai_compatible.model = 'gpt-test';
    expect(toUpdate(values, base).providers).toEqual({
      openai_compatible: { model: 'gpt-test', base_url: 'https://api.openai.com/v1' },
    });
  });

  it('asks for the acknowledgement only for a provider outside South Africa that it does not cover', () => {
    const base = settings();
    const values = toValues(base);
    expect(needsAcknowledgement(values, base)).toBe(false);

    values.provider = 'anthropic';
    expect(needsAcknowledgement(values, base)).toBe(true);

    const covered = settings({
      active_provider: 'anthropic',
      acknowledgement: { acknowledged_at: '2026-10-27T10:00:00Z', current: true },
      providers: [{ ...anthropic, model: 'm', key_status: 'set', missing: [] }, openai, ollama],
    });
    expect(needsAcknowledgement(toValues(covered), covered)).toBe(false);

    const changed = toValues(covered);
    changed.provider = 'openai_compatible';
    expect(needsAcknowledgement(changed, covered)).toBe(true);
  });
});

describe('AI settings screen', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
    applyTerminology(i18n, {});
    mocked.fetchMe.mockResolvedValue(testUser);
    mocked.fetchMyRoles.mockResolvedValue([role('platform_admin', ['settings.manage'])]);
    mocked.fetchInstitution.mockResolvedValue(testInstitution);
    mocked.fetchAiSettings.mockResolvedValue(settings());
  });

  it('is linked from the admin page and refused to people without the permission', async () => {
    renderAt('/admin');
    expect(await screen.findByRole('link', { name: 'AI settings' })).toHaveAttribute(
      'href',
      '/admin/ai'
    );
  });

  it('warns with an alert when production has no encryption key of its own', async () => {
    mocked.fetchAiSettings.mockResolvedValue(
      settings({ encryption: { keys_stored_ok: false, rotation_needed: false } })
    );
    renderAt('/admin/ai');

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('API keys cannot be saved yet')).toBeInTheDocument();
    expect(alert).toHaveTextContent('SECRETS_ENCRYPTION_KEYS');
  });

  it('shows no encryption warning when the key is set', async () => {
    renderAt('/admin/ai');

    await screen.findByText('AI is off');
    expect(screen.queryByText('API keys cannot be saved yet')).not.toBeInTheDocument();
    expect(screen.queryByText('Saved keys use the older encryption key')).not.toBeInTheDocument();
  });

  it('says when saved keys still use the older key', async () => {
    mocked.fetchAiSettings.mockResolvedValue(
      settings({ encryption: { keys_stored_ok: true, rotation_needed: true } })
    );
    renderAt('/admin/ai');

    expect(await screen.findByText('Saved keys use the older encryption key')).toBeInTheDocument();
  });

  it('refuses people who may not manage settings', async () => {
    mocked.fetchMyRoles.mockResolvedValue([role('lecturer', ['curriculum.view'])]);
    renderAt('/admin/ai');
    expect(await screen.findByRole('heading', { name: 'No access' })).toBeInTheDocument();
    expect(mocked.fetchAiSettings).not.toHaveBeenCalled();
  });

  it('starts with AI off, nothing sent and the test button unavailable', async () => {
    renderAt('/admin/ai');

    expect(await screen.findByText('AI is off')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'AI settings' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /AI off/ })).toBeChecked();
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled();
    expect(screen.getByText('Choose and save a provider to test it.')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /Local-only mode/ })).toBeChecked();
    expect(screen.getByLabelText(/Refuse the request/)).toBeChecked();
    expect(screen.getByText(/This month: 0 calls, 0 tokens, USD 0\./)).toBeInTheDocument();
  });

  it('shows an error with a retry when the settings cannot be loaded', async () => {
    mocked.fetchAiSettings.mockRejectedValueOnce(new ApiError(500, 'boom'));
    renderAt('/admin/ai');

    expect(await screen.findByText("Couldn't load the AI settings")).toBeInTheDocument();
    mocked.fetchAiSettings.mockResolvedValue(settings());
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('AI is off')).toBeInTheDocument();
  });

  it('warns about text leaving South Africa and needs the acknowledgement before saving', async () => {
    renderAt('/admin/ai');
    await userEvent.click(await screen.findByRole('radio', { name: /Anthropic Claude/ }));

    const warning = screen.getByRole('region', { name: 'Text will be sent outside South Africa' });
    expect(within(warning).getByText(/never personal information/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Model'), 'claude-sonnet-5-5');
    await userEvent.type(screen.getByLabelText('API key'), 'sk-test-not-real');
    await userEvent.click(screen.getByRole('button', { name: 'Save AI settings' }));

    expect(await screen.findByText('Tick this to confirm you have read the warning.')).toBeInTheDocument();
    expect(mocked.updateAiSettings).not.toHaveBeenCalled();
  });

  it('saves the key write-only with the acknowledgement and then shows only that a key is saved', async () => {
    const saved = settings({
      active_provider: 'anthropic',
      local_only: false,
      acknowledgement: { acknowledged_at: '2026-10-27T10:00:00Z', current: true },
      status: { state: 'ready', reasons: [], budget_message: null },
      providers: [
        {
          ...anthropic,
          model: 'claude-sonnet-5-5',
          key_status: 'set',
          key_set_at: '2026-10-27T10:00:00Z',
          missing: [],
        },
        openai,
        ollama,
      ],
    });
    mocked.updateAiSettings.mockResolvedValue(saved);
    renderAt('/admin/ai');

    await userEvent.click(await screen.findByRole('radio', { name: /Anthropic Claude/ }));
    await userEvent.type(screen.getByLabelText('Model'), 'claude-sonnet-5-5');
    await userEvent.type(screen.getByLabelText('API key'), 'sk-test-not-real');
    await userEvent.click(screen.getByRole('switch', { name: /Local-only mode/ }));
    await userEvent.click(screen.getByLabelText(/I understand that curriculum text/));
    await userEvent.click(screen.getByRole('button', { name: 'Save AI settings' }));

    expect(await screen.findByText('AI settings saved.')).toBeInTheDocument();
    expect(mocked.updateAiSettings).toHaveBeenCalledWith({
      active_provider: 'anthropic',
      local_only: false,
      on_personal_data: 'refuse',
      monthly_cost_cap: '10.00',
      monthly_token_cap: 2000000,
      monthly_call_cap: 2000,
      max_calls_per_run: 500,
      max_output_tokens: 1024,
      acknowledge_outside_south_africa: true,
      providers: { anthropic: { model: 'claude-sonnet-5-5', api_key: 'sk-test-not-real' } },
    });
    // The key is gone from the screen; only its state remains.
    expect(screen.getByLabelText('API key')).toHaveValue('');
    expect(screen.getByText(/A key is saved\. It cannot be shown/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('sk-test-not-real');
    expect(screen.getByText('Ready: Anthropic Claude')).toBeInTheDocument();
    expect(screen.getByText(/Acknowledged on 27 October 2026/)).toBeInTheDocument();
  });

  it('shows the server reason when a save is refused', async () => {
    mocked.updateAiSettings.mockRejectedValue(
      new ApiError(422, 'Local-only mode is on. Only a provider on this server or network can be chosen.')
    );
    renderAt('/admin/ai');
    await userEvent.click(await screen.findByRole('radio', { name: /Ollama/ }));
    await userEvent.type(screen.getByLabelText('Model'), 'llama-test');
    await userEvent.type(screen.getByLabelText('Address'), 'http://ollama:11434');
    await userEvent.click(screen.getByRole('button', { name: 'Save AI settings' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The settings were not saved. Local-only mode is on.');
  });

  it('checks the limits before saving', async () => {
    renderAt('/admin/ai');
    await userEvent.clear(await screen.findByLabelText(/Monthly call limit/));
    await userEvent.type(screen.getByLabelText(/Monthly call limit/), 'many');
    await userEvent.clear(screen.getByLabelText('Most calls in one run'));
    await userEvent.click(screen.getByRole('button', { name: 'Save AI settings' }));

    expect(await screen.findByText('Enter a whole number, or leave empty.')).toBeInTheDocument();
    expect(screen.getByText('Fill in this field.')).toBeInTheDocument();
    expect(mocked.updateAiSettings).not.toHaveBeenCalled();
  });

  it('lets a limit be removed by leaving it empty', async () => {
    mocked.updateAiSettings.mockResolvedValue(settings());
    renderAt('/admin/ai');
    await userEvent.clear(await screen.findByLabelText(/Monthly token limit/));
    await userEvent.click(screen.getByRole('button', { name: 'Save AI settings' }));

    await waitFor(() =>
      expect(mocked.updateAiSettings).toHaveBeenCalledWith(
        expect.objectContaining({ monthly_token_cap: null })
      )
    );
  });

  it('offers the saved key for removal and says when it cannot be read', async () => {
    mocked.fetchAiSettings.mockResolvedValue(
      settings({
        providers: [{ ...anthropic, key_status: 'unreadable' }, openai, ollama],
        active_provider: 'anthropic',
        status: { state: 'blocked', reasons: ['not_configured'], budget_message: null },
      })
    );
    renderAt('/admin/ai');

    expect(await screen.findByText(/cannot be read with the current encryption keys/)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Remove the saved key' })).toBeInTheDocument();
    expect(screen.getByText('Blocked: Anthropic Claude')).toBeInTheDocument();
    expect(screen.getByText(/The provider is not complete/)).toBeInTheDocument();
  });

  it('states why a provider is blocked, including the budget message', async () => {
    mocked.fetchAiSettings.mockResolvedValue(
      settings({
        ...readyOllama,
        status: {
          state: 'blocked',
          reasons: ['local_only', 'acknowledgement_missing', 'budget_exceeded'],
          budget_message: 'The monthly limit of 5 AI calls is reached. It resets on 01 November 2026.',
        },
      })
    );
    renderAt('/admin/ai');

    expect(await screen.findByText(/Local-only mode is on, and this provider is not/)).toBeInTheDocument();
    expect(screen.getByText(/has not been acknowledged/)).toBeInTheDocument();
    expect(screen.getByText(/monthly limit of 5 AI calls is reached/)).toBeInTheDocument();
  });

  describe('test connection', () => {
    beforeEach(() => {
      mocked.fetchAiSettings.mockResolvedValue(readyOllama);
    });

    it('sends nothing until the button is pressed and reports the answer', async () => {
      mocked.testAiConnection.mockResolvedValue({
        ok: true,
        code: 'ok',
        message: 'The provider answered.',
        provider: 'ollama',
        model: 'llama-test',
        input_tokens: 26,
        output_tokens: 4,
        duration_ms: 120,
      });
      renderAt('/admin/ai');
      const button = await screen.findByRole('button', { name: 'Test connection' });
      expect(mocked.testAiConnection).not.toHaveBeenCalled();
      expect(screen.getByText(/No curriculum data is sent/)).toBeInTheDocument();

      await userEvent.click(button);

      expect(await screen.findByText('The provider answered. 26 tokens in, 4 out, 120 ms.')).toBeInTheDocument();
      expect(mocked.testAiConnection).toHaveBeenCalledTimes(1);
    });

    it('reports a failed test as an alert', async () => {
      mocked.testAiConnection.mockResolvedValue({
        ok: false,
        code: 'provider_error',
        message: 'The provider answered with status 401.',
        provider: 'ollama',
        model: 'llama-test',
        input_tokens: 0,
        output_tokens: 0,
        duration_ms: 0,
      });
      renderAt('/admin/ai');
      await userEvent.click(await screen.findByRole('button', { name: 'Test connection' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'The test failed. The provider answered with status 401.'
      );
    });

    it('asks to save first when the form has unsaved changes', async () => {
      renderAt('/admin/ai');
      const button = await screen.findByRole('button', { name: 'Test connection' });
      expect(button).toBeEnabled();

      fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'another' } });

      await waitFor(() => expect(button).toBeDisabled());
      expect(screen.getByText('Save your changes first. The test uses the saved settings.')).toBeInTheDocument();
    });
  });
});
