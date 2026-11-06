import { ArrayBufferTarget, Muxer } from 'mp4-muxer'
import { renderFrame } from './renderer'
import { assetRegistry } from './assetRegistry'
import { audioRegistry } from './audioRegistry'
import { projectDuration } from './timeline'
import type { Project } from './types'

export interface ExportProgress { phase: 'video' | 'audio' | 'finalizing'; progress: number }
export interface ExportOptions { height: 720 | 1080; signal?: AbortSignal; onProgress?: (value: ExportProgress) => void }
const aborted = (signal?: AbortSignal) => { if (signal?.aborted) throw new DOMException('Export cancelled', 'AbortError') }

async function firstSupportedVideoConfig(width: number, height: number, fps: number): Promise<VideoEncoderConfig | null> {
  const bitrate = height === 1080 ? 8_000_000 : 4_000_000
  const level = height === 1080 ? '28' : '1f'
  const codecs = [`avc1.6400${level}`, `avc1.4d00${level}`, `avc1.42e0${level}`, `avc1.4200${level}`]
  const accelerations: HardwareAcceleration[] = ['prefer-hardware', 'prefer-software', 'no-preference']
  for (const codec of codecs) for (const hardwareAcceleration of accelerations) {
    const config: VideoEncoderConfig = { codec, width, height, bitrate, framerate: fps, hardwareAcceleration, avc: { format: 'avc' } }
    try { const support = await VideoEncoder.isConfigSupported(config); if (support.supported) return support.config ?? config } catch { /* try a more compatible profile */ }
  }
  return null
}

async function firstSupportedAudioConfig(): Promise<AudioEncoderConfig | null> {
  for (const bitrate of [256000, 192000, 128000, 96000]) {
    const config: AudioEncoderConfig = { codec: 'mp4a.40.2', sampleRate: 48000, numberOfChannels: 2, bitrate }
    try { const support = await AudioEncoder.isConfigSupported(config); if (support.supported) return support.config ?? config } catch { /* try a lower AAC bitrate */ }
  }
  try {
    const config: AudioEncoderConfig = { codec: 'mp4a.40.2', sampleRate: 48000, numberOfChannels: 2 }
    const support = await AudioEncoder.isConfigSupported(config)
    return support.supported ? support.config ?? config : null
  } catch { return null }
}

async function mixAudio(project: Project, duration: number, speed: number, rate = 48000): Promise<AudioBuffer> {
  const context = new OfflineAudioContext(2, Math.max(1, Math.ceil(duration * rate)), rate)
  for (const track of project.audioTracks) {
    if (track.muted || track.volume <= 0) continue
    const trackGain = context.createGain(); trackGain.gain.value = track.volume; trackGain.connect(context.destination)
    for (const clip of track.clips) {
      const buffer = audioRegistry.get(clip.assetId); if (!buffer || clip.muted || clip.volume <= 0) continue
      const source = context.createBufferSource(); source.buffer = buffer;source.playbackRate.value=speed; const gain = context.createGain(); gain.gain.value = clip.volume; source.connect(gain).connect(trackGain)
      const clipDuration = clip.sourceOut - clip.sourceIn
      const outputStart=clip.start/speed,outputDuration=clipDuration/speed
      if (clip.fadeIn) { gain.gain.setValueAtTime(0, outputStart); gain.gain.linearRampToValueAtTime(clip.volume, outputStart + Math.min(clip.fadeIn/speed, outputDuration)) }
      if (clip.fadeOut) { gain.gain.setValueAtTime(clip.volume, outputStart + Math.max(0, outputDuration - clip.fadeOut/speed)); gain.gain.linearRampToValueAtTime(0, outputStart + outputDuration) }
      source.start(outputStart, clip.sourceIn, clipDuration)
    }
  }
  return context.startRendering()
}

function readAudioChannel(buffer: AudioBuffer, index: number): Float32Array {
  const channel = Math.min(index, buffer.numberOfChannels - 1)
  if (typeof buffer.copyFromChannel === 'function') {
    const copy = new Float32Array(buffer.length)
    buffer.copyFromChannel(copy, channel)
    return copy
  }
  return new Float32Array(buffer.getChannelData(channel))
}

async function waitForEncoderQueue(encoder: { readonly encodeQueueSize: number; addEventListener?: (type: string, listener: () => void, options?: AddEventListenerOptions) => void; removeEventListener?: (type: string, listener: () => void) => void }, limit: number): Promise<void> {
  if (encoder.encodeQueueSize <= limit) return
  await new Promise<void>((resolve) => {
    if (typeof encoder.addEventListener !== 'function') { setTimeout(resolve, 0); return }
    const done = () => { clearTimeout(timer); encoder.removeEventListener?.('dequeue', done); resolve() }
    const timer = setTimeout(done, 16)
    encoder.addEventListener('dequeue', done, { once: true })
  })
}

