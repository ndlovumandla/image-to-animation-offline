import type { AudioClip, Project, Scene } from './types'

export const MIN_SCENE_DURATION = 0.5
export const MIN_CLIP_DURATION = 1 / 1000
const clamp = (value: number, low: number, high = Number.POSITIVE_INFINITY) => Math.min(high, Math.max(low, value))

export function sceneStarts(scenes: readonly Scene[]): number[] {
  const starts: number[] = []; let cursor = 0
  for (const scene of scenes) { starts.push(cursor); cursor += scene.duration }
  return starts
}
export function sceneEnd(project: Project): number { return project.scenes.reduce((sum, scene) => sum + scene.duration, 0) }
export function projectDuration(project: Project): number {
  const audioEnd = Math.max(0, ...project.audioTracks.flatMap((track) => track.clips.map((clip) => clip.start + clip.sourceOut - clip.sourceIn)))
  return Math.max(sceneEnd(project), audioEnd)
}
export function resizeScene(project: Project, sceneId: string, duration: number): void {
  const scene = project.scenes.find((item) => item.id === sceneId)
  if (!scene) throw new Error(`Scene not found: ${sceneId}`)
  scene.duration = Math.max(MIN_SCENE_DURATION, duration)
}
export function splitScene(project: Project, sceneId: string, timelineTime: number, newId: string = crypto.randomUUID()): Scene {
  const index = project.scenes.findIndex((item) => item.id === sceneId)
  if (index < 0) throw new Error(`Scene not found: ${sceneId}`)
  const scene = project.scenes[index]
  const start = sceneStarts(project.scenes)[index]
  const leftDuration = timelineTime - start
  const rightDuration = scene.duration - leftDuration
  if (leftDuration < MIN_SCENE_DURATION || rightDuration < MIN_SCENE_DURATION) throw new Error('Split must leave at least 0.5 seconds on each side')
  const span = scene.progressEnd - scene.progressStart
  const splitProgress = scene.progressStart + span * (leftDuration / scene.duration)
  const right: Scene = { ...scene, id: newId, duration: rightDuration, progressStart: splitProgress }
  scene.duration = leftDuration; scene.progressEnd = splitProgress
  project.scenes.splice(index + 1, 0, right)
  for (const transition of project.transitions) if (transition.fromSceneId === sceneId) transition.fromSceneId = right.id
  return right
}
export function trimClip(clip: AudioClip, edge: 'left' | 'right', deltaSec: number, assetDuration: number): void {
  if (edge === 'left') {
    const next = clamp(clip.sourceIn + deltaSec, 0, clip.sourceOut - MIN_CLIP_DURATION)
    clip.start = Math.max(0, clip.start + next - clip.sourceIn); clip.sourceIn = next
  } else clip.sourceOut = clamp(clip.sourceOut + deltaSec, clip.sourceIn + MIN_CLIP_DURATION, assetDuration)
}
export function clipsOverlap(a: AudioClip, b: AudioClip): boolean {
  return a.start < b.start + b.sourceOut - b.sourceIn && b.start < a.start + a.sourceOut - a.sourceIn
}
export function nonOverlappingStart(clips: readonly AudioClip[], moving: AudioClip, requestedStart: number): number {
  let candidate = Math.max(0, requestedStart)
  const others = clips.filter((clip) => clip.id !== moving.id).sort((a, b) => a.start - b.start)
  for (const other of others) {
    const probe = { ...moving, start: candidate }
    if (clipsOverlap(probe, other)) candidate = other.start + other.sourceOut - other.sourceIn
  }
  return candidate
}
export function moveClip(project: Project, clipId: string, targetTrackId: string, requestedStart: number): void {
  const sourceTrack = project.audioTracks.find((track) => track.clips.some((clip) => clip.id === clipId))
  const targetTrack = project.audioTracks.find((track) => track.id === targetTrackId)
  const clip = sourceTrack?.clips.find((item) => item.id === clipId)
  if (!sourceTrack || !targetTrack || !clip) throw new Error('Audio clip or track not found')
  sourceTrack.clips.splice(sourceTrack.clips.indexOf(clip), 1)
  clip.start = nonOverlappingStart(targetTrack.clips, clip, requestedStart)
  targetTrack.clips.push(clip); targetTrack.clips.sort((a, b) => a.start - b.start)
}
