import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://localhost:8123', channel: 'chrome' },
  webServer: {
    command: '".venv/Scripts/python.exe" -m uvicorn server.main:app --port 8123',
    cwd: '..',
    url: 'http://localhost:8123/api/health',
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
