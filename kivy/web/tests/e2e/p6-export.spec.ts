import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import ffprobe from 'ffprobe-static'

function wav(seconds = 1, rate = 8000): Buffer { const samples = seconds * rate; const output = Buffer.alloc(44 + samples * 2); output.write('RIFF', 0); output.writeUInt32LE(36 + samples * 2, 4); output.write('WAVEfmt ', 8); output.writeUInt32LE(16, 16); output.writeUInt16LE(1, 20); output.writeUInt16LE(1, 22); output.writeUInt32LE(rate, 24); output.writeUInt32LE(rate * 2, 28); output.writeUInt16LE(2, 32); output.writeUInt16LE(16, 34); output.write('data', 36); output.writeUInt32LE(samples * 2, 40); for (let i = 0; i < samples; i += 1) output.writeInt16LE(Math.round(Math.sin(2 * Math.PI * 440 * i / rate) * 9000), 44 + i * 2); return output }

test('exports a verified H.264/AAC MP4', async ({ page }) => {
  test.setTimeout(120_000); await page.goto('/'); const png = await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 160; canvas.height = 90; const context = canvas.getContext('2d')!; context.fillStyle = 'white'; context.fillRect(0, 0, 160, 90); context.strokeStyle = 'black'; context.lineWidth = 6; context.strokeRect(20, 15, 120, 60); return canvas.toDataURL().split(',')[1] })
  await page.getByTestId('image-input').setInputFiles({ name: 'export.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') }); await page.getByRole('button',{name:'Add export.png to timeline'}).click(); await expect(page.getByTestId('scene-block')).toHaveCount(1)
  await page.getByTestId('audio-input').setInputFiles({ name: 'export.wav', mimeType: 'audio/wav', buffer: wav() }); await page.getByRole('button',{name:'Add export.wav to timeline'}).click(); await expect(page.getByTestId('audio-clip')).toHaveCount(1)
  await page.getByRole('slider',{name:'Video speed',exact:true}).fill('2');await page.getByLabel('Project name').click();await expect.poll(()=>page.evaluate(()=>(window as unknown as {__SKETCH_STORE__:{getState():{project:{playbackSpeed:number}}}}).__SKETCH_STORE__.getState().project.playbackSpeed)).toBe(2);await expect(page.getByLabel('Current video speed')).toHaveText('2.00×')
  const downloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: 'Export MP4' }).click(); const download = await downloadEvent; const path = await download.path(); if (!path) throw new Error('MP4 download path unavailable')
  const probePath = typeof ffprobe === 'string' ? ffprobe : ffprobe.path; const details = JSON.parse(execFileSync(probePath, ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', path], { encoding: 'utf8' })) as { streams: Array<{ codec_type: string; codec_name: string }>; format: { duration: string } }
  expect(details.streams).toEqual(expect.arrayContaining([expect.objectContaining({ codec_type: 'video', codec_name: 'h264' }), expect.objectContaining({ codec_type: 'audio', codec_name: 'aac' })])); expect(Number(details.format.duration)).toBeGreaterThanOrEqual(1.96); expect(Number(details.format.duration)).toBeLessThanOrEqual(2.04)
  const base64 = readFileSync(path).toString('base64'); const playback = await page.evaluate(async (encoded) => { const bytes = Uint8Array.from(atob(encoded), (value) => value.charCodeAt(0)); const video = document.createElement('video'); video.muted = true; video.src = URL.createObjectURL(new Blob([bytes], { type: 'video/mp4' })); document.body.replaceChildren(video); await new Promise<void>((resolve, reject) => { video.oncanplay = () => resolve(); video.onerror = () => reject(new Error('Browser could not play exported MP4')) }); await video.play(); const deadline = performance.now() + 2000; while (video.currentTime <= 0 && performance.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 50)); return { duration: video.duration, currentTime: video.currentTime } }, base64)
  expect(playback.duration).toBeGreaterThanOrEqual(1.96); expect(playback.duration).toBeLessThanOrEqual(2.04); expect(playback.currentTime).toBeGreaterThan(0)
})

test('splitting audio does not reduce volume or quality across the MP4', async ({ page }) => {
  test.setTimeout(120_000)
  await page.goto('/')
  // Simulate Brave Shields in-place AudioBuffer.getChannelData attenuation and track AudioEncoder.flush calls
  await page.evaluate(() => {
    const origGetChannelData = AudioBuffer.prototype.getChannelData
    AudioBuffer.prototype.getChannelData = function (channel: number) {
      const data = origGetChannelData.call(this, channel)
      for (let i = 0; i < data.length; i += 1) data[i] *= 0.995
      return data
    }
    const origAudioFlush = AudioEncoder.prototype.flush
    ;(window as unknown as { __AUDIO_FLUSH_COUNT__: number }).__AUDIO_FLUSH_COUNT__ = 0
    AudioEncoder.prototype.flush = function () {
      ;(window as unknown as { __AUDIO_FLUSH_COUNT__: number }).__AUDIO_FLUSH_COUNT__ += 1
      return origAudioFlush.call(this)
    }
  })
  const png = await page.evaluate(() => { const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;const context=canvas.getContext('2d')!;context.fillStyle='white';context.fillRect(0,0,160,90);return canvas.toDataURL().split(',')[1] })
  await page.getByTestId('image-input').setInputFiles({ name:'split.png',mimeType:'image/png',buffer:Buffer.from(png,'base64') })
  await page.getByRole('button',{name:'Add split.png to timeline'}).click()
  await page.getByTestId('audio-input').setInputFiles({ name:'split.wav',mimeType:'audio/wav',buffer:wav(4,48000) })
  await page.getByRole('button',{name:'Add split.wav to timeline'}).click()
  await page.getByTestId('audio-clip').click()
  for (const cut of ['1','2','3']) { await page.getByLabel('Scrub sketch').fill(cut);await page.getByRole('button',{name:'Split',exact:true}).click() }
  await expect(page.getByTestId('audio-clip')).toHaveCount(4)
  const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Export MP4'}).click();const download=await downloadEvent,path=await download.path();if(!path)throw new Error('MP4 download path unavailable')
  const flushCount = await page.evaluate(() => (window as unknown as { __AUDIO_FLUSH_COUNT__: number }).__AUDIO_FLUSH_COUNT__)
  expect(flushCount).toBe(1)
  const encoded=readFileSync(path).toString('base64')
  const levels=await page.evaluate(async(base64)=>{const bytes=Uint8Array.from(atob(base64),value=>value.charCodeAt(0)),context=new AudioContext(),buffer=await context.decodeAudioData(bytes.buffer),channel=new Float32Array(buffer.length),rate=buffer.sampleRate;buffer.copyFromChannel(channel,0);const rms=(from:number,to:number)=>{let sum=0,count=0;for(let i=Math.floor(from*rate);i<Math.min(channel.length,Math.floor(to*rate));i++){sum+=channel[i]*channel[i];count++}return Math.sqrt(sum/Math.max(1,count))};const result=[rms(.1,.9),rms(1.1,1.9),rms(2.1,2.9),rms(3.1,3.9)];await context.close();return result},encoded)
  expect(Math.max(...levels)/Math.min(...levels)).toBeLessThan(1.03)
})
