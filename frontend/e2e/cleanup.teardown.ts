import fs from 'node:fs';

import { expect, request, test as teardown } from '@playwright/test';

import { LECTURER_EMAIL, LECTURER_STATE, SIGNED_IN_STATE } from './support';

// After the whole run: delete the lecturer account that lecturer.setup.ts made, so the local
// demo stack keeps no test accounts (DELETE /users/{id}, ADR 037). It is made again, through
// the API, by the next run. The admin account used to sign in is the operator's (README).
teardown('delete the test lecturer', async ({ baseURL }) => {
  const admin = await request.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
    storageState: SIGNED_IN_STATE,
  });
  try {
    const csrf = (await admin.storageState()).cookies.find((cookie) => cookie.name === 'ocmp_csrf');
    if (!csrf) throw new Error('No CSRF cookie: is the admin session valid?');
    const found = await admin.get(`/api/v1/users?search=${encodeURIComponent(LECTURER_EMAIL)}`);
    expect(found.ok()).toBe(true);
    const { items } = (await found.json()) as { items: { id: string; email: string }[] };
    for (const user of items.filter((item) => item.email === LECTURER_EMAIL)) {
      const deleted = await admin.delete(`/api/v1/users/${user.id}`, {
        headers: { 'X-CSRF-Token': csrf.value },
      });
      expect(deleted.status(), await deleted.text()).toBe(204);
    }
  } finally {
    await admin.dispose();
  }
  fs.rmSync(LECTURER_STATE, { force: true });
});
