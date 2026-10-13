import type { WaveformLevel } from './types'

export function computeWaveformLevels(channels: readonly Float32Array[], bucketSizes: readonly number[]): WaveformLevel[] {
  const length = channels[0]?.length ?? 0
  return bucketSizes.map((bucketSize) => {
    const buckets = Math.ceil(length / bucketSize); const min = new Array<number>(buckets); const max = new Array<number>(buckets)
    for (let bucket = 0; bucket < buckets; bucket += 1) { let low = 1; let high = -1; const end = Math.min(length, (bucket + 1) * bucketSize); for (let i = bucket * bucketSize; i < end; i += 1) for (const channel of channels) { const sample = channel[i] ?? 0; low = Math.min(low, sample); high = Math.max(high, sample) } min[bucket] = low; max[bucket] = high }
    return { bucketSize, min, max }
  })
}
