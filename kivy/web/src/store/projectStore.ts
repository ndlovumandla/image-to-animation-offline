import { produce } from 'immer'
import { create } from 'zustand'
import { createEmptyProject, defaultSketchSettings, normalizeProject, type Asset, type Project, type SketchRegion, type TransitionType } from '../engine/types'
import { moveClip, resizeScene, splitScene, trimClip } from '../engine/timeline'
import { createId } from '../engine/id'

interface ProjectState {
  project: Project; past: Project[]; future: Project[]
  addAsset(asset: Asset): void
  addSceneFromAsset(assetId: string, targetIndex?: number): void
  addAudioFromAsset(assetId: string, start?: number, trackId?: string): void
  addImageScene(asset: Asset): void
  addAudioTrack(asset: Asset): void; setTrackMuted(id: string, muted: boolean): void; setTrackVolume(id: string, volume: number): void
  replaceProject(project: Project): void; resizeScene(id: string, duration: number): void
  splitScene(id: string, time: number): string; trimClip(id: string, edge: 'left' | 'right', delta: number): void
  moveClip(id: string, trackId: string, start: number): void; undo(): void; redo(): void
  resizeSceneLeft(id: string, delta: number): void; reorderScene(id: string, targetIndex: number): void
  duplicateScene(id: string): void; deleteScene(id: string): void; deleteClip(id: string): void; splitClip(id: string, time: number): string
  setTransition(fromId: string, type: TransitionType, duration?: number): void
  setProjectName(name: string): void; setClipMuted(id: string, muted: boolean): void; setClipVolume(id: string, volume: number): void
  setSceneDurationMs(id: string, milliseconds: number): void; setSketchDurationMs(id: string, milliseconds: number): void; setSceneSketchEnabled(id:string,enabled:boolean):void; setSceneHand(id: string, show: boolean, style: 'classic'|'left'|'marker'): void
  setSceneSketchRegions(id:string,regions:SketchRegion[]):void
  resizeSketchRegionBoundary(id:string,boundaryIndex:number,delta:number):void
  setProjectBackground(color: string): void; newProject(): void; setAllTransitions(type: TransitionType, duration: number): void
  setPlaybackSpeed(speed: number): void
}

