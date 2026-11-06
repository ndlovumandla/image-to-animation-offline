/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      // Make `npm run dev` reachable from other devices on the local network.
      // Use `npm run dev:local` when an intentionally localhost-only server is wanted.
      host: '0.0.0.0',
      proxy: {
        '/openverse': {
          target: 'https://api.openverse.org',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/openverse/, ''),
        },
        '/commons': {
          target: 'https://commons.wikimedia.org',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/commons/, ''),
        },
        '/api': {
          target: env.BG_API_TARGET || 'http://127.0.0.1:7000',
          changeOrigin: true,
        },
      },
    },
    test: { environment: 'node', include: ['src/**/*.test.ts'] },
  }
})
