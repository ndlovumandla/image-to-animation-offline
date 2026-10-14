import { expect, test } from '@playwright/test'

test('edits an uploaded image with text and shapes then creates a sketch scene', async ({ page }) => {
  await page.route('https://api.iconify.design/search**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ icons: ['lucide:graduation-cap'] }) }))
  await page.goto('/')
  const png = await page.evaluate(() => {
    const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180
    const context=canvas.getContext('2d')!;context.fillStyle='white';context.fillRect(0,0,320,180);context.fillStyle='#2563eb';context.fillRect(90,40,140,100)
    return canvas.toDataURL('image/png').split(',')[1]
  })
  await page.getByTestId('image-input').setInputFiles({ name:'lesson.png', mimeType:'image/png', buffer:Buffer.from(png,'base64') })
  await expect(page.getByTestId('scene-block')).toHaveCount(1,{timeout:20_000})
  await page.getByTitle('Edit image').click()
  await expect(page.getByText('Image editor',{exact:true})).toBeVisible()
  await expect(page.getByLabel('Search elements')).toBeVisible()
  await page.getByRole('button',{name:'Remove background'}).click();await expect(page.getByText('Background removed',{exact:true})).toBeVisible()
  await expect(page.getByRole('button',{name:'Undo image edit'})).toBeVisible();await expect(page.getByRole('button',{name:/Magic erase brush/})).toBeVisible()
  await page.getByRole('button',{name:/Magic erase brush/}).click();const mask=page.getByTestId('magic-erase-mask'),box=await mask.boundingBox();if(!box)throw new Error('Mask canvas missing');await page.mouse.move(box.x+box.width*.4,box.y+box.height*.4);await page.mouse.down();await page.mouse.move(box.x+box.width*.6,box.y+box.height*.6,{steps:8});await page.mouse.up();await page.getByRole('button',{name:'Remove painted'}).click();await expect(page.locator('div[role="status"]')).toContainText(/removed/i)
  await page.getByRole('button',{name:'+ Text'}).click();await page.getByRole('button',{name:/Shape/}).click()
  await page.getByRole('button',{name:'Use in video'}).click()
  await expect(page.getByTestId('scene-block')).toHaveCount(2,{timeout:20_000})
})
