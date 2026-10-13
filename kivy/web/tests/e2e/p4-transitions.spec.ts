import { expect, test } from '@playwright/test'

test('transition marker cycles fade, slide, wipe and none', async ({ page }) => {
  await page.goto('/'); const base64 = await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 80; canvas.height = 60; const context = canvas.getContext('2d')!; context.fillStyle = 'white'; context.fillRect(0, 0, 80, 60); context.strokeStyle = 'black'; context.lineWidth = 5; context.strokeRect(10, 10, 60, 40); return canvas.toDataURL().split(',')[1] }); const input = page.getByTestId('image-input')
  await input.setInputFiles({ name: 'a.png', mimeType: 'image/png', buffer: Buffer.from(base64, 'base64') }); await input.setInputFiles({ name: 'b.png', mimeType: 'image/png', buffer: Buffer.from(base64, 'base64') })
  const marker = page.getByTestId('transition-marker'); await expect(marker).toHaveText('+'); await marker.click(); await expect(marker).toHaveText('fade'); await marker.click(); await expect(marker).toHaveText('slide'); await marker.click(); await expect(marker).toHaveText('wipe'); await marker.click(); await expect(marker).toHaveText('+')
})
