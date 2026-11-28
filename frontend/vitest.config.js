import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    env: { VITE_API_BASE_URL: '/api' },
    maxWorkers: 4,
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.js'],
    clearMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      // Explicit white-box assignment scope, not whole-application or UI coverage.
      include: [
        'src/services/api.js',
        'src/services/adapters.js',
        'src/utils/github.js',
        'src/components/graph/graphAdapter.js',
        'src/components/graph/graphLayout.js',
      ],
      thresholds: { statements: 95, branches: 85, functions: 95, lines: 95 },
    },
  },
});