export async function exportMp4(project: Project, options: ExportOptions): Promise<Blob> {
  if (!project.scenes.length) throw new Error('Add at least one image scene before exporting')
  for (const scene of project.scenes) if (!assetRegistry.get(scene.assetId)) throw new Error(`Scene asset is unavailable: ${project.assets[scene.assetId]?.name ?? scene.assetId}`)
  if (!('VideoEncoder' in window) || !('AudioEncoder' in window)) throw new Error('This browser does not provide the video/audio encoders needed for MP4 export. Use a current Chrome, Edge, or Safari release.')
  const speed=Math.max(.25,Math.min(3,project.playbackSpeed??1)),sourceDuration=projectDuration(project),duration=sourceDuration/speed; const fps = project.fps; const height = options.height; const width = Math.round(height * 16 / 9)
  const [videoConfig, audioConfig] = await Promise.all([firstSupportedVideoConfig(width, height, fps), firstSupportedAudioConfig()])
  if (!videoConfig || !audioConfig) throw new Error('This browser cannot create an MP4 locally because its H.264 or AAC encoder is unavailable. Try the latest Chrome, Edge, or Safari; Firefox and desktop Linux commonly omit AAC encoding.')
  const target = new ArrayBufferTarget(); const muxer = new Muxer({ target, video: { codec: 'avc', width, height }, audio: { codec: 'aac', sampleRate: 48000, numberOfChannels: 2 }, fastStart: 'in-memory', firstTimestampBehavior: 'offset' })
  const videoEncoder = new VideoEncoder({ output: (chunk, meta) => muxer.addVideoChunk(chunk, meta), error: (error) => { throw error } }); const audioEncoder = new AudioEncoder({ output: (chunk, meta) => muxer.addAudioChunk(chunk, meta), error: (error) => { throw error } })
  videoEncoder.configure(videoConfig); audioEncoder.configure(audioConfig)
  try {
    const canvas = new OffscreenCanvas(width, height); const context = canvas.getContext('2d')!; const frames = Math.ceil(duration * fps); const assets = assetRegistry.snapshot()
    for (let frameIndex = 0; frameIndex < frames; frameIndex += 1) { aborted(options.signal); renderFrame(context, project, assets, Math.min(sourceDuration,frameIndex / fps*speed)); const frame = new VideoFrame(canvas, { timestamp: Math.round(frameIndex / fps * 1_000_000), duration: Math.round(1_000_000 / fps) }); videoEncoder.encode(frame, { keyFrame: frameIndex % (fps * 2) === 0 }); frame.close(); await waitForEncoderQueue(videoEncoder, 8); options.onProgress?.({ phase: 'video', progress: frameIndex / frames * 0.8 }) }
    await videoEncoder.flush(); aborted(options.signal)
    const mixed = await mixAudio(project, duration,speed); const chunkSize = 1024
    const leftChannel = readAudioChannel(mixed, 0)
    const rightChannel = mixed.numberOfChannels > 1 ? readAudioChannel(mixed, 1) : leftChannel
    const channels = [leftChannel, rightChannel]
    for (let offset = 0; offset < mixed.length; offset += chunkSize) { aborted(options.signal); const frames = Math.min(chunkSize, mixed.length - offset); const planar = new Float32Array(frames * 2); for (let channel = 0; channel < 2; channel += 1) { const source = channels[channel]; for (let i = 0; i < frames; i += 1) planar[channel * frames + i] = Math.max(-0.98, Math.min(0.98, source[offset + i])) } const data = new AudioData({ format: 'f32-planar', sampleRate: 48000, numberOfFrames: frames, numberOfChannels: 2, timestamp: Math.round(offset / 48000 * 1_000_000), data: planar }); audioEncoder.encode(data); data.close(); await waitForEncoderQueue(audioEncoder, 16); options.onProgress?.({ phase: 'audio', progress: 0.8 + offset / mixed.length * 0.19 }) }
    await audioEncoder.flush(); options.onProgress?.({ phase: 'finalizing', progress: 0.99 }); muxer.finalize(); options.onProgress?.({ phase: 'finalizing', progress: 1 }); return new Blob([target.buffer], { type: 'video/mp4' })
  } finally { videoEncoder.close(); audioEncoder.close() }
}
