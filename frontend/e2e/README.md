# End-to-end tests

Playwright journeys with axe-core accessibility checks (WCAG 2.2 A and AA), each run in a
light and a dark project. They run against a running stack, normally the Docker Compose
stack behind Caddy (ADR 006, ADR 026).

## Run locally

1. Start the stack (`deploy/`, see the install guide) and finish the first-run setup, or
   load the demo data: `docker compose exec api python -m app.cli load-demo`.
2. Create a platform admin for the tests (any name; the password is only for this stack):

   ```bash
   docker compose exec -e OCMP_ADMIN_PASSWORD=<password> api \
     python -m app.cli create-admin --email e2e.admin@example.org --name "Thandi Nkosi"
   ```

3. Put the credentials in `frontend/e2e/.env.local` (git-ignored; loaded by `playwright.config.ts`,
   values already in the environment win):

   ```
   E2E_EMAIL=e2e.admin@example.org
   E2E_PASSWORD=<password>
   ```

4. Install the browser once, then run the tests from `frontend/`:

   ```bash
   npx playwright install chromium firefox webkit
   npm run e2e
   ```

   The projects are `light` and `dark` (Chromium) and `firefox` and `webkit` (light theme only: the dark
   theme is the same CSS in every engine). CI runs all four. To run one: `npm run e2e -- --project=webkit`.
   Journeys that change a setting shared by every project (the explorer's competency switch) run in `light`
   only.

`E2E_BASE_URL` points the tests at another address (default `https://localhost`; the
certificate is not checked). After a frontend change, rebuild the web image first:
`docker compose up -d --build web`.

## Notes

- `auth.setup.ts` signs in once and saves the session in `e2e/.auth/` (git-ignored);
  later runs reuse it while it is valid. Sign-in is rate-limited, so tests must not sign
  in themselves. Tests of signed-out pages use `test.use({ storageState: SIGNED_OUT })`.
- `lecturer.setup.ts` makes (through the admin API) and signs in a lecturer once,
  `e2e.lecturer@example.org` with the password `<E2E_PASSWORD>-lecturer`, and saves the
  session in `e2e/.auth/lecturer.json`. Journeys that need a user with only a session role
  grant the role through the admin API and remove it afterwards.
- **Journeys leave nothing behind** (ADR 037). Each removes what it creates through the API:
  modules, phases, tag lists, imported frameworks (`DELETE /frameworks/{id}`), role grants, and
  `cleanup.teardown.ts` deletes the lecturer account after the run. Only the admin account from
  step 2 (made by you, not by the tests) stays. Any new journey that creates data must clean it
  up in `afterEach`, also when it fails. Never delete with SQL.
- Call `expectNoAccessibilityViolations(page)` on every new screen and state (for
  example an open menu or an error message).
- On failure, `playwright-report/` and `test-results/` hold traces and screenshots
  (`npx playwright show-report`).
