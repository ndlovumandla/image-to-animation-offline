import { expect, test } from '@playwright/test'

test('sidebar tools, millisecond timing and file menu are functional', async ({ page }) => {
  await page.route('**/openverse/v1/audio/**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({results:[{id:'lesson',title:'Education theme',url:'https://media.test/lesson.wav',creator:'Open artist',license:'cc0'}]})}))
  await page.goto('/')
  const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=80;c.height=60;const x=c.getContext('2d')!;x.fillStyle='white';x.fillRect(0,0,80,60);x.fillStyle='black';x.fillRect(20,20,40,20);return c.toDataURL().split(',')[1]})
  await page.getByTestId('image-input').setInputFiles({name:'scene.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});await expect(page.getByTestId('scene-block')).toHaveCount(1,{timeout:20_000})
  await page.getByRole('button',{name:'Design'}).click();await page.getByLabel('Scene 1 duration milliseconds').fill('4321');await expect(page.getByLabel('Scene 1 duration milliseconds')).toHaveValue('4321');await page.getByLabel('Scene 1 hand').selectOption('left')
  await page.getByRole('button',{name:'Audio'}).click();await page.getByLabel('Search open audio').fill('educational');await page.getByLabel('Search open audio').press('Enter');await expect(page.getByText('Education theme')).toBeVisible()
  await page.getByRole('button',{name:'File'}).click();await expect(page.getByRole('button',{name:'New project'})).toBeVisible();await expect(page.getByRole('button',{name:'Save project file'})).toBeVisible();await expect(page.getByRole('button',{name:'Share editable copy'})).toBeVisible()
})
