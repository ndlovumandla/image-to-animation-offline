import { produce } from 'immer'
import { create } from 'zustand'
import { createEmptyProject, defaultSketchSettings, type Asset, type Project } from '../engine/types'
import { moveClip, resizeScene, splitScene, trimClip } from '../engine/timeline'

interface ProjectState {
  project: Project; past: Project[]; future: Project[]
  addImageScene(asset: Asset): void
  addAudioTrack(asset: Asset): void; setTrackMuted(id: string, muted: boolean): void; setTrackVolume(id: string, volume: number): void
  replaceProject(project: Project): void; resizeScene(id: string, duration: number): void
  splitScene(id: string, time: number): void; trimClip(id: string, edge: 'left' | 'right', delta: number): void
  moveClip(id: string, trackId: string, start: number): void; undo(): void; redo(): void
}

const clone = (project: Project): Project => structuredClone(project)
export const useProjectStore = create<ProjectState>((set) => {
  const commit = (mutate: (draft: Project) => void) => set((state) => ({ project: produce(state.project, mutate), past: [...state.past, clone(state.project)], future: [] }))
  return {
    project: createEmptyProject(), past: [], future: [],
    addImageScene: (asset) => commit((project) => {
      project.assets[asset.id] = asset
      project.scenes.push({ id: crypto.randomUUID(), assetId: asset.id, duration: 4, progressStart: 0, progressEnd: 1, sketchSettings: defaultSketchSettings() })
    }),
    addAudioTrack: (asset) => commit((project) => {
      project.assets[asset.id] = asset
      project.audioTracks.push({ id: crypto.randomUUID(), name: asset.name, muted: false, volume: 1, clips: [{ id: crypto.randomUUID(), assetId: asset.id, start: 0, sourceIn: 0, sourceOut: asset.meta.duration ?? 0, volume: 1, muted: false }] })
    }),
    setTrackMuted: (id, muted) => commit((project) => { const track = project.audioTracks.find((item) => item.id === id); if (!track) throw new Error(`Track not found: ${id}`); track.muted = muted }),
    setTrackVolume: (id, volume) => commit((project) => { const track = project.audioTracks.find((item) => item.id === id); if (!track) throw new Error(`Track not found: ${id}`); track.volume = Math.max(0, Math.min(2, volume)) }),
    replaceProject: (project) => set({ project: clone(project), past: [], future: [] }),
    resizeScene: (id, duration) => commit((project) => resizeScene(project, id, duration)),
    splitScene: (id, time) => commit((project) => { splitScene(project, id, time) }),
    trimClip: (id, edge, delta) => commit((project) => {
      for (const track of project.audioTracks) { const clip = track.clips.find((item) => item.id === id); if (clip) { const duration = project.assets[clip.assetId]?.meta.duration; if (duration === undefined) throw new Error('Audio duration unavailable'); trimClip(clip, edge, delta, duration); return } }
      throw new Error(`Clip not found: ${id}`)
    }),
    moveClip: (id, trackId, start) => commit((project) => moveClip(project, id, trackId, start)),
    undo: () => set((state) => state.past.length ? { project: clone(state.past.at(-1)!), past: state.past.slice(0, -1), future: [clone(state.project), ...state.future] } : state),
    redo: () => set((state) => state.future.length ? { project: clone(state.future[0]), past: [...state.past, clone(state.project)], future: state.future.slice(1) } : state),
  }
})
