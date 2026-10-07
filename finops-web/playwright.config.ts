import { defineConfig, devices } from '@playwright/test';

/**
 * The journey runs against the built application, served by vite preview.
 *
 * The API is stubbed at the network boundary rather than run alongside. What
 * this proves is that the real bundle, the real components and the real shell
 * carry a user from a session through to the organization map, and that the
 * honesty rules survive the build rather than only the test renderer. What it
 * does not prove is the live stack, which needs a database, the API and real
 * accounts, and is recorded as not performed here.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:9736',
    trace: 'on-first-retry',
    // Every journey reads the settled screen. Motion leaves nothing behind once it ends, so a
    // screen at rest is the same with it or without, and a journey that ran mid fade measured a
    // half drawn panel: axe found contrast failures on a tab still fading in, and a figure read
    // before it arrived. e2e/motion.spec.ts proves the motion itself, with motion on.
    contextOptions: { reducedMotion: 'reduce' },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 9736 --strictPort',
    url: 'http://127.0.0.1:9736',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
