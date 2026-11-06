import { expect, test } from '@playwright/test'

test('transition seam configures style and millisecond duration', async ({ page }) => {
  await page.goto('/'); const base64 = await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 80; canvas.height = 60; const context = canvas.getContext('2d')!; context.fillStyle = 'white'; context.fillRect(0, 0, 80, 60); context.strokeStyle = 'black'; context.lineWidth = 5; context.strokeRect(10, 10, 60, 40); return canvas.toDataURL().split(',')[1] }); const input = page.getByTestId('image-input')
  await input.setInputFiles({ name: 'a.png', mimeType: 'image/png', buffer: Buffer.from(base64, 'base64') }); await page.getByRole('button',{name:'Add a.png to timeline'}).click(); await input.setInputFiles({ name: 'b.png', mimeType: 'image/png', buffer: Buffer.from(base64, 'base64') }); await page.getByRole('button',{name:'Add b.png to timeline'}).click()
  const marker = page.getByTestId('transition-marker'); await expect(marker).toHaveText('+'); await marker.click(); await page.getByLabel('Transition style').selectOption('fade');await expect(marker).toHaveText('fade');await page.getByLabel('Transition duration').fill('0.735');await expect(page.getByText('Duration: 0.735s')).toBeVisible()
})
