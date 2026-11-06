import { describe, expect, it } from 'vitest'
import { frameState, sketchRegionProgress, transitionState } from './renderer'
import { defaultSketchSettings, type Project } from './types'

const project: Project = {
  id: 'p', name: 'Render', fps: 30, width: 1920, height: 1080, background: '#fff', playbackSpeed:1, transitions: [], audioTracks: [], assets: {},
  scenes: [
    { id: 'a', assetId: 'image', duration: 4, sketchDuration: 4, sketchRegions:[], progressStart: 0, progressEnd: 1, sketchSettings: defaultSketchSettings() },
    { id: 'b', assetId: 'image', duration: 2, sketchDuration: 2, sketchRegions:[], progressStart: 0.4, progressEnd: 1, sketchSettings: defaultSketchSettings() },
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
  it('finishes drawing at sketch duration while the scene continues', () => {
    const fast = structuredClone(project); fast.scenes[0].duration = 5; fast.scenes[0].sketchDuration = 1
    expect(frameState(fast, .5).progress).toBeCloseTo(.5)
    expect(frameState(fast, 1).progress).toBe(1)
    expect(frameState(fast, 4.5).progress).toBe(1)
    expect(frameState(fast, 4.5).localTime).toBeCloseTo(4.5)
  })
  it('plays brushed sketch regions sequentially',()=>{
    const scene=structuredClone(project.scenes[0]);scene.sketchRegions=[{id:'r1',name:'First',duration:1,color:'#f00',strokes:[]},{id:'r2',name:'Second',duration:2,color:'#0f0',strokes:[]}]
    expect(sketchRegionProgress(scene,.5).map(item=>item.progress)).toEqual([.5,0])
    expect(sketchRegionProgress(scene,2).map(item=>item.progress)).toEqual([1,.5])
    expect(sketchRegionProgress(scene,4).map(item=>item.progress)).toEqual([1,1])
  })
})

describe('transition timing', () => {
  it('activates the configured transition only in the outgoing window', () => {
    project.transitions = [{ id: 't', fromSceneId: 'a', toSceneId: 'b', type: 'wipe', duration: 1 }]
    expect(transitionState(project, 2.99)).toBeUndefined(); expect(transitionState(project, 3)?.progress).toBe(0); expect(transitionState(project, 3.5)?.progress).toBe(0.5); expect(transitionState(project, 4)).toBeUndefined()
  })
})
