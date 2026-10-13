import { describe, expect, it } from 'vitest'
import { computeWaveformLevels } from './waveform'

describe('waveform peaks', () => {
  it('places known clicks in the exact source-time buckets at every resolution', () => {
    const samples = new Float32Array(8192); samples[1024] = 1; samples[4096] = -0.75
    const levels = computeWaveformLevels([samples], [256, 1024, 4096])
    expect(levels[0].max[4]).toBe(1); expect(levels[0].min[16]).toBe(-0.75)
    expect(levels[1].max[1]).toBe(1); expect(levels[1].min[4]).toBe(-0.75)
    expect(levels[2].max[0]).toBe(1); expect(levels[2].min[1]).toBe(-0.75)
  })
})
