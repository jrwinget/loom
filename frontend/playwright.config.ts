import { defineConfig, devices } from '@playwright/test';

// the smoke spec walks one user journey through a real lite backend
// (scripts/e2e-backend.sh) and the vite dev server. state is
// stateful across steps, so a single worker and no parallelism.
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }]]
    : 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // reuseExistingServer stays false everywhere: the spec requires a
  // fresh database (first-run flow), so an already-running backend
  // or dev server on these ports must fail the run loudly
  webServer: [
    {
      command: 'bash ../scripts/e2e-backend.sh',
      url: 'http://127.0.0.1:8000/api/v1/health',
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: 'pnpm dev',
      url: 'http://localhost:3000',
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
