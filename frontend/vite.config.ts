import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { defineConfig } from 'vite';

// note: pdf.js CMap + standard-font assets are copied into public/pdfjs/
// by scripts/copy-pdfjs-assets.mjs (run from the build/dev npm scripts),
// so vite serves them in dev and emits them to dist/ on build. the loader
// points at <base>/pdfjs/{cmaps,standard_fonts}/ — see lib/pdf.ts.

// react core + router share one long-lived vendor chunk (scheduler is
// react-dom's runtime dependency, so it belongs with it).
const vendorModules =
  /node_modules\/(react|react-dom|react-router(-dom)?|scheduler)\//;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 'hidden' generates source maps but does not reference them in
    // bundles, so error trackers (e.g. Sentry) can still resolve
    // stack traces while end users with browser dev tools cannot
    // recover full source from the deployed build.
    sourcemap: 'hidden',
    // vite 8 (rolldown) drops the object form of manualChunks; these
    // codeSplitting groups reproduce the previous vendor/query/state
    // chunks by matching module paths instead of package names.
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'vendor', test: vendorModules },
            { name: 'query', test: /node_modules\/@tanstack\// },
            { name: 'state', test: /node_modules\/zustand\// },
          ],
        },
      },
    },
  },
});
