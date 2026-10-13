import { expect, test } from '@playwright/test'

test('autosave restores media and sketchproj round-trips with assets', async ({ page }) => {
  await page.goto('/'); await expect(page.getByTestId('save-status')).toHaveText('Saved')
  const base64 = await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 100; canvas.height = 60; const context = canvas.getContext('2d')!; context.fillStyle = 'white'; context.fillRect(0, 0, 100, 60); context.strokeStyle = 'black'; context.lineWidth = 5; context.strokeRect(10, 10, 80, 40); return canvas.toDataURL().split(',')[1] })
  await page.getByTestId('image-input').setInputFiles({ name: 'saved.png', mimeType: 'image/png', buffer: Buffer.from(base64, 'base64') }); await expect(page.getByTestId('scene-block')).toHaveCount(1); await expect(page.getByTestId('save-status')).toHaveText('Saved', { timeout: 10_000 })
  await page.reload(); await expect(page.getByTestId('scene-block')).toHaveCount(1, { timeout: 15_000 }); await expect(page.getByTestId('save-status')).toHaveText('Saved')
  const downloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: 'Download project' }).click(); const download = await downloadEvent; expect(download.suggestedFilename()).toMatch(/\.sketchproj$/); const path = await download.path(); if (!path) throw new Error('Project download path unavailable')
  await page.getByTestId('scene-block').click(); await page.getByRole('button', { name: 'Delete' }).click(); await expect(page.getByTestId('scene-block')).toHaveCount(0)
  await page.getByTestId('project-input').setInputFiles(path); await expect(page.getByTestId('scene-block')).toHaveCount(1, { timeout: 15_000 })
})
