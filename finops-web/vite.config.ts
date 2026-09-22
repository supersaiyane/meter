import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// defineConfig comes from vitest/config rather than vite, so the test block is
// typed rather than accepted and ignored.
//
// The environment is jsdom, not node. Every component here is asserted on what
// it renders, because a figure rendered without its provenance is the defect
// the whole design exists to prevent, and that cannot be checked without a DOM.
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', sourcemap: true },
  // The port comes from the environment when something else assigns one,
  // because vite does not read PORT on its own. Without this it silently
  // picks the next free port, which looks like a started server to whoever
  // asked for a specific one and is then unreachable. strictPort is on only
  // when a port was assigned, so a plain npm run dev still steps aside when
  // the compose stack already holds 5173.
  server: {
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
    strictPort: Boolean(process.env.PORT),
    // Without this the dev server answers /api itself, and the SPA fallback
    // returns index.html with status 200. Every screen then fails on
    // "Unexpected token '<'", which reads as a product defect and is not one.
    // The api container publishes 8000, and mounts its routes under /api
    // already, so nothing is rewritten.
    proxy: {
      '/api': {
        target: process.env.METER_API_ORIGIN ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // Processed rather than stubbed. With css false a raw stylesheet import
    // returns an empty string, and the token assertions would pass over nothing
    // while looking like they checked the palette.
    css: true,
    // Only the source is tested. Anything under a build output directory is a
    // second copy that can pass while the source fails.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules/**', 'dist/**', 'dist-types/**', 'dist-types-node/**'],
  },
});
