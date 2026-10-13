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
import { Timeline } from './components/Timeline'

export function App() {
  const project = useProjectStore((state) => state.project)
  const addImageScene = useProjectStore((state) => state.addImageScene)
  const addAudioTrack = useProjectStore((state) => state.addAudioTrack)
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
    <div className="mx-auto mt-4 flex max-w-6xl justify-end"><label className="cursor-pointer rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white">{audioProcessing ? 'Decoding…' : '+ Add audio'}<input data-testid="audio-input" className="hidden" type="file" accept="audio/*" disabled={audioProcessing} onChange={(event) => void importAudio(event.target.files?.[0])} /></label></div>
    <Timeline playhead={time} onSeek={(value) => void seek(value)} />
  </main>
}
