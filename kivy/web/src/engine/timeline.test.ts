import { beforeEach, describe, expect, it } from 'vitest'
import { clipsOverlap, moveClip, nonOverlappingStart, projectDuration, resizeScene, sceneStarts, splitScene, trimClip } from './timeline'
import { defaultSketchSettings, type AudioClip, type Project, type Scene } from './types'
import { pxToTime, timeToPx } from './timeScale'
import { useProjectStore } from '../store/projectStore'

const scene = (id: string, duration: number, progressStart = 0, progressEnd = 1): Scene => ({ id, assetId: `asset-${id}`, duration, sketchDuration: duration, sketchRegions:[], progressStart, progressEnd, sketchSettings: defaultSketchSettings() })
const clip = (id: string, start: number, sourceIn = 0, sourceOut = 4): AudioClip => ({ id, assetId: 'audio', start, sourceIn, sourceOut, volume: 1, muted: false })
const project = (): Project => ({
  id: 'p', name: 'Test', fps: 30, width: 1920, height: 1080, background: '#fff', playbackSpeed:1,
  scenes: [scene('a', 2), scene('b', 3), scene('c', 4)], transitions: [],
  audioTracks: [{ id: 't1', name: 'One', muted: false, volume: 1, clips: [] }, { id: 't2', name: 'Two', muted: false, volume: 1, clips: [] }],
  assets: { audio: { id: 'audio', kind: 'audio', blobKey: 'audio', name: 'tone.mp3', meta: { duration: 20 } } },
})

describe('magnetic scene timeline', () => {
  it('derives contiguous scene starts', () => expect(sceneStarts(project().scenes)).toEqual([0, 2, 5]))
  it('ripples later starts when duration changes and enforces 0.5s minimum', () => {
    const value = project(); resizeScene(value, 'a', 6); expect(sceneStarts(value.scenes)).toEqual([0, 6, 9])
    resizeScene(value, 'a', 0.1); expect(value.scenes[0].duration).toBe(0.5); expect(sceneStarts(value.scenes)[1]).toBe(0.5)
  })
  it('splits duration and sketch progress without discontinuity', () => {
    const value = project(); value.scenes[0].progressStart = 0.2; value.scenes[0].progressEnd = 0.8
    const right = splitScene(value, 'a', 0.75, 'right')
    expect(value.scenes.map((item) => item.duration)).toEqual([0.75, 1.25, 3, 4])
    expect(value.scenes[0].progressEnd).toBeCloseTo(0.425); expect(right.progressStart).toBeCloseTo(0.425); expect(right.progressEnd).toBe(0.8)
  })
  it('rejects a split that creates an undersized scene', () => expect(() => splitScene(project(), 'a', 0.2)).toThrow(/0.5/))
  it('can split the newly-created segment repeatedly', () => {
    const value = project(); const firstRight = splitScene(value, 'a', 1, 'right-1'); const secondRight = splitScene(value, firstRight.id, 1.5, 'right-2')
    expect(secondRight.id).toBe('right-2')
    expect(value.scenes.slice(0, 3).map((item) => item.duration)).toEqual([1, .5, .5])
    expect(value.scenes.slice(0, 3).map((item) => item.id)).toEqual(['a', 'right-1', 'right-2'])
  })
})

describe('audio timeline math', () => {
  it('trims the source range and preserves timeline alignment', () => {
    const value = clip('x', 2, 1, 8); trimClip(value, 'left', 2, 10)
    expect(value).toMatchObject({ start: 4, sourceIn: 3, sourceOut: 8 }); trimClip(value, 'right', 8, 10); expect(value.sourceOut).toBe(10)
  })
  it('detects overlap and pushes a dropped clip to the next free point', () => {
    const first = clip('a', 0, 0, 4); const moving = clip('b', 1, 0, 3)
    expect(clipsOverlap(first, moving)).toBe(true); expect(nonOverlappingStart([first], moving, 1)).toBe(4)
  })
  it('moves clips between tracks without allowing same-track overlap', () => {
    const value = project(); const first = clip('a', 0, 0, 4); const moving = clip('b', 8, 0, 2)
    value.audioTracks[0].clips.push(first, moving); moveClip(value, 'b', 't2', 1); expect(value.audioTracks[1].clips[0].start).toBe(1)
    moveClip(value, 'b', 't1', 1); expect(value.audioTracks[0].clips.find((item) => item.id === 'b')?.start).toBe(4)
  })
  it('uses whichever of scenes or audio ends last', () => { const value = project(); value.audioTracks[0].clips.push(clip('x', 10)); expect(projectDuration(value)).toBe(14) })
})

describe('shared time scale and history', () => {
  it('round-trips seconds and pixels', () => expect(pxToTime(timeToPx(7.25, 80), 80)).toBe(7.25))
  beforeEach(() => useProjectStore.getState().replaceProject(project()))
  it('records each command as one undo entry and clears redo after a new edit', () => {
    useProjectStore.getState().resizeScene('a', 7); expect(useProjectStore.getState().past).toHaveLength(1)
    useProjectStore.getState().undo(); expect(useProjectStore.getState().project.scenes[0].duration).toBe(2)
    useProjectStore.getState().redo(); expect(useProjectStore.getState().project.scenes[0].duration).toBe(7)
    useProjectStore.getState().undo(); useProjectStore.getState().resizeScene('a', 5); expect(useProjectStore.getState().future).toHaveLength(0)
  })
  it('keeps fades only on the outside edges when audio is split', () => {
    const value=project();value.audioTracks[0].clips.push({...clip('x',0),fadeIn:1,fadeOut:2});useProjectStore.getState().replaceProject(value)
    const rightId=useProjectStore.getState().splitClip('x',2),clips=useProjectStore.getState().project.audioTracks[0].clips
    expect(clips.find(item=>item.id==='x')).toMatchObject({fadeIn:1,fadeOut:0,sourceOut:2})
    expect(clips.find(item=>item.id===rightId)).toMatchObject({fadeIn:0,fadeOut:2,sourceIn:2})
  })
  it('toggles sketch animation independently for each scene',()=>{
    useProjectStore.getState().setSceneSketchEnabled('a',false)
    expect(useProjectStore.getState().project.scenes[0].sketchSettings.enabled).toBe(false)
    expect(useProjectStore.getState().project.scenes[1].sketchSettings.enabled).toBe(true)
    useProjectStore.getState().undo()
    expect(useProjectStore.getState().project.scenes[0].sketchSettings.enabled).toBe(true)
  })
  it('moves a sketch region boundary without changing the combined drawing time',()=>{
    useProjectStore.getState().setSceneSketchRegions('a',[
      {id:'r1',name:'Face',duration:1,color:'#7c3aed',strokes:[]},
      {id:'r2',name:'Board',duration:1,color:'#0891b2',strokes:[]},
    ])
    useProjectStore.getState().resizeSketchRegionBoundary('a',0,.35)
    const regions=useProjectStore.getState().project.scenes[0].sketchRegions
    expect(regions.map(region=>region.duration)).toEqual([1.35,.65])
    expect(regions.reduce((sum,region)=>sum+region.duration,0)).toBe(2)
  })
})
