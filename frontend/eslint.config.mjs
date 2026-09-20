import { dirname } from 'path'
import { fileURLToPath } from 'url'
import { FlatCompat } from '@eslint/eslintrc'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const compat = new FlatCompat({
  baseDirectory: __dirname,
})

const eslintConfig = [
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    // `.next-verify/**` is the verification build next.config.ts documents: generated output,
    // and `make lint` would fail for as long as it exists without this entry.
    ignores: [
      'node_modules/**',
      '.next/**',
      '.next-verify/**',
      // pdf.js's own runtime assets, copied in by `scripts/copy-pdfjs-assets.mjs` (ADR-0105).
      // Vendored emscripten output: not ours to lint, and 160 warnings deep if it is.
      'public/pdfjs/**',
      'out/**',
      'build/**',
      'next-env.d.ts',
      // Playwright's output (npm run test:e2e): a generated report and traces, never source.
      'test-results/**',
      'playwright-report/**',
      'blob-report/**',
      '.playwright/**',
    ],
  },
]

export default eslintConfig
