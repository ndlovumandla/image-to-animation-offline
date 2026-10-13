import { useCallback, useEffect, useRef, useState } from 'react'
import { assetRegistry } from './engine/assetRegistry'
import { audioRegistry } from './engine/audioRegistry'
import { blobRegistry } from './engine/blobRegistry'
import { decodeAudio } from './engine/audioProcessor'
import { PlaybackEngine } from './engine/playbackEngine'
import { exportProject, importProject, restoreProject, saveProject } from './engine/persistence'
import { exportMp4 } from './engine/exportVideo'
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
  const replaceProject = useProjectStore((state) => state.replaceProject)
  const setProjectName = useProjectStore((state) => state.setProjectName)
  const undo = useProjectStore((state) => state.undo)
  const redo = useProjectStore((state) => state.redo)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const playbackRef = useRef(new PlaybackEngine())
  const animationRef = useRef<number | null>(null)
  const initializedRef = useRef(false)
  const exportAbortRef = useRef<AbortController | null>(null)
  const [time, setTime] = useState(0)
  const [processing, setProcessing] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [audioProcessing, setAudioProcessing] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'Loading' | 'Saving' | 'Saved' | 'Error'>('Loading')
  const [ready, setReady] = useState(false)
  const [exportHeight, setExportHeight] = useState<720 | 1080>(720)
  const [exportProgress, setExportProgress] = useState<number | null>(null)
  const [loop, setLoop] = useState(false)
  const [masterMuted, setMasterMuted] = useState(false)
  const duration = projectDuration(project)

  const draw = useCallback(() => {
    const context = canvasRef.current?.getContext('2d')
    if (context) renderFrame(context, project, assetRegistry.snapshot(), time)
  }, [project, time])
  useEffect(() => { draw() }, [draw])
  useEffect(() => () => { if (animationRef.current !== null) cancelAnimationFrame(animationRef.current); playbackRef.current.dispose() }, [])
  useEffect(() => { if (initializedRef.current) return; initializedRef.current = true; void restoreProject(playbackRef.current.audioContext).then((saved) => { if (saved) replaceProject(saved); setSaveStatus('Saved'); setReady(true) }).catch((reason) => { setError(reason instanceof Error ? reason.message : 'Unable to restore project'); setSaveStatus('Error'); setReady(true) }) }, [replaceProject])
  useEffect(() => { if (!ready) return; setSaveStatus('Saving'); const timer = window.setTimeout(() => { void saveProject(project).then(() => setSaveStatus('Saved')).catch((reason) => { setError(reason instanceof Error ? reason.message : 'Autosave failed'); setSaveStatus('Error') }) }, 400); return () => clearTimeout(timer) }, [project, ready])

  async function importImage(file?: File) {
    if (!file) return
    setError(''); setProcessing(0)
    try {
      const result = await processSketch(file, 0.5, setProcessing)
      const id = crypto.randomUUID(); blobRegistry.set(id, file)
      const asset: Asset = { id, kind: 'image', blobKey: id, name: file.name, meta: { width: result.image.width, height: result.image.height }, sketchData: result.sketchData }
      assetRegistry.set(id, result); addImageScene(asset); setTime(sceneStarts([...project.scenes, { id: 'pending', assetId: id, duration: 4, progressStart: 0, progressEnd: 1, sketchSettings: { style: 'pencil', detail: 0.5, lineWidth: 2, fillMode: 'fade', showHand: true } }]).at(-1) ?? 0)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to process image') } finally { setProcessing(null) }
  }

  async function importAudio(file?: File) {
    if (!file) return
    setError(''); setAudioProcessing(true)
    try {
      const { buffer, waveform } = await decodeAudio(file, playbackRef.current.audioContext)
      const id = crypto.randomUUID(); audioRegistry.set(id, buffer); blobRegistry.set(id, file)
      addAudioTrack({ id, kind: 'audio', blobKey: id, name: file.name, meta: { duration: buffer.duration, sampleRate: buffer.sampleRate }, waveform })
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to decode audio') } finally { setAudioProcessing(false) }
  }

  function animatePlayback() {
    const next = playbackRef.current.currentTime
    if (next >= duration) { if (loop) { setTime(0); void playbackRef.current.play(project, 0).then(() => { animationRef.current = requestAnimationFrame(animatePlayback) }); return } playbackRef.current.pause(); setPlaying(false); setTime(duration); return }
    setTime(next); animationRef.current = requestAnimationFrame(animatePlayback)
  }
  async function togglePlayback() {
    if (playing) { setTime(playbackRef.current.pause()); setPlaying(false); if (animationRef.current !== null) cancelAnimationFrame(animationRef.current); return }
    await playbackRef.current.play(project, time >= duration ? 0 : time); setPlaying(true); animationRef.current = requestAnimationFrame(animatePlayback)
  }
  async function seek(value: number) { setTime(value); await playbackRef.current.seek(project, value) }
  async function downloadProject() { try { const blob = await exportProject(project); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${project.name.replace(/[^a-z0-9_-]+/gi, '_')}.sketchproj`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Project download failed') } }
  async function openProject(file?: File) { if (!file) return; try { replaceProject(await importProject(file, playbackRef.current.audioContext)); setTime(0); setSaveStatus('Saved') } catch (reason) { setError(reason instanceof Error ? reason.message : 'Project open failed') } }
  async function exportVideo() { setError(''); const controller = new AbortController(); exportAbortRef.current = controller; setExportProgress(0); try { const blob = await exportMp4(structuredClone(project), { height: exportHeight, signal: controller.signal, onProgress: ({ progress }) => setExportProgress(progress) }); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${project.name.replace(/[^a-z0-9_-]+/gi, '_')}.mp4`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) } catch (reason) { if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(reason instanceof Error ? reason.message : 'Video export failed') } finally { exportAbortRef.current = null; setExportProgress(null) } }

  useEffect(() => { const onKey = (event: KeyboardEvent) => { if ((event.target as HTMLElement)?.matches('input, textarea, select')) return; if (event.code === 'Space') { event.preventDefault(); void togglePlayback() } }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey) })
  const timecode = (value: number) => `${Math.floor(value / 60).toString().padStart(2, '0')}:${Math.floor(value % 60).toString().padStart(2, '0')}.${Math.floor(value % 1 * project.fps).toString().padStart(2, '0')}`

  return <><div className="p-8 text-center text-gray-700 min-[1280px]:hidden"><h1 className="text-xl font-semibold">Use a larger screen</h1><p className="mt-2">Sketch Video Studio requires a window at least 1280px wide.</p></div><main className="min-h-screen p-6 max-[1279px]:hidden">
    <header className="mx-auto flex max-w-6xl items-center justify-between rounded-xl bg-white p-4 shadow-sm">
      <div><input aria-label="Project name" className="text-xl font-semibold outline-none focus:ring-2 focus:ring-violet-300" value={project.name} onChange={(event) => setProjectName(event.target.value)} /><p className="text-sm text-gray-500">Sketch Video Studio · {duration.toFixed(2)} seconds · <span data-testid="save-status">{saveStatus}</span></p></div>
      <div className="flex gap-2"><button className="rounded-lg bg-gray-100 px-3 py-2 hover:bg-gray-200" onClick={undo}>Undo</button><button className="rounded-lg bg-gray-100 px-3 py-2 hover:bg-gray-200" onClick={redo}>Redo</button><button className="rounded-lg bg-gray-100 px-3 py-2 hover:bg-gray-200" onClick={() => void downloadProject()}>Download project</button><label className="cursor-pointer rounded-lg bg-gray-100 px-3 py-2 hover:bg-gray-200">Open project<input data-testid="project-input" className="hidden" type="file" accept=".sketchproj" onChange={(event) => void openProject(event.target.files?.[0])} /></label><select aria-label="Export resolution" value={exportHeight} onChange={(event) => setExportHeight(Number(event.target.value) as 720 | 1080)} className="rounded-lg bg-gray-100 px-2"><option value="720">720p</option><option value="1080">1080p</option></select><button className="rounded-lg bg-violet-600 px-4 py-2 font-medium text-white" onClick={() => void exportVideo()}>Export MP4</button></div>
    </header>
    <section className="mx-auto mt-5 max-w-6xl rounded-xl bg-white p-5 shadow-sm">
      <div className="mx-auto aspect-video max-h-[62vh] overflow-hidden rounded-lg bg-white ring-1 ring-gray-200">
        <canvas ref={canvasRef} data-testid="preview-canvas" width={1920} height={1080} className="h-full w-full object-contain" />
      </div>
      <div className="mt-4 flex items-center gap-4">
        <button aria-label="Skip to start" className="rounded-lg bg-gray-100 px-3 py-2" onClick={() => void seek(0)}>⏮</button>
        <button className="w-20 rounded-lg bg-gray-900 px-3 py-2 text-white" onClick={() => void togglePlayback()}>{playing ? 'Pause' : 'Play'}</button>
        <button aria-label="Skip to end" className="rounded-lg bg-gray-100 px-3 py-2" onClick={() => void seek(duration)}>⏭</button>
        <output data-testid="scheduled-audio" className="sr-only">{playing ? playbackRef.current.scheduledCount : 0}</output>
        <label className="cursor-pointer rounded-lg bg-violet-600 px-4 py-2 font-medium text-white hover:bg-violet-700">Upload image<input data-testid="image-input" className="hidden" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(event) => void importImage(event.target.files?.[0])} /></label>
        <input aria-label="Scrub sketch" className="min-w-0 flex-1 accent-violet-600" type="range" min="0" max={Math.max(duration, 0.01)} step={1 / project.fps} value={Math.min(time, duration)} onChange={(event) => void seek(Number(event.target.value))} />
        <output className="w-36 text-right font-mono text-sm">{timecode(time)} / {timecode(duration)}</output>
        <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={loop} onChange={(event) => setLoop(event.target.checked)} /> Loop</label>
        <button aria-label="Master mute" aria-pressed={masterMuted} className="rounded-lg bg-gray-100 px-3 py-2" onClick={() => { const muted = !masterMuted; setMasterMuted(muted); playbackRef.current.setMasterMuted(muted) }}>{masterMuted ? '🔇' : '🔊'}</button>
      </div>
      {processing !== null && <div className="mt-3" role="status"><div className="mb-1 text-sm">Tracing sketch… {Math.round(processing * 100)}%</div><div className="h-2 rounded bg-gray-200"><div className="h-2 rounded bg-violet-600" style={{ width: `${processing * 100}%` }} /></div></div>}
      {error && <p role="alert" className="mt-3 rounded bg-red-50 p-3 text-red-700">{error}</p>}
      {exportProgress !== null && <div data-testid="export-progress" className="mt-3 rounded bg-violet-50 p-3"><div className="flex justify-between text-sm"><span>Exporting video… {Math.round(exportProgress * 100)}%</span><button onClick={() => exportAbortRef.current?.abort()}>Cancel</button></div><progress className="w-full" max="1" value={exportProgress} /></div>}
    </section>
    <div className="mx-auto mt-4 flex max-w-6xl justify-end"><label className="cursor-pointer rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white">{audioProcessing ? 'Decoding…' : '+ Add audio'}<input data-testid="audio-input" className="hidden" type="file" accept="audio/*" disabled={audioProcessing} onChange={(event) => void importAudio(event.target.files?.[0])} /></label></div>
    <Timeline playhead={time} onSeek={(value) => void seek(value)} />
  </main></>
}
