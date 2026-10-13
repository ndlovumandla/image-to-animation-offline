import { describe, expect, it } from 'vitest'
import { frameState } from './renderer'
import { defaultSketchSettings, type Project } from './types'

const project: Project = {
  id: 'p', name: 'Render', fps: 30, width: 1920, height: 1080, background: '#fff', transitions: [], audioTracks: [], assets: {},
  scenes: [
    { id: 'a', assetId: 'image', duration: 4, progressStart: 0, progressEnd: 1, sketchSettings: defaultSketchSettings() },
    { id: 'b', assetId: 'image', duration: 2, progressStart: 0.4, progressEnd: 1, sketchSettings: defaultSketchSettings() },
  ],
}

describe('deterministic frame state', () => {
  it('returns identical state for identical project time', () => expect(frameState(project, 2)).toEqual(frameState(project, 2)))
  it('maps scene-local time to drawing and fill phases', () => {
    expect(frameState(project, 0)).toMatchObject({ localTime: 0, progress: 0, drawProgress: 0, fillOpacity: 0 })
    expect(frameState(project, 2).drawProgress).toBeCloseTo(2 / 3)
    expect(frameState(project, 4).progress).toBeCloseTo(0.4)
    expect(frameState(project, 6).fillOpacity).toBe(1)
  })
})
