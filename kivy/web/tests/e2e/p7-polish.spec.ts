import { expect, test } from '@playwright/test'

test('large timeline remains interactive and transport controls work', async ({ page }) => {
  await page.goto('/'); await page.evaluate(() => {
    const settings = { style: 'pencil' as const, detail: 0.5, lineWidth: 2, fillMode: 'fade' as const, showHand: true }; const waveform = [{ bucketSize: 4096, min: Array(200).fill(-0.5), max: Array(200).fill(0.5) }]
    const project = { id: 'stress', name: 'Stress Project', fps: 30, width: 1920, height: 1080, background: '#fff', transitions: [], scenes: Array.from({ length: 60 }, (_, i) => ({ id: `s${i}`, assetId: `img${i}`, duration: 10, progressStart: 0, progressEnd: 1, sketchSettings: settings })), audioTracks: Array.from({ length: 4 }, (_, i) => ({ id: `t${i}`, name: `Track ${i}`, muted: false, volume: 1, clips: [{ id: `c${i}`, assetId: `audio${i}`, start: 0, sourceIn: 0, sourceOut: 600, volume: 1, muted: false }] })), assets: Object.fromEntries([...Array.from({ length: 60 }, (_, i) => [`img${i}`, { id: `img${i}`, kind: 'image', blobKey: `img${i}`, name: `Image ${i}`, meta: { width: 1, height: 1 } }]), ...Array.from({ length: 4 }, (_, i) => [`audio${i}`, { id: `audio${i}`, kind: 'audio', blobKey: `audio${i}`, name: `Audio ${i}`, meta: { duration: 600, sampleRate: 48000 }, waveform }])]) }
    ;(window as unknown as { __SKETCH_STORE__: { getState(): { replaceProject(value: unknown): void } } }).__SKETCH_STORE__.getState().replaceProject(project)
  })
  await expect(page.getByTestId('scene-block')).toHaveCount(60); await expect(page.getByTestId('timeline-audio-lane')).toHaveCount(4); await page.getByLabel('Timeline zoom').fill('20'); await expect(page.getByLabel('Timeline zoom')).toHaveValue('20')
  await page.getByLabel('Skip to end').click(); await expect(page.getByLabel('Scrub sketch')).toHaveValue('600'); await page.getByLabel('Skip to start').click(); await expect(page.getByLabel('Scrub sketch')).toHaveValue('0')
  await page.getByLabel('Master mute').click(); await expect(page.getByLabel('Master mute')).toHaveAttribute('aria-pressed', 'true'); await page.getByLabel('Project name').fill('My Sketch Film'); await expect(page.getByLabel('Project name')).toHaveValue('My Sketch Film')
})
