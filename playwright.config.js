const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests',
    retries: 1,
    use: { baseURL: 'http://localhost:7342', serviceWorkers: 'block' },
    projects: [
        { name: 'webkit-iphone', use: { ...devices['iPhone 14'] } },
        { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    ],
    webServer: {
        command: '.venv/bin/python3 server.py',
        url: 'http://localhost:7342',
        reuseExistingServer: true,
    },
});
