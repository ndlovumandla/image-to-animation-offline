import type { WaveformLevel } from './types'

export async function decodeAudio(file: Blob, context: AudioContext): Promise<{ buffer: AudioBuffer; waveform: WaveformLevel[] }> {
  const buffer = await context.decodeAudioData(await file.arrayBuffer())
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, index) => {
    if (typeof buffer.copyFromChannel === 'function') {
      const copy = new Float32Array(buffer.length)
      buffer.copyFromChannel(copy, index)
      return copy
    }
    return new Float32Array(buffer.getChannelData(index))
  })
  const worker = new Worker(new URL('./waveformWorker.ts', import.meta.url), { type: 'module' })
  try {
    const waveform = await new Promise<WaveformLevel[]>((resolve, reject) => {
      worker.onmessage = (event: MessageEvent<WaveformLevel[]>) => resolve(event.data)
      worker.onerror = (event) => reject(new Error(event.message || 'Waveform worker failed'))
      worker.postMessage({ channels, bucketSizes: [256, 1024, 4096] }, channels.map((channel) => channel.buffer))
    })
    return { buffer, waveform }
  } finally { worker.terminate() }
}
