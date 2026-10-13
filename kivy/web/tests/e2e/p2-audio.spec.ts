import { expect, test } from '@playwright/test'

function wav(frequency: number, seconds = 1.5, rate = 8000): Buffer {
  const samples = Math.floor(seconds * rate); const output = Buffer.alloc(44 + samples * 2)
  output.write('RIFF', 0); output.writeUInt32LE(36 + samples * 2, 4); output.write('WAVEfmt ', 8); output.writeUInt32LE(16, 16); output.writeUInt16LE(1, 20); output.writeUInt16LE(1, 22); output.writeUInt32LE(rate, 24); output.writeUInt32LE(rate * 2, 28); output.writeUInt16LE(2, 32); output.writeUInt16LE(16, 34); output.write('data', 36); output.writeUInt32LE(samples * 2, 40)
  for (let i = 0; i < samples; i += 1) output.writeInt16LE(Math.round(Math.sin(2 * Math.PI * frequency * i / rate) * 10000), 44 + i * 2)
  return output
}

test('overlapping tracks play, seek, mute and change volume live', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', (error) => errors.push(error.message)); await page.goto('/')
  const input = page.getByTestId('audio-input')
  await input.setInputFiles({ name: 'voice.wav', mimeType: 'audio/wav', buffer: wav(440) })
  await expect(page.getByTestId('audio-track')).toHaveCount(1)
  await input.setInputFiles({ name: 'music.wav', mimeType: 'audio/wav', buffer: wav(660) })
  await expect(page.getByTestId('audio-track')).toHaveCount(2); await expect(page.getByTestId('waveform')).toHaveCount(2)
  await page.getByRole('button', { name: 'Play' }).click(); await expect(page.getByTestId('scheduled-audio')).toHaveText('2')
  await page.waitForTimeout(250); await expect(page.getByText(/^0\.[12-9]\d \/ 1\.50$/)).toBeVisible()
  await page.getByRole('button', { name: 'Mute voice.wav' }).click(); await expect(page.getByRole('button', { name: 'Mute voice.wav' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByLabel('Volume music.wav').fill('0.25'); await expect(page.getByLabel('Volume music.wav')).toHaveValue('0.25')
  await page.getByLabel('Scrub sketch').fill('0.5'); await expect(page.getByTestId('scheduled-audio')).toHaveText('2')
  await page.getByRole('button', { name: 'Pause' }).click(); expect(errors).toEqual([])
})
