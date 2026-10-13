import { computeWaveformLevels } from './waveform'

self.onmessage = (event: MessageEvent<{ channels: Float32Array[]; bucketSizes: number[] }>) => {
  self.postMessage(computeWaveformLevels(event.data.channels, event.data.bucketSizes))
}
