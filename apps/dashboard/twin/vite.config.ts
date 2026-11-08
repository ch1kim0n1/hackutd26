import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { host: '127.0.0.1' },
  build: { rolldownOptions: { input: { command: fileURLToPath(new URL('./index.html', import.meta.url)), lab: fileURLToPath(new URL('./lab.html', import.meta.url)), legacy: fileURLToPath(new URL('./legacy.html', import.meta.url)) } } },
})
