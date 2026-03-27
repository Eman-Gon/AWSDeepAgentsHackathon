import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { resolve } from 'path';

export default defineConfig({
  plugins: [preact()],
  envDir: resolve(__dirname, '..'),
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: 'dist',
  },
  server: {
    proxy: {
      // Proxy /api requests to the Python SSE backend during development.
      // The configure callback disables response buffering so SSE events
      // flush to the browser immediately instead of being held until the
      // full response completes.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          // When the upstream sends headers, remove transfer-encoding
          // and ensure the browser treats this as a streaming response
          proxy.on('proxyRes', (proxyRes) => {
            // Disable buffering in http-proxy so SSE events flush in real time
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
    },
  },
});
