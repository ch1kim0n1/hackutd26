import { expect, test } from '@playwright/test'

// Live-mode integration via the REPLAY fixture transport (?live=fixture).
// Verifies backend-shaped rows flow into the dashboard, provenance stays
// honest, refresh resyncs without duplication, and demo mode is untouched.

test('live mode streams fixture backend data with honest REPLAY labels', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto('/?live=fixture')
  // Switch to LIVE via the header mode switcher.
  await page.getByRole('button', { name: 'LIVE', exact: true }).click()
  await expect(page.getByText('REPLAY', { exact: false }).first()).toBeVisible({ timeout: 10000 })
  // Fixture incident appears in the incident queue.
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Incident Center' }).click()
  await expect(page.getByText('Unregistered BLE transmitter near rack hall')).toBeVisible({ timeout: 10000 })
  // Live entities carry REPLAY provenance in their detail text.
  await expect(page.getByText(/REPLAY · /).first()).toBeVisible()
  // Demo-only controls are hidden/disabled in live mode.
  await expect(page.getByRole('button', { name: 'Create incident', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Start simulation', exact: true })).toHaveCount(0)
  // Network workspace shows backend devices.
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Network Intelligence' }).click()
  await expect(page.getByTestId('command-device-grid')).toContainText('PUCK-WIFI-01', { timeout: 10000 })
  expect(errors).toEqual([])
})

test('refresh in live mode resyncs without duplicating events', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('phantom-command-mode', 'live'))
  await page.goto('/?live=fixture')
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: 'Incident Center' }).click()
  await expect(page.getByText('Unregistered BLE transmitter near rack hall')).toBeVisible({ timeout: 10000 })
  const countBefore = await page.locator('.sec-incident-card').count()
  await page.reload()
  await expect(page.getByText('Unregistered BLE transmitter near rack hall')).toBeVisible({ timeout: 10000 })
  const countAfter = await page.locator('.sec-incident-card').count()
  expect(countAfter).toBe(countBefore) // wholesale resync — no duplicates
  // Switch back to demo: simulation restored.
  await page.getByRole('button', { name: 'DEMO', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Start simulation', exact: true })).toBeVisible()
})
