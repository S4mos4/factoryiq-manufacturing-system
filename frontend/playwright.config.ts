import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  workers: 1,
  retries: 0,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.FACTORYIQ_E2E_URL || 'http://127.0.0.1:8071',
    trace: 'retain-on-failure',
  },
});
