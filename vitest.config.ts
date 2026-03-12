import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: {
      '@agent/core': path.resolve(__dirname, 'packages/core/src/index.ts'),
      '@agent/director': path.resolve(__dirname, 'packages/agent-director/src/index.ts'),
      '@agent/git': path.resolve(__dirname, 'packages/agent-git/src/index.ts'),
      '@agent/backend': path.resolve(__dirname, 'packages/agent-backend/src/index.ts'),
      '@agent/frontend': path.resolve(__dirname, 'packages/agent-frontend/src/index.ts'),
      '@agent/docs': path.resolve(__dirname, 'packages/agent-docs/src/index.ts'),
      '@agent/dashboard-server': path.resolve(__dirname, 'packages/dashboard-server/src/index.ts'),
      '@agent/main': path.resolve(__dirname, 'packages/main/src/index.ts'),
    },
  },
  test: {
    globals: true,
    environment: 'node',
    include: ['packages/*/src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['packages/*/src/**/*.ts'],
      exclude: ['**/*.test.ts', '**/*.d.ts', '**/dist/**', '**/node_modules/**'],
    },
  },
});
