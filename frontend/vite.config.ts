import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/docs': { target: 'http://localhost:8000', changeOrigin: true },
      '/openapi.json': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/docs': { target: 'http://localhost:8000', changeOrigin: true },
      '/openapi.json': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks: {
          maplibre: ['maplibre-gl'],
          motion: ['gsap', 'gsap/ScrollTrigger'],
          vendor: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
        },
      },
    },
  },
});