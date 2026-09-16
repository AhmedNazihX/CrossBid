/**
 * Unit tests for the web app: Vitest in jsdom, colocated as `*.test.ts(x)` beside the module
 * they protect, the way `.claude/rules/react/coding-style.md` asks.
 *
 * What these tests can hold is the pure logic and the component branches where a wrong
 * answer is silent — a countdown floored the wrong way, a poll that never stops, a rule
 * that drifted from the backend's, a warning headed "Not saved". What they cannot see is
 * layout or real CSS: jsdom has neither, so anything about a column, a sticky header or a
 * breakpoint belongs to the Playwright suite under `e2e/`, which this config deliberately
 * leaves alone.
 */
import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    // The same `@/*` alias `tsconfig.json` declares, so a test imports a module by the path
    // the app does and a move breaks both the same way.
    alias: { '@': fileURLToPath(new URL('.', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/*.test.{ts,tsx}'],
    // Playwright's specs are `*.spec.ts` under `e2e/`; excluding the folder outright means
    // a spec renamed by mistake cannot start running against a browser that is not there.
    exclude: ['node_modules/**', '.next/**', '.next-verify/**', 'e2e/**'],
  },
})
