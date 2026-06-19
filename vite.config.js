import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  root: 'static',
  base: '/static/dist/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'static/index.html'),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8185',
      '/login': 'http://localhost:8185',
      '/register': 'http://localhost:8185',
      '/library': 'http://localhost:8185',
      '/downloads': 'http://localhost:8185',
      '/status': 'http://localhost:8185',
      '/health': 'http://localhost:8185',
    },
  },
});
