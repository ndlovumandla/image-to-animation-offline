import { projectDuration } from './timeline'
import type { Project } from './types'
import { audioRegistry } from './audioRegistry'

interface Scheduled { source: AudioBufferSourceNode; clipGain: GainNode; trackId: string; clipId: string }

export class PlaybackEngine {
  private context?: AudioContext
  private scheduled: Scheduled[] = []
  private trackGains = new Map<string, GainNode>()
  private master?: GainNode
  private origin = 0
  private fallbackOrigin = 0
  private startPosition = 0
  private speed = 1
  playing = false
  get scheduledCount(): number { return this.scheduled.length }

  private ensureContext(): AudioContext { this.context ??= new AudioContext(); return this.context }
  get audioContext(): AudioContext { return this.ensureContext() }
  get currentTime(): number {
    if (!this.playing) return this.startPosition
    const elapsed=this.context?this.context.currentTime-this.origin:(performance.now()-this.fallbackOrigin)/1000
    return Math.max(0,this.startPosition+elapsed*this.speed)
  }
  async play(project: Project, from = this.startPosition): Promise<void> {
    this.stopNodes(); const context = this.ensureContext(); await context.resume(); this.startPosition = Math.max(0, Math.min(from, projectDuration(project))); this.speed=Math.max(.25,Math.min(3,project.playbackSpeed??1));this.origin = context.currentTime; this.fallbackOrigin = performance.now(); this.master = context.createGain(); this.master.connect(context.destination); this.playing = true
    for (const track of project.audioTracks) {
      const trackGain = context.createGain(); trackGain.gain.value = track.muted ? 0 : track.volume; trackGain.connect(this.master); this.trackGains.set(track.id, trackGain)
      for (const clip of track.clips) {
        const buffer = audioRegistry.get(clip.assetId); if (!buffer || clip.muted || clip.volume <= 0 || clip.start + clip.sourceOut - clip.sourceIn <= this.startPosition) continue
        const source = context.createBufferSource(); source.buffer = buffer;source.playbackRate.value=this.speed; const clipGain = context.createGain(); clipGain.gain.value = clip.volume; source.connect(clipGain).connect(trackGain)
        const late = Math.max(0, this.startPosition - clip.start); const when = context.currentTime+Math.max(0,(clip.start-this.startPosition)/this.speed); const offset = clip.sourceIn + late; const duration = Math.max(0, clip.sourceOut - offset)
        if (duration > 0) { source.start(when, offset, duration); this.scheduled.push({ source, clipGain, trackId: track.id, clipId: clip.id }) }
      }
    }
  }
  pause(): number { this.startPosition = this.currentTime; this.playing = false; this.stopNodes(); return this.startPosition }
  async seek(project: Project, time: number): Promise<void> { const wasPlaying = this.playing; this.startPosition = Math.max(0, Math.min(time, projectDuration(project))); if (wasPlaying) await this.play(project, this.startPosition) }
  setTrack(trackId: string, muted: boolean, volume: number): void { const gain = this.trackGains.get(trackId); if (gain && this.context) gain.gain.setValueAtTime(muted ? 0 : volume, this.context.currentTime) }
  setClip(clipId: string, muted: boolean, volume: number): void { for (const item of this.scheduled) if (item.clipId === clipId && this.context) item.clipGain.gain.setValueAtTime(muted ? 0 : volume, this.context.currentTime) }
  setMasterMuted(muted: boolean): void { if (this.master && this.context) this.master.gain.setValueAtTime(muted ? 0 : 1, this.context.currentTime) }
  dispose(): void { this.pause(); void this.context?.close(); this.context = undefined }
  private stopNodes(): void { for (const item of this.scheduled) { try { item.source.stop() } catch { /* already stopped */ } item.source.disconnect(); item.clipGain.disconnect() } this.scheduled = []; for (const gain of this.trackGains.values()) gain.disconnect(); this.trackGains.clear(); this.master?.disconnect(); this.master = undefined }
}
