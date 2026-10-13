export type Id = string
export type FillMode = 'fade' | 'brush' | 'none'
export type SketchStyle = 'pencil' | 'ink' | 'marker'
export type TransitionType = 'none' | 'fade' | 'slide' | 'wipe'

export interface Point { x: number; y: number }
export interface Stroke { points: Point[]; length: number }
export interface SketchData { strokes: Stroke[]; totalLength: number; width: number; height: number }

export interface SketchSettings {
  style: SketchStyle; detail: number; lineWidth: number; fillMode: FillMode; showHand: boolean
}
export interface Scene {
  id: Id; assetId: Id; duration: number; progressStart: number; progressEnd: number; sketchSettings: SketchSettings
}
export interface Transition { id: Id; fromSceneId: Id; toSceneId: Id; type: TransitionType; duration: number }
export interface AudioClip {
  id: Id; assetId: Id; start: number; sourceIn: number; sourceOut: number; volume: number; muted: boolean; fadeIn?: number; fadeOut?: number
}
export interface AudioTrack { id: Id; name: string; muted: boolean; volume: number; clips: AudioClip[] }
export interface Asset {
  id: Id; kind: 'image' | 'audio'; blobKey: string; name: string;
  meta: { width?: number; height?: number; duration?: number; sampleRate?: number }; sketchData?: SketchData
}
export interface Project {
  id: Id; name: string; fps: number; width: number; height: number; background: string;
  scenes: Scene[]; transitions: Transition[]; audioTracks: AudioTrack[]; assets: Record<Id, Asset>
}

export const defaultSketchSettings = (): SketchSettings => ({ style: 'pencil', detail: 0.5, lineWidth: 2, fillMode: 'fade', showHand: true })
export const createEmptyProject = (): Project => ({ id: crypto.randomUUID(), name: 'Untitled project', fps: 30, width: 1920, height: 1080, background: '#fff', scenes: [], transitions: [], audioTracks: [], assets: {} })
