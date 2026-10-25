import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests against a running stack (Docker Compose behind Caddy), by default
 * https://localhost. Each journey runs in the light and the dark theme. See e2e/README.md.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'https://localhost',
    // Caddy's local certificate authority is not trusted by the test browser.
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'light',
      use: { ...devices['Desktop Chrome'], colorScheme: 'light', storageState: 'e2e/.auth/signed-in.json' },
      dependencies: ['setup'],
    },
    {
      name: 'dark',
      use: { ...devices['Desktop Chrome'], colorScheme: 'dark', storageState: 'e2e/.auth/signed-in.json' },
      dependencies: ['setup'],
    },
  ],
});
