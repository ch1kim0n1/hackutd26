import { expect, test } from '@playwright/test'

test('camera feed is marked live only while fresh and does not fall back to a simulated image', async ({ page }) => {
  let fresh = true
  await page.route('http://127.0.0.1:19999/health', async route => {
    await route.fulfill({ status: 200, headers: { 'access-control-allow-origin': '*' }, json: { frame_age_s: fresh ? 0.1 : 12, timestamp_utc: '2026-11-08T14:00:00Z' } })
  })
  await page.route('http://127.0.0.1:19999/stream.mjpg', async route => {
    const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
    await route.fulfill({ status: 200, contentType: 'image/png', body: image })
  })
  await page.goto('/#rover')
  const panel = page.getByTestId('physical-camera')
  await expect(panel.getByText('CAM 01 / LIVE')).toBeVisible()
  await expect(panel.getByRole('img', { name: 'Live rover camera' })).toBeVisible()
  fresh = false
  await expect(panel.getByText('Rover camera unavailable or stale')).toBeVisible({ timeout: 7000 })
  await expect(panel.getByText('CAM 01 / OFFLINE')).toBeVisible()
  await expect(panel.getByRole('img', { name: 'Live rover camera' })).toHaveCount(0)
  await expect(page.getByRole('img', { name: /Simulated rover camera/ })).toHaveCount(0)
})
