import { expect, test } from '@playwright/test'

test('uploads, traces, and deterministically scrubs a real image', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  const pngBase64 = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 180
    const context = canvas.getContext('2d')!; context.fillStyle = 'white'; context.fillRect(0, 0, 320, 180)
    context.strokeStyle = 'black'; context.lineWidth = 8; context.beginPath(); context.arc(95, 90, 55, 0, Math.PI * 2); context.stroke()
    context.beginPath(); context.moveTo(170, 35); context.lineTo(285, 145); context.moveTo(285, 35); context.lineTo(170, 145); context.stroke()
    return canvas.toDataURL('image/png').split(',')[1]
  })
  await page.getByTestId('image-input').setInputFiles({ name: 'drawing.png', mimeType: 'image/png', buffer: Buffer.from(pngBase64, 'base64') })
  await expect(page.getByTestId('scene-block')).toHaveCount(1, { timeout: 20_000 })
  await expect(page.getByText(/Tracing sketch/)).toHaveCount(0)
  const canvas = page.getByTestId('preview-canvas')
  const start = await canvas.evaluate((element: HTMLCanvasElement) => element.toDataURL())
  await page.getByLabel('Scrub sketch').fill('2')
  await expect(page.getByText(/^2\.00 \/ 4\.00$/)).toBeVisible()
  const middleA = await canvas.evaluate((element: HTMLCanvasElement) => element.toDataURL())
  await page.getByLabel('Scrub sketch').fill('1')
  await page.getByLabel('Scrub sketch').fill('2')
  const middleB = await canvas.evaluate((element: HTMLCanvasElement) => element.toDataURL())
  expect(middleA).not.toBe(start); expect(middleB).toBe(middleA); expect(errors).toEqual([])
})
