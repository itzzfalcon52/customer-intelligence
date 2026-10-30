import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api/auth': { target: 'http://127.0.0.1:3001', changeOrigin: true },
      '/api/backend': { target: 'http://127.0.0.1:3001', changeOrigin: true },
      '/api/v1': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
