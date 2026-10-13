import { ArrayBufferTarget, Muxer } from 'mp4-muxer'
import { renderFrame } from './renderer'
import { assetRegistry } from './assetRegistry'
import { audioRegistry } from './audioRegistry'
import { projectDuration } from './timeline'
import type { Project } from './types'

export interface ExportProgress { phase: 'video' | 'audio' | 'finalizing'; progress: number }
export interface ExportOptions { height: 720 | 1080; signal?: AbortSignal; onProgress?: (value: ExportProgress) => void }
const aborted = (signal?: AbortSignal) => { if (signal?.aborted) throw new DOMException('Export cancelled', 'AbortError') }

async function mixAudio(project: Project, duration: number, rate = 48000): Promise<AudioBuffer> {
  const context = new OfflineAudioContext(2, Math.max(1, Math.ceil(duration * rate)), rate)
  for (const track of project.audioTracks) {
    if (track.muted || track.volume <= 0) continue
    const trackGain = context.createGain(); trackGain.gain.value = track.volume; trackGain.connect(context.destination)
    for (const clip of track.clips) {
      const buffer = audioRegistry.get(clip.assetId); if (!buffer || clip.muted || clip.volume <= 0) continue
      const source = context.createBufferSource(); source.buffer = buffer; const gain = context.createGain(); gain.gain.value = clip.volume; source.connect(gain).connect(trackGain)
      const clipDuration = clip.sourceOut - clip.sourceIn
      if (clip.fadeIn) { gain.gain.setValueAtTime(0, clip.start); gain.gain.linearRampToValueAtTime(clip.volume, clip.start + Math.min(clip.fadeIn, clipDuration)) }
      if (clip.fadeOut) { gain.gain.setValueAtTime(clip.volume, clip.start + Math.max(0, clipDuration - clip.fadeOut)); gain.gain.linearRampToValueAtTime(0, clip.start + clipDuration) }
      source.start(clip.start, clip.sourceIn, clipDuration)
    }
  }
  return context.startRendering()
}

export async function exportMp4(project: Project, options: ExportOptions): Promise<Blob> {
  if (!project.scenes.length) throw new Error('Add at least one image scene before exporting')
  for (const scene of project.scenes) if (!assetRegistry.get(scene.assetId)) throw new Error(`Scene asset is unavailable: ${project.assets[scene.assetId]?.name ?? scene.assetId}`)
  if (!('VideoEncoder' in window) || !('AudioEncoder' in window)) throw new Error('MP4 export requires current Chrome or Edge with WebCodecs video and audio support')
  const duration = projectDuration(project); const fps = project.fps; const height = options.height; const width = Math.round(height * 16 / 9)
  const videoConfig: VideoEncoderConfig = { codec: 'avc1.640028', width, height, bitrate: height === 1080 ? 8_000_000 : 4_000_000, framerate: fps, avc: { format: 'avc' } }
  const audioConfig: AudioEncoderConfig = { codec: 'mp4a.40.2', sampleRate: 48000, numberOfChannels: 2, bitrate: 192000 }
  const [videoSupport, audioSupport] = await Promise.all([VideoEncoder.isConfigSupported(videoConfig), AudioEncoder.isConfigSupported(audioConfig)])
  if (!videoSupport.supported || !audioSupport.supported) throw new Error('This browser cannot encode H.264/AAC with the required settings')
  const target = new ArrayBufferTarget(); const muxer = new Muxer({ target, video: { codec: 'avc', width, height }, audio: { codec: 'aac', sampleRate: 48000, numberOfChannels: 2 }, fastStart: 'in-memory', firstTimestampBehavior: 'offset' })
  const videoEncoder = new VideoEncoder({ output: (chunk, meta) => muxer.addVideoChunk(chunk, meta), error: (error) => { throw error } }); const audioEncoder = new AudioEncoder({ output: (chunk, meta) => muxer.addAudioChunk(chunk, meta), error: (error) => { throw error } })
  videoEncoder.configure(videoConfig); audioEncoder.configure(audioConfig)
  try {
    const canvas = new OffscreenCanvas(width, height); const context = canvas.getContext('2d')!; const frames = Math.ceil(duration * fps); const assets = assetRegistry.snapshot()
    for (let frameIndex = 0; frameIndex < frames; frameIndex += 1) { aborted(options.signal); renderFrame(context, project, assets, frameIndex / fps); const frame = new VideoFrame(canvas, { timestamp: Math.round(frameIndex / fps * 1_000_000), duration: Math.round(1_000_000 / fps) }); videoEncoder.encode(frame, { keyFrame: frameIndex % (fps * 2) === 0 }); frame.close(); if (videoEncoder.encodeQueueSize > 5) await videoEncoder.flush(); options.onProgress?.({ phase: 'video', progress: frameIndex / frames * 0.8 }) }
    await videoEncoder.flush(); aborted(options.signal)
    const mixed = await mixAudio(project, duration); let peak = 0; for (let channel = 0; channel < mixed.numberOfChannels; channel += 1) for (const sample of mixed.getChannelData(channel)) peak = Math.max(peak, Math.abs(sample)); const scale = peak > 0.98 ? 0.98 / peak : 1; const chunkSize = 1024
    for (let offset = 0; offset < mixed.length; offset += chunkSize) { aborted(options.signal); const frames = Math.min(chunkSize, mixed.length - offset); const planar = new Float32Array(frames * 2); for (let channel = 0; channel < 2; channel += 1) { const source = mixed.getChannelData(Math.min(channel, mixed.numberOfChannels - 1)); for (let i = 0; i < frames; i += 1) planar[channel * frames + i] = source[offset + i] * scale } const data = new AudioData({ format: 'f32-planar', sampleRate: 48000, numberOfFrames: frames, numberOfChannels: 2, timestamp: Math.round(offset / 48000 * 1_000_000), data: planar }); audioEncoder.encode(data); data.close(); if (audioEncoder.encodeQueueSize > 10) await audioEncoder.flush(); options.onProgress?.({ phase: 'audio', progress: 0.8 + offset / mixed.length * 0.19 }) }
    await audioEncoder.flush(); options.onProgress?.({ phase: 'finalizing', progress: 0.99 }); muxer.finalize(); options.onProgress?.({ phase: 'finalizing', progress: 1 }); return new Blob([target.buffer], { type: 'video/mp4' })
  } finally { videoEncoder.close(); audioEncoder.close() }
}
