import { useCallback, useEffect, useRef, useState } from 'react'
import { assetRegistry } from './engine/assetRegistry'
import { audioRegistry } from './engine/audioRegistry'
import { decodeAudio } from './engine/audioProcessor'
import { PlaybackEngine } from './engine/playbackEngine'
import { renderFrame } from './engine/renderer'
import { processSketch } from './engine/sketchProcessor'
import { projectDuration, sceneStarts } from './engine/timeline'
import type { Asset } from './engine/types'
import { useProjectStore } from './store/projectStore'
import { Waveform } from './components/Waveform'

export function App() {
  const project = useProjectStore((state) => state.project)
  const addImageScene = useProjectStore((state) => state.addImageScene)
  const addAudioTrack = useProjectStore((state) => state.addAudioTrack)
  const setTrackMuted = useProjectStore((state) => state.setTrackMuted)
  const setTrackVolume = useProjectStore((state) => state.setTrackVolume)
  const undo = useProjectStore((state) => state.undo)
  const redo = useProjectStore((state) => state.redo)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const playbackRef = useRef(new PlaybackEngine())
  const animationRef = useRef<number | null>(null)
  const [time, setTime] = useState(0)
  const [processing, setProcessing] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [audioProcessing, setAudioProcessing] = useState(false)
  const [playing, setPlaying] = useState(false)
  const duration = projectDuration(project)

  const draw = useCallback(() => {
    const context = canvasRef.current?.getContext('2d')
    if (context) renderFrame(context, project, assetRegistry.snapshot(), time)
  }, [project, time])
  useEffect(() => { draw() }, [draw])
  useEffect(() => () => { if (animationRef.current !== null) cancelAnimationFrame(animationRef.current); playbackRef.current.dispose() }, [])

  async function importImage(file?: File) {
    if (!file) return
    setError(''); setProcessing(0)
    try {
      const result = await processSketch(file, 0.5, setProcessing)
      const id = crypto.randomUUID(); const url = URL.createObjectURL(file)
      const asset: Asset = { id, kind: 'image', blobKey: url, name: file.name, meta: { width: result.image.width, height: result.image.height }, sketchData: result.sketchData }
      assetRegistry.set(id, result); addImageScene(asset); setTime(sceneStarts([...project.scenes, { id: 'pending', assetId: id, duration: 4, progressStart: 0, progressEnd: 1, sketchSettings: { style: 'pencil', detail: 0.5, lineWidth: 2, fillMode: 'fade', showHand: true } }]).at(-1) ?? 0)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to process image') } finally { setProcessing(null) }
  }

  async function importAudio(file?: File) {
    if (!file) return
    setError(''); setAudioProcessing(true)
    try {
      const { buffer, waveform } = await decodeAudio(file, playbackRef.current.audioContext)
      const id = crypto.randomUUID(); audioRegistry.set(id, buffer)
      addAudioTrack({ id, kind: 'audio', blobKey: URL.createObjectURL(file), name: file.name, meta: { duration: buffer.duration, sampleRate: buffer.sampleRate }, waveform })
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to decode audio') } finally { setAudioProcessing(false) }
  }

  function animatePlayback() {
    const next = playbackRef.current.currentTime
    if (next >= duration) { playbackRef.current.pause(); setPlaying(false); setTime(duration); return }
    setTime(next); animationRef.current = requestAnimationFrame(animatePlayback)
  }
  async function togglePlayback() {
    if (playing) { setTime(playbackRef.current.pause()); setPlaying(false); if (animationRef.current !== null) cancelAnimationFrame(animationRef.current); return }
    await playbackRef.current.play(project, time >= duration ? 0 : time); setPlaying(true); animationRef.current = requestAnimationFrame(animatePlayback)
  }
  async function seek(value: number) { setTime(value); await playbackRef.current.seek(project, value) }

  return <main className="min-h-screen p-6">
    <header className="mx-auto flex max-w-6xl items-center justify-between rounded-xl bg-white p-4 shadow-sm">
      <div><h1 className="text-xl font-semibold">{project.name}</h1><p className="text-sm text-gray-500">Sketch engine harness · {duration.toFixed(2)} seconds</p></div>
      <div className="flex gap-2"><button className="rounded-lg bg-gray-100 px-3 py-2 hover:bg-gray-200" onClick={undo}>Undo</button><button className="rounded-lg bg-gray-100 px-3 py-2 hover:bg-gray-200" onClick={redo}>Redo</button></div>
    </header>
    <section className="mx-auto mt-5 max-w-6xl rounded-xl bg-white p-5 shadow-sm">
      <div className="mx-auto aspect-video max-h-[62vh] overflow-hidden rounded-lg bg-white ring-1 ring-gray-200">
        <canvas ref={canvasRef} data-testid="preview-canvas" width={1920} height={1080} className="h-full w-full object-contain" />
      </div>
      <div className="mt-4 flex items-center gap-4">
        <button className="w-20 rounded-lg bg-gray-900 px-3 py-2 text-white" onClick={() => void togglePlayback()}>{playing ? 'Pause' : 'Play'}</button>
        <output data-testid="scheduled-audio" className="sr-only">{playing ? playbackRef.current.scheduledCount : 0}</output>
        <label className="cursor-pointer rounded-lg bg-violet-600 px-4 py-2 font-medium text-white hover:bg-violet-700">Upload image<input data-testid="image-input" className="hidden" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(event) => void importImage(event.target.files?.[0])} /></label>
        <input aria-label="Scrub sketch" className="min-w-0 flex-1 accent-violet-600" type="range" min="0" max={Math.max(duration, 0.01)} step={1 / project.fps} value={Math.min(time, duration)} onChange={(event) => void seek(Number(event.target.value))} />
        <output className="w-24 text-right font-mono text-sm">{time.toFixed(2)} / {duration.toFixed(2)}</output>
      </div>
      {processing !== null && <div className="mt-3" role="status"><div className="mb-1 text-sm">Tracing sketch… {Math.round(processing * 100)}%</div><div className="h-2 rounded bg-gray-200"><div className="h-2 rounded bg-violet-600" style={{ width: `${processing * 100}%` }} /></div></div>}
      {error && <p role="alert" className="mt-3 rounded bg-red-50 p-3 text-red-700">{error}</p>}
    </section>
    <section className="mx-auto mt-4 max-w-6xl rounded-xl bg-white p-4 shadow-sm">
      <h2 className="font-medium">Scenes</h2>
      <div className="mt-3 flex gap-2">{project.scenes.length ? project.scenes.map((scene, index) => <button key={scene.id} className="min-w-32 rounded-lg bg-violet-50 p-3 text-left ring-1 ring-violet-200" onClick={() => setTime(sceneStarts(project.scenes)[index])}><span className="block font-medium">Scene {index + 1}</span><span className="text-sm text-gray-600">{scene.duration.toFixed(1)}s</span></button>) : <p className="text-sm text-gray-500">Drop images here to start.</p>}</div>
    </section>
    <section className="mx-auto mt-4 max-w-6xl rounded-xl bg-[#eceef2] p-4 shadow-sm">
      <div className="flex items-center justify-between"><h2 className="font-medium">Global audio tracks</h2><label className="cursor-pointer rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white">{audioProcessing ? 'Decoding…' : '+ Add audio'}<input data-testid="audio-input" className="hidden" type="file" accept="audio/*" disabled={audioProcessing} onChange={(event) => void importAudio(event.target.files?.[0])} /></label></div>
      <div className="mt-3 space-y-2">{project.audioTracks.length ? project.audioTracks.map((track) => {
        const asset = project.assets[track.clips[0]?.assetId]
        return <div key={track.id} data-testid="audio-track" className="flex h-20 items-center gap-3 rounded-lg bg-white p-2 ring-1 ring-gray-200">
          <div className="w-40 truncate text-sm font-medium">{track.name}</div>
          <button aria-label={`Mute ${track.name}`} aria-pressed={track.muted} className="rounded bg-gray-100 px-2 py-1 text-xs" onClick={() => { const muted = !track.muted; setTrackMuted(track.id, muted); playbackRef.current.setTrack(track.id, muted, track.volume) }}>{track.muted ? 'Unmute' : 'Mute'}</button>
          <input aria-label={`Volume ${track.name}`} className="w-24 accent-teal-700" type="range" min="0" max="2" step="0.05" value={track.volume} onChange={(event) => { const volume = Number(event.target.value); setTrackVolume(track.id, volume); playbackRef.current.setTrack(track.id, track.muted, volume) }} />
          <div className="h-14 min-w-0 flex-1 rounded bg-teal-50">{asset?.waveform && <Waveform levels={asset.waveform} />}</div>
        </div>
      }) : <p className="text-sm text-gray-500">Add an MP3 or WAV. Audio is independent and can span every scene.</p>}</div>
    </section>
  </main>
}
