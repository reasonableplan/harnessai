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
    },
  },
  test: {
    globals: true,
    environment: 'node',
    include: ['packages/*/src/**/*.test.ts'],
  },
});
