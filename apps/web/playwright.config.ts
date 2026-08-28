import { defineConfig, devices } from "@playwright/test";

/**
 * CI runs `playwright test --grep @smoke` (see e2e/smoke.spec.ts). This
 * config boots the real Next.js dev server against whatever DATABASE_URL /
 * NEXT_PUBLIC_API_URL is in the environment -- the smoke test exercises the
 * real Better Auth + JWT/JWKS + FastAPI path end to end, so it needs
 * Postgres and services/api actually running (see docker-compose.yml).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }]],
  timeout: 60_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "pnpm dev",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
