import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { expectNoAccessibilityViolations, LECTURER_STATE, openApp } from './support';

// Admin > AI settings. A platform admin turns AI from off to a local provider and to a cloud
// provider, meets the warning about text leaving South Africa, the local-only refusal, the
// blocked state and the write-only key. Everything is a fictional key and a closed local port:
// no real provider or network address is ever contacted.
//
// The "Test connection" button is deliberately not pressed here: every press writes an AI run
// that, by design, can never be deleted (ADR 016), and this suite leaves nothing behind
// (ADR 037). The button is covered by the API tests (a mocked provider) and the unit tests;
// the browser checks that it is off while AI is off and while the form has unsaved changes.
//
// Clean-up (also when a step fails): AI off, local-only on, refuse, default limits, keys removed
// and the provider details emptied, through the API. The acknowledgement is withdrawn by turning
// AI off. Empty provider rows remain (they hold defaults); the audit log keeps the history.
const API = '/api/v1/ai';
const FAKE_KEY = 'sk-e2e-not-a-real-key-0000';

async function resetAi(page: Page): Promise<void> {
  const api: APIRequestContext = page.request;
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === 'ocmp_csrf');
  if (!csrf) return;
  const empty = {
    model: null,
    temperature: null,
    input_price_per_mtok: null,
    output_price_per_mtok: null,
  };
  const response = await api.patch(`${API}/settings`, {
    headers: { 'X-CSRF-Token': csrf.value },
    data: {
      active_provider: 'null',
      local_only: true,
      on_personal_data: 'refuse',
      monthly_cost_cap: '10.00',
      monthly_token_cap: 2000000,
      monthly_call_cap: 2000,
      max_calls_per_run: 500,
      max_output_tokens: 1024,
      providers: {
        anthropic: { ...empty, clear_api_key: true },
        openai_compatible: { ...empty, base_url: null, clear_api_key: true },
        ollama: { ...empty, base_url: null },
      },
    },
  });
  expect(response.ok(), await response.text()).toBe(true);
}

test.describe('AI settings', () => {
  test.afterEach(async ({ page }) => {
    await openApp(page, '/');
    await resetAi(page);
  });

  test('off by default, local provider, cloud provider with warning, blocked state, write-only key', async ({
    page,
  }) => {
    await openApp(page, '/admin');
    await page.getByRole('link', { name: 'AI settings' }).click();

    // 1. Off by default.
    await expect(page.getByRole('heading', { level: 1, name: 'AI settings' })).toBeVisible();
    await expect(page.getByText('AI is off', { exact: true })).toBeVisible();
    await expect(page.getByRole('radio', { name: 'AI off' })).toBeChecked();
    await expect(page.getByRole('switch', { name: /Local-only mode/ })).toBeChecked();
    await expect(page.getByRole('button', { name: 'Test connection' })).toBeDisabled();
    await expectNoAccessibilityViolations(page);

    // 2. A cloud provider: the warning, and the refusals.
    await page.getByRole('radio', { name: /Anthropic Claude/ }).check();
    await expect(
      page.getByRole('region', { name: 'Text will be sent outside South Africa' })
    ).toBeVisible();
    await expect(page.getByLabel('API key')).toHaveValue('');
    await page.getByLabel('Model').fill('claude-sonnet-5-5');
    await page.getByLabel('API key').fill(FAKE_KEY);
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    await expect(page.getByText('Tick this to confirm you have read the warning.')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await page.getByLabel(/I understand that curriculum text/).check();
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    // Local-only mode is still on: the server refuses and says why.
    await expect(page.getByRole('alert')).toContainText('Local-only mode is on');
    await expectNoAccessibilityViolations(page);

    // 3. Local-only off: saved, but blocked because a cost limit needs prices.
    await page.getByRole('switch', { name: /Local-only mode/ }).uncheck();
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    await expect(page.getByText('AI settings saved.')).toBeVisible();
    await expect(page.getByText('Blocked: Anthropic Claude')).toBeVisible();
    await expect(page.getByText(/no prices, so cost cannot be counted/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Test connection' })).toBeEnabled();
    await expectNoAccessibilityViolations(page);

    // 4. The key is write-only: only its state is shown, after saving and after a reload.
    await expect(page.getByLabel('API key')).toHaveValue('');
    await expect(page.getByText(/A key is saved\. It cannot be shown/)).toBeVisible();
    await page.reload();
    await expect(page.getByText('Blocked: Anthropic Claude')).toBeVisible();
    await expect(page.getByLabel('API key')).toHaveValue('');
    expect(await page.content()).not.toContain(FAKE_KEY);

    // 5. Prices make it ready. Unsaved changes switch the test button off.
    await page.getByLabel(/Price per million input tokens/).fill('1');
    await expect(page.getByRole('button', { name: 'Test connection' })).toBeDisabled();
    await expect(page.getByText('Save your changes first.')).toBeVisible();
    await page.getByLabel(/Price per million output tokens/).fill('5');
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    await expect(page.getByText('Ready: Anthropic Claude')).toBeVisible();
    await expect(page.getByText(/Acknowledged on/)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // 6. A local provider on a closed port: saved and ready (nothing is contacted).
    await page.getByRole('radio', { name: /Ollama/ }).check();
    await page.getByLabel('Model').fill('e2e-model');
    await page.getByLabel('Address').fill('http://127.0.0.1:9');
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    await expect(page.getByText('Ready: Ollama')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // 7. Limits are checked before they are sent.
    await page.getByLabel(/Monthly call limit/).fill('many');
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    await expect(page.getByText('Enter a whole number, or leave empty.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('turning AI off withdraws the acknowledgement', async ({ page }) => {
    await openApp(page, '/admin/ai');
    await page.getByRole('radio', { name: /Anthropic Claude/ }).check();
    await page.getByLabel('Model').fill('claude-sonnet-5-5');
    await page.getByLabel('API key').fill(FAKE_KEY);
    await page.getByLabel(/Price per million input tokens/).fill('1');
    await page.getByLabel(/Price per million output tokens/).fill('5');
    await page.getByRole('switch', { name: /Local-only mode/ }).uncheck();
    await page.getByLabel(/I understand that curriculum text/).check();
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    await expect(page.getByText('Ready: Anthropic Claude')).toBeVisible();

    await page.getByRole('radio', { name: 'AI off' }).check();
    await page.getByRole('button', { name: 'Save AI settings' }).click();
    await expect(page.getByText('AI is off', { exact: true })).toBeVisible();

    // Choosing the same provider again asks for a fresh acknowledgement.
    await page.getByRole('radio', { name: /Anthropic Claude/ }).check();
    await expect(page.getByLabel(/I understand that curriculum text/)).toBeVisible();
    await expect(page.getByLabel(/I understand that curriculum text/)).not.toBeChecked();
  });
});

test.describe('AI settings, a lecturer', () => {
  test.use({ storageState: LECTURER_STATE });

  test('cannot open the screen', async ({ page }) => {
    await page.goto('/admin/ai');
    await expect(page.getByRole('heading', { name: 'No access' })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});
