import { expect, test } from '@playwright/test'

test('landing page introduces the project and hands over to the dashboard', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('blind spot')
  await page.screenshot({ path: 'test-results/landing.png', fullPage: true })

  // Section links scroll in place and must not open the dashboard.
  await page.getByRole('link', { name: 'How it works' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Signal to verdict.' })).toBeInViewport()

  // The floating corner button opens the dashboard from anywhere on the page.
  await page.getByRole('link', { name: /Open dashboard/ }).click()
  await expect(page).toHaveURL(/#overview$/)
  await expect(page.getByRole('heading', { name: 'Command overview', exact: true })).toBeVisible()

  await page.goBack()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('blind spot')

  // Workspace cards deep-link into the console.
  await page.getByRole('link', { name: /Network Intelligence/ }).click()
  await expect(page).toHaveURL(/#network$/)
  await expect(page.getByRole('heading', { name: 'Network intelligence', exact: true })).toBeVisible()

  await page.goBack()
  await page.getByRole('link', { name: /Launch Phantom Command/ }).last().click()
  await expect(page).toHaveURL(/#overview$/)
  expect(errors).toEqual([])
})

test('landing page fits a phone viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1)
  await page.screenshot({ path: 'test-results/landing-mobile.png', fullPage: true })
})
