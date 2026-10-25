import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

/** Matches modules of the named packages in node_modules (either path separator). */
function vendor(...packages: string[]): RegExp {
  return new RegExp(`node_modules[\\\\/](${packages.join('|')})[\\\\/]`);
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
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
    outDir: 'dist',
    sourcemap: true,
    rolldownOptions: {
      output: {
        // Libraries in their own chunks: smaller files, and they stay cached across
        // releases because they change far less often than the app.
        codeSplitting: {
          groups: [
            { name: 'react', test: vendor('react', 'react-dom', 'react-router', 'scheduler') },
            { name: 'mantine', test: vendor('@mantine/[^\\\\/]+') },
            { name: 'data', test: vendor('@tanstack/[^\\\\/]+', 'axios') },
            { name: 'i18n', test: vendor('i18next', 'react-i18next', 'i18next-browser-languagedetector') },
          ],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
    },
  },
});