const clone = (project: Project): Project => structuredClone(project)
const cloneRegions = (regions: readonly SketchRegion[]): SketchRegion[] => regions.map(region=>({...region,strokes:region.strokes.map(stroke=>({...stroke,points:stroke.points.map(point=>({...point}))}))}))
export const useProjectStore = create<ProjectState>((set) => {
  // Immer projects are immutable snapshots. Keeping those references makes undo O(1)
  // and avoids cloning image traces and waveform arrays on every timeline gesture.
  const commit = (mutate: (draft: Project) => void) => set((state) => ({ project: produce(state.project, mutate), past: [...state.past, state.project], future: [] }))
  return {
    project: createEmptyProject(), past: [], future: [],
    addAsset: (asset) => commit((project) => { project.assets[asset.id] = asset }),
    addSceneFromAsset: (assetId, targetIndex) => commit((project) => {
      const asset = project.assets[assetId]
      if (!asset || asset.kind !== 'image') throw new Error('Only an uploaded image can be placed in the video lane')
      const scene = { id: createId(), assetId, duration: 4, sketchDuration: 4, sketchRegions:[], progressStart: 0, progressEnd: 1, sketchSettings: defaultSketchSettings() }
      if (targetIndex === undefined) project.scenes.push(scene)
      else project.scenes.splice(Math.max(0, Math.min(project.scenes.length, targetIndex)), 0, scene)
    }),
    addAudioFromAsset: (assetId, start = 0, trackId) => commit((project) => {
      const asset = project.assets[assetId]
      if (!asset || asset.kind !== 'audio') throw new Error('Only an uploaded audio file can be placed in an audio lane')
      const clip = { id: createId(), assetId, start: Math.max(0, start), sourceIn: 0, sourceOut: asset.meta.duration ?? 0, volume: 1, muted: false }
      const track = trackId ? project.audioTracks.find((item) => item.id === trackId) : undefined
      if (track) track.clips.push(clip)
      else project.audioTracks.push({ id: createId(), name: asset.name, muted: false, volume: 1, clips: [clip] })
    }),
    addImageScene: (asset) => commit((project) => {
      project.assets[asset.id] = asset
      project.scenes.push({ id: createId(), assetId: asset.id, duration: 4, sketchDuration: 4, sketchRegions:[], progressStart: 0, progressEnd: 1, sketchSettings: defaultSketchSettings() })
    }),
    addAudioTrack: (asset) => commit((project) => {
      project.assets[asset.id] = asset
      project.audioTracks.push({ id: createId(), name: asset.name, muted: false, volume: 1, clips: [{ id: createId(), assetId: asset.id, start: 0, sourceIn: 0, sourceOut: asset.meta.duration ?? 0, volume: 1, muted: false }] })
    }),
    setTrackMuted: (id, muted) => commit((project) => { const track = project.audioTracks.find((item) => item.id === id); if (!track) throw new Error(`Track not found: ${id}`); track.muted = muted }),
    setTrackVolume: (id, volume) => commit((project) => { const track = project.audioTracks.find((item) => item.id === id); if (!track) throw new Error(`Track not found: ${id}`); track.volume = Math.max(0, Math.min(2, volume)) }),
    replaceProject: (project) => set({ project: normalizeProject(clone(project)), past: [], future: [] }),
    resizeScene: (id, duration) => commit((project) => resizeScene(project, id, duration)),
    splitScene: (id, time) => { const rightId=createId();commit((project) => { splitScene(project, id, time, rightId) });return rightId },
    trimClip: (id, edge, delta) => commit((project) => {
      for (const track of project.audioTracks) { const clip = track.clips.find((item) => item.id === id); if (clip) { const duration = project.assets[clip.assetId]?.meta.duration; if (duration === undefined) throw new Error('Audio duration unavailable'); trimClip(clip, edge, delta, duration); return } }
      throw new Error(`Clip not found: ${id}`)
    }),
    moveClip: (id, trackId, start) => commit((project) => moveClip(project, id, trackId, start)),
    resizeSceneLeft: (id, delta) => commit((project) => {
      const index = project.scenes.findIndex((scene) => scene.id === id); if (index <= 0) return
      const previous = project.scenes[index - 1]; const scene = project.scenes[index]
      const applied = Math.max(0.5 - previous.duration, Math.min(scene.duration - 0.5, delta)); previous.duration += applied; scene.duration -= applied; previous.sketchDuration=Math.min(previous.sketchDuration??previous.duration,previous.duration);scene.sketchDuration=Math.min(scene.sketchDuration??scene.duration,scene.duration)
      for(const item of [previous,scene]){const total=item.sketchRegions.reduce((sum,region)=>sum+region.duration,0);if(total>item.duration){for(const region of item.sketchRegions)region.duration=region.duration/total*item.duration;item.sketchDuration=item.duration}}
    }),
    reorderScene: (id, targetIndex) => commit((project) => { const from = project.scenes.findIndex((scene) => scene.id === id); if (from < 0) return; const [scene] = project.scenes.splice(from, 1); project.scenes.splice(Math.max(0, Math.min(project.scenes.length, targetIndex)), 0, scene) }),
    duplicateScene: (id) => commit((project) => { const index = project.scenes.findIndex((scene) => scene.id === id); if (index < 0) return; const source = project.scenes[index]; project.scenes.splice(index + 1, 0, { ...source, sketchSettings: { ...source.sketchSettings }, sketchRegions:cloneRegions(source.sketchRegions), id: createId() }) }),
    deleteScene: (id) => commit((project) => { const index = project.scenes.findIndex((scene) => scene.id === id); if (index >= 0) project.scenes.splice(index, 1); project.transitions = project.transitions.filter((transition) => transition.fromSceneId !== id && transition.toSceneId !== id) }),
    deleteClip: (id) => commit((project) => { for (const track of project.audioTracks) { const index = track.clips.findIndex((clip) => clip.id === id); if (index >= 0) { track.clips.splice(index, 1); return } } }),
    splitClip: (id, time) => { const rightId=createId();commit((project) => { for (const track of project.audioTracks) { const clip = track.clips.find((item) => item.id === id); if (!clip) continue; const local = time - clip.start; const duration = clip.sourceOut - clip.sourceIn; if (local <= 0.001 || local >= duration - 0.001) throw new Error('Playhead must be inside the audio clip'); const right = { ...clip, id: rightId, start: time, sourceIn: clip.sourceIn + local, fadeIn: 0 }; clip.sourceOut = right.sourceIn; clip.fadeOut = 0; track.clips.push(right); track.clips.sort((a, b) => a.start - b.start); return } throw new Error(`Clip not found: ${id}`) });return rightId },
    setTransition: (fromId, type, duration = 0.5) => commit((project) => { const index = project.scenes.findIndex((scene) => scene.id === fromId); if (index < 0 || index >= project.scenes.length - 1) return; const to = project.scenes[index + 1]; const safeDuration = type === 'none' ? 0 : Math.min(duration, project.scenes[index].duration / 2, to.duration / 2); const existing = project.transitions.find((item) => item.fromSceneId === fromId); if (existing) { existing.toSceneId = to.id; existing.type = type; existing.duration = safeDuration } else project.transitions.push({ id: createId(), fromSceneId: fromId, toSceneId: to.id, type, duration: safeDuration }) }),
    setProjectName: (name) => commit((project) => { project.name = name.trim() || 'Untitled project' }),
    setClipMuted: (id, muted) => commit((project) => { for (const track of project.audioTracks) { const clip = track.clips.find((item) => item.id === id); if (clip) { clip.muted = muted; return } } }),
    setClipVolume: (id, volume) => commit((project) => { for (const track of project.audioTracks) { const clip = track.clips.find((item) => item.id === id); if (clip) { clip.volume = Math.max(0, Math.min(2, volume)); return } } }),
    setSceneDurationMs: (id, milliseconds) => commit((project) => resizeScene(project, id, Math.max(100, milliseconds) / 1000)),
    setSketchDurationMs: (id, milliseconds) => commit((project) => { const scene=project.scenes.find(item=>item.id===id);if(!scene)throw new Error(`Scene not found: ${id}`);const minimum=Math.max(.1,scene.sketchRegions.length*.1),target=Math.max(minimum,Math.min(scene.duration,milliseconds/1000)),total=scene.sketchRegions.reduce((sum,region)=>sum+region.duration,0);if(scene.sketchRegions.length&&total>0)for(const region of scene.sketchRegions)region.duration=region.duration/total*target;scene.sketchDuration=scene.sketchRegions.length?scene.sketchRegions.reduce((sum,region)=>sum+region.duration,0):target }),
    setSceneSketchEnabled:(id,enabled)=>commit(project=>{const scene=project.scenes.find(item=>item.id===id);if(!scene)throw new Error(`Scene not found: ${id}`);scene.sketchSettings.enabled=enabled}),
    setSceneSketchRegions:(id,regions)=>commit(project=>{const scene=project.scenes.find(item=>item.id===id);if(!scene)throw new Error(`Scene not found: ${id}`);scene.sketchRegions=cloneRegions(regions);const total=scene.sketchRegions.reduce((sum,region)=>sum+region.duration,0);if(total>scene.duration)for(const region of scene.sketchRegions)region.duration=region.duration/total*scene.duration;if(regions.length)scene.sketchDuration=scene.sketchRegions.reduce((sum,region)=>sum+region.duration,0)}),
    resizeSketchRegionBoundary:(id,boundaryIndex,delta)=>commit(project=>{const scene=project.scenes.find(item=>item.id===id);if(!scene)throw new Error(`Scene not found: ${id}`);const left=scene.sketchRegions[boundaryIndex],right=scene.sketchRegions[boundaryIndex+1];if(!left||!right)return;const applied=Math.max(.1-left.duration,Math.min(right.duration-.1,delta));left.duration+=applied;right.duration-=applied;scene.sketchDuration=scene.sketchRegions.reduce((sum,region)=>sum+region.duration,0)}),
    setSceneHand: (id, show, style) => commit((project) => { const scene=project.scenes.find(item=>item.id===id);if(scene){scene.sketchSettings.showHand=show;scene.sketchSettings.handStyle=style} }),
    setProjectBackground: (color) => commit((project) => { project.background=color }),
    setPlaybackSpeed: (speed) => commit((project) => { project.playbackSpeed=Math.max(.25,Math.min(3,speed)) }),
    newProject: () => set({ project:createEmptyProject(),past:[],future:[] }),
    setAllTransitions: (type,duration) => commit((project) => { project.transitions=[];for(let i=0;i<project.scenes.length-1;i++){const from=project.scenes[i],to=project.scenes[i+1];project.transitions.push({id:createId(),fromSceneId:from.id,toSceneId:to.id,type,duration:type==='none'?0:Math.min(duration,from.duration/2,to.duration/2)})} }),
    undo: () => set((state) => state.past.length ? { project: state.past.at(-1)!, past: state.past.slice(0, -1), future: [state.project, ...state.future] } : state),
    redo: () => set((state) => state.future.length ? { project: state.future[0], past: [...state.past, state.project], future: state.future.slice(1) } : state),
  }
})

if (import.meta.env.DEV && typeof window !== 'undefined') Object.assign(window, { __SKETCH_STORE__: useProjectStore })
