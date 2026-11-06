import { createId } from './id'

export type Id = string
export type FillMode = 'fade' | 'brush' | 'none'
export type SketchStyle = 'pencil' | 'ink' | 'marker'
export type TransitionType = 'none' | 'fade' | 'dissolve' | 'slide' | 'push' | 'wipe' | 'zoom' | 'blur'

export interface Point { x: number; y: number }
export interface Stroke { points: Point[]; length: number }
export interface SketchData { strokes: Stroke[]; totalLength: number; width: number; height: number }
export interface WaveformLevel { bucketSize: number; min: number[]; max: number[] }
export interface RegionBrushStroke { points: Point[]; radius: number }
export interface SketchRegion { id: Id; name: string; duration: number; color: string; strokes: RegionBrushStroke[] }

export interface SketchSettings {
  enabled: boolean; style: SketchStyle; detail: number; lineWidth: number; fillMode: FillMode; showHand: boolean; handStyle?: 'classic' | 'left' | 'marker'
}
export interface Scene {
  id: Id; assetId: Id; duration: number; sketchDuration: number; sketchRegions: SketchRegion[]; progressStart: number; progressEnd: number; sketchSettings: SketchSettings
}
export interface Transition { id: Id; fromSceneId: Id; toSceneId: Id; type: TransitionType; duration: number }
export interface AudioClip {
  id: Id; assetId: Id; start: number; sourceIn: number; sourceOut: number; volume: number; muted: boolean; fadeIn?: number; fadeOut?: number
}
export interface AudioTrack { id: Id; name: string; muted: boolean; volume: number; clips: AudioClip[] }
export interface Asset {
  id: Id; kind: 'image' | 'audio'; blobKey: string; name: string;
  meta: { width?: number; height?: number; duration?: number; sampleRate?: number }; sketchData?: SketchData; waveform?: WaveformLevel[]
}
export interface Project {
  id: Id; name: string; fps: number; width: number; height: number; background: string; playbackSpeed: number;
  scenes: Scene[]; transitions: Transition[]; audioTracks: AudioTrack[]; assets: Record<Id, Asset>
}

export const defaultSketchSettings = (): SketchSettings => ({ enabled: true, style: 'pencil', detail: 0.5, lineWidth: 2, fillMode: 'fade', showHand: true, handStyle: 'classic' })
export const createEmptyProject = (): Project => ({ id: createId(), name: 'Untitled project', fps: 30, width: 1920, height: 1080, background: '#fff', playbackSpeed: 1, scenes: [], transitions: [], audioTracks: [], assets: {} })

/** Upgrades older saved projects without changing their previous playback speed. */
export function normalizeProject(project: Project): Project {
  const speed=Number(project.playbackSpeed)
  project.playbackSpeed=Number.isFinite(speed)?Math.max(.25,Math.min(3,speed)):1
  for (const scene of project.scenes) {
    if(typeof scene.sketchSettings.enabled!=='boolean')scene.sketchSettings.enabled=true
    if(!Array.isArray(scene.sketchRegions))scene.sketchRegions=[]
    const stored = Number(scene.sketchDuration)
    scene.sketchDuration = Number.isFinite(stored) ? Math.max(.1, Math.min(scene.duration, stored)) : scene.duration
  }
  return project
}
