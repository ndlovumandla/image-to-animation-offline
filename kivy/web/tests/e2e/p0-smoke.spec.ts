import { expect, test } from '@playwright/test'

test('P0 harness loads in a real browser without runtime errors', async ({ page }) => {
  const pageErrors: string[] = []
  const consoleErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })

  await page.goto('/')
  await expect(page).toHaveTitle('Sketch Video Studio')
  await expect(page.getByRole('heading', { name: 'Untitled project' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'P0 project model' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Redo' })).toBeVisible()
  await expect(page.locator('pre')).toContainText('[]')

  expect(pageErrors).toEqual([])
  expect(consoleErrors).toEqual([])
})
