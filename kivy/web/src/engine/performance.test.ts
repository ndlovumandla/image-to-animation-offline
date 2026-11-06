import { expect, it } from 'vitest'
import { projectDuration, sceneStarts } from './timeline'
import { computeWaveformLevels } from './waveform'
import { defaultSketchSettings, type Project } from './types'

it('handles 60 scenes, four 10-minute tracks, and waveform peaks within a responsive budget', () => {
  const project: Project = { id: 'stress', name: 'Stress', fps: 30, width: 1920, height: 1080, background: '#fff', playbackSpeed:1, transitions: [], assets: {}, scenes: Array.from({ length: 60 }, (_, i) => ({ id: `s${i}`, assetId: 'image', duration: 10, sketchDuration: 10, sketchRegions:[], progressStart: 0, progressEnd: 1, sketchSettings: defaultSketchSettings() })), audioTracks: Array.from({ length: 4 }, (_, i) => ({ id: `t${i}`, name: `Track ${i}`, muted: false, volume: 1, clips: [{ id: `c${i}`, assetId: 'audio', start: 0, sourceIn: 0, sourceOut: 600, volume: 1, muted: false }] })) }
  const before = performance.now(); for (let i = 0; i < 1000; i += 1) { sceneStarts(project.scenes); projectDuration(project) } const samples = new Float32Array(600_000); samples[300_000] = 1; const levels = computeWaveformLevels([samples], [256, 1024, 4096]); const elapsed = performance.now() - before
  expect(projectDuration(project)).toBe(600); expect(levels).toHaveLength(3); expect(elapsed).toBeLessThan(1000)
})
