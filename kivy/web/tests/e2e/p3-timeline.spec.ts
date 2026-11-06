import { expect, test, type Page } from '@playwright/test'

async function png(page: Page, variant: number): Promise<Buffer> {
  const value = await page.evaluate((offset) => { const canvas = document.createElement('canvas'); canvas.width = 120; canvas.height = 80; const context = canvas.getContext('2d')!; context.fillStyle = 'white'; context.fillRect(0, 0, 120, 80); context.strokeStyle = 'black'; context.lineWidth = 5; context.strokeRect(10 + offset, 10, 70, 55); return canvas.toDataURL('image/png').split(',')[1] }, variant)
  return Buffer.from(value, 'base64')
}

function wav(frequency: number, seconds = 2, rate = 8000): Buffer { const samples = seconds * rate; const output = Buffer.alloc(44 + samples * 2); output.write('RIFF', 0); output.writeUInt32LE(36 + samples * 2, 4); output.write('WAVEfmt ', 8); output.writeUInt32LE(16, 16); output.writeUInt16LE(1, 20); output.writeUInt16LE(1, 22); output.writeUInt32LE(rate, 24); output.writeUInt32LE(rate * 2, 28); output.writeUInt16LE(2, 32); output.writeUInt16LE(16, 34); output.write('data', 36); output.writeUInt32LE(samples * 2, 40); for (let i = 0; i < samples; i += 1) output.writeInt16LE(Math.round(Math.sin(2 * Math.PI * frequency * i / rate) * 10000), 44 + i * 2); return output }

test('scene timeline resizes, splits, duplicates, reorders, deletes and zooms', async ({ page }) => {
  await page.goto('/'); const input = page.getByTestId('image-input')
  await input.setInputFiles({ name: 'one.png', mimeType: 'image/png', buffer: await png(page, 0) }); await page.getByRole('button',{name:'Add one.png to timeline'}).click(); await expect(page.getByTestId('scene-block')).toHaveCount(1)
  await input.setInputFiles({ name: 'two.png', mimeType: 'image/png', buffer: await png(page, 12) }); await page.getByRole('button',{name:'Add two.png to timeline'}).click(); await expect(page.getByTestId('scene-block')).toHaveCount(2)
  const sketchHandle=page.getByTestId('sketch-duration-handle').first(),sketchBox=await sketchHandle.boundingBox();if(!sketchBox)throw new Error('Sketch completion handle unavailable');await page.mouse.move(sketchBox.x+sketchBox.width/2,sketchBox.y+sketchBox.height/2);await page.mouse.down();await page.mouse.move(sketchBox.x-155,sketchBox.y+sketchBox.height/2);await page.mouse.up();await expect(sketchHandle).toHaveAttribute('aria-valuenow','2000')
  const firstWidth = await page.getByTestId('scene-block').first().evaluate((element) => element.getBoundingClientRect().width)
  const handle = page.getByTestId('scene-right-handle').first(); await handle.scrollIntoViewIfNeeded(); const box = await handle.boundingBox(); if (!box) throw new Error('Resize handle unavailable')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down(); await page.mouse.move(box.x + 85, box.y + box.height / 2); await page.mouse.up()
  await expect.poll(() => page.getByTestId('scene-block').first().evaluate((element) => element.getBoundingClientRect().width)).toBeGreaterThan(firstWidth + 60)
  await page.getByTestId('scene-block').first().click(); await page.getByRole('button', { name: 'Duplicate' }).click(); await expect(page.getByTestId('scene-block')).toHaveCount(3)
  await page.getByLabel('Scrub sketch').fill('1'); await page.getByTestId('scene-block').first().click(); await page.getByRole('button', { name: 'Split' }).click(); await expect(page.getByTestId('scene-block')).toHaveCount(4)
  await page.getByTestId('scene-drag').first().dragTo(page.getByTestId('scene-block').last()); await expect(page.getByTestId('scene-block')).toHaveCount(4)
  await page.getByTestId('scene-block').first().click(); await page.keyboard.press('Delete'); await expect(page.getByTestId('scene-block')).toHaveCount(3)
  const beforeZoom = await page.getByTestId('scene-block').first().evaluate((element) => element.getBoundingClientRect().width); await page.getByLabel('Timeline zoom').fill('160'); await expect.poll(() => page.getByTestId('scene-block').first().evaluate((element) => element.getBoundingClientRect().width)).toBeGreaterThan(beforeZoom * 1.8)
  await page.keyboard.press('Control+z'); await expect(page.getByTestId('scene-block')).toHaveCount(4); await page.keyboard.press('Control+Shift+z'); await expect(page.getByTestId('scene-block')).toHaveCount(3)
})

test('a video scene can be split repeatedly without reselecting each new segment', async ({ page }) => {
  await page.goto('/'); const input = page.getByTestId('image-input')
  await input.setInputFiles({ name: 'repeat.png', mimeType: 'image/png', buffer: await png(page, 4) }); await page.getByRole('button',{name:'Add repeat.png to timeline'}).click()
  await page.getByTestId('scene-block').click()
  for (const cut of ['1', '2', '3']) {
    await page.getByLabel('Scrub sketch').fill(cut)
    await page.getByRole('button', { name: 'Split' }).click()
  }
  await expect(page.getByTestId('scene-block')).toHaveCount(4)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('audio clips trim, move across tracks, split and delete', async ({ page }) => {
  await page.goto('/'); const input = page.getByTestId('audio-input'); await input.setInputFiles({ name: 'one.wav', mimeType: 'audio/wav', buffer: wav(300) }); await page.getByRole('button',{name:'Add one.wav to timeline'}).click(); await input.setInputFiles({ name: 'two.wav', mimeType: 'audio/wav', buffer: wav(500) }); await page.getByRole('button',{name:'Add two.wav to timeline'}).click(); await expect(page.getByTestId('audio-clip')).toHaveCount(2)
  const right = page.getByTestId('clip-right-handle').first(); await right.scrollIntoViewIfNeeded(); const box = await right.boundingBox(); if (!box) throw new Error('Audio trim handle unavailable'); const width = await page.getByTestId('audio-clip').first().evaluate((element) => element.getBoundingClientRect().width)
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down(); await page.mouse.move(box.x - 35, box.y + box.height / 2); await page.mouse.up(); await expect.poll(() => page.getByTestId('audio-clip').first().evaluate((element) => element.getBoundingClientRect().width)).toBeLessThan(width - 20)
  const lanes = page.getByTestId('timeline-audio-lane'); await page.getByTestId('clip-drag').first().dragTo(lanes.nth(1), { targetPosition: { x: 400, y: 40 } }); await expect(page.getByTestId('audio-clip')).toHaveCount(2)
  await page.getByLabel('Scrub sketch').fill('0.5'); await page.getByTestId('audio-clip').first().click(); await page.getByRole('button', { name: 'Split' }).click(); await expect(page.getByTestId('audio-clip')).toHaveCount(3)
  await page.getByTestId('audio-clip').last().click(); await page.getByRole('button', { name: 'Delete' }).click(); await expect(page.getByTestId('audio-clip')).toHaveCount(2)
})
