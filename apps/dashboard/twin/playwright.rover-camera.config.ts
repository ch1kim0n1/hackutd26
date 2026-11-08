import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/camera', workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:4188', viewport: { width: 1440, height: 1000 },
    launchOptions: { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined, args: ['--enable-unsafe-swiftshader'] },
  },
  webServer: {
    command: 'npm run dev -- --port 4188 --strictPort', url: 'http://127.0.0.1:4188',
    env: { VITE_ROVER_CAMERA_URL: 'http://127.0.0.1:19999' }, reuseExistingServer: false,
  },
})
