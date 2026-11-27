import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 180000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4175",
    actionTimeout: 15000,
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 960 },
  },
  webServer: {
    command: "npm run dev -- --port 4175 --strictPort --bypass-lock",
    url: "http://127.0.0.1:4175",
    reuseExistingServer: false,
  },
  reporter: "list",
});
