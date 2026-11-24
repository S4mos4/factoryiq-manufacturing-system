import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [tailwindcss()],
  server: { proxy: { '/api': process.env.FACTORYIQ_API_ORIGIN || 'http://127.0.0.1:8000' } },
});
