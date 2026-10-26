import fs from 'node:fs';

import { expect, request, test as setup } from '@playwright/test';

import { credentials, LECTURER_EMAIL, LECTURER_STATE, lecturerPassword, SIGNED_IN_STATE } from './support';

// A lecturer who holds only a session role is made once through the API by the test
// admin (the saved session of auth.setup.ts), then signs in once; journeys reuse the
// saved session because sign-in is rate-limited. The account stays between runs (it
// has no roles until a journey grants one, and the journeys remove what they grant).
setup('sign in as a lecturer', async ({ page, baseURL }) => {
  if (fs.existsSync(LECTURER_STATE)) {
    const api = await request.newContext({
      baseURL,
      ignoreHTTPSErrors: true,
      storageState: LECTURER_STATE,
    });
    const me = await api.get('/api/v1/auth/me');
    await api.dispose();
    if (me.ok()) return;
  }

  credentials();
  const admin = await request.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
    storageState: SIGNED_IN_STATE,
  });
  const state = await admin.storageState();
  const csrf = state.cookies.find((cookie) => cookie.name === 'ocmp_csrf');
  if (!csrf) throw new Error('No CSRF cookie: is the admin session valid?');
  const found = await admin.get(`/api/v1/users?search=${encodeURIComponent(LECTURER_EMAIL)}`);
  expect(found.ok()).toBe(true);
  const { items } = (await found.json()) as { items: { email: string }[] };
  if (!items.some((user) => user.email === LECTURER_EMAIL)) {
    const created = await admin.post('/api/v1/users', {
      headers: { 'X-CSRF-Token': csrf.value },
      data: {
        email: LECTURER_EMAIL,
        display_name: 'Sipho Lecturer',
        password: lecturerPassword(),
      },
    });
    expect(created.status(), await created.text()).toBe(201);
  }
  await admin.dispose();

  await page.goto('/login');
  await page.getByRole('textbox', { name: 'Email' }).fill(LECTURER_EMAIL);
  await page.getByRole('textbox', { name: 'Password' }).fill(lecturerPassword());
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('button', { name: /account menu for/i })).toBeVisible();
  await page.context().storageState({ path: LECTURER_STATE });
});
