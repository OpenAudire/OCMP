import fs from 'node:fs';

import { expect, request, test as setup } from '@playwright/test';

import { credentials, SIGNED_IN_STATE } from './support';

// One sign-in for the whole run: the API slows down and then blocks repeated sign-ins
// (rate limiting), so tests reuse this session, and local reruns reuse it while it is
// still valid.
setup('sign in', async ({ page, baseURL }) => {
  if (fs.existsSync(SIGNED_IN_STATE)) {
    const api = await request.newContext({
      baseURL,
      ignoreHTTPSErrors: true,
      storageState: SIGNED_IN_STATE,
    });
    const me = await api.get('/api/v1/auth/me');
    await api.dispose();
    if (me.ok()) return;
  }

  const { email, password } = credentials();
  await page.goto('/login');
  await page.getByRole('textbox', { name: 'Email' }).fill(email);
  await page.getByRole('textbox', { name: 'Password' }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('button', { name: /account menu for/i })).toBeVisible();
  await page.context().storageState({ path: SIGNED_IN_STATE });
});
