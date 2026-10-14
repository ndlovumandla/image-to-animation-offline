/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/openverse': {
        target: 'https://api.openverse.org',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/openverse/, ''),
      },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
