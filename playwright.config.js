const { defineConfig, devices } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  testMatch: 'browser.spec.js',
  timeout: 30000,
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'work/playwright-report', open: 'never' }]],
  outputDir: 'work/test-results',
  use: { baseURL: 'http://127.0.0.1:8765', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } }
  ],
  webServer: {
    command: 'python -m http.server 8765 --bind 127.0.0.1 --directory docs',
    url: 'http://127.0.0.1:8765',
    stdout: 'ignore',
    stderr: 'ignore',
    reuseExistingServer: !process.env.CI
  }
});
