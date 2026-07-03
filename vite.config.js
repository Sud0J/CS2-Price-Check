import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Static build. In dev, proxy /api to the local Python price server (port 8000)
// so `npm run dev` and the built site behave the same.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
