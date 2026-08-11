import { defineConfig, devices } from "@playwright/test";

const chromeChannel = process.env.CI ? undefined : "chrome";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  globalTimeout: 120_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], ...(chromeChannel ? { channel: chromeChannel } : {}) },
    },
  ],
});
