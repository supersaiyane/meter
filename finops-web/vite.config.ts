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
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: false,
  },
});
