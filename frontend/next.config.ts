import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Emits .next/standalone with a self-contained server.js, so the Docker
  // runtime stage needs neither node_modules nor the npm lockfile.
  output: 'standalone',

  // The API is a separate process on a separate origin (see docs/project-plan.md
  // -> "Frontend <-> backend boundary"). Nothing is proxied through Next.js.
  reactStrictMode: true,
}

export default nextConfig
