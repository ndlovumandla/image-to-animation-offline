import { useCallback, useEffect, useRef, useState } from 'react'
import { assetRegistry } from './engine/assetRegistry'
import { renderFrame } from './engine/renderer'
import { processSketch } from './engine/sketchProcessor'
import { projectDuration, sceneStarts } from './engine/timeline'
import type { Asset } from './engine/types'
import { useProjectStore } from './store/projectStore'

export function App() {
  const project = useProjectStore((state) => state.project)
  const addImageScene = useProjectStore((state) => state.addImageScene)
  const undo = useProjectStore((state) => state.undo)
  const redo = useProjectStore((state) => state.redo)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [time, setTime] = useState(0)
  const [processing, setProcessing] = useState<number | null>(null)
  const [error, setError] = useState('')
  const duration = projectDuration(project)

  const draw = useCallback(() => {
    const context = canvasRef.current?.getContext('2d')
    if (context) renderFrame(context, project, assetRegistry.snapshot(), time)
  }, [project, time])
  useEffect(() => { draw() }, [draw])

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
        <label className="cursor-pointer rounded-lg bg-violet-600 px-4 py-2 font-medium text-white hover:bg-violet-700">Upload image<input data-testid="image-input" className="hidden" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={(event) => void importImage(event.target.files?.[0])} /></label>
        <input aria-label="Scrub sketch" className="min-w-0 flex-1 accent-violet-600" type="range" min="0" max={Math.max(duration, 0.01)} step={1 / project.fps} value={Math.min(time, duration)} onChange={(event) => setTime(Number(event.target.value))} />
        <output className="w-24 text-right font-mono text-sm">{time.toFixed(2)} / {duration.toFixed(2)}</output>
      </div>
      {processing !== null && <div className="mt-3" role="status"><div className="mb-1 text-sm">Tracing sketch… {Math.round(processing * 100)}%</div><div className="h-2 rounded bg-gray-200"><div className="h-2 rounded bg-violet-600" style={{ width: `${processing * 100}%` }} /></div></div>}
      {error && <p role="alert" className="mt-3 rounded bg-red-50 p-3 text-red-700">{error}</p>}
    </section>
    <section className="mx-auto mt-4 max-w-6xl rounded-xl bg-white p-4 shadow-sm">
      <h2 className="font-medium">Scenes</h2>
      <div className="mt-3 flex gap-2">{project.scenes.length ? project.scenes.map((scene, index) => <button key={scene.id} className="min-w-32 rounded-lg bg-violet-50 p-3 text-left ring-1 ring-violet-200" onClick={() => setTime(sceneStarts(project.scenes)[index])}><span className="block font-medium">Scene {index + 1}</span><span className="text-sm text-gray-600">{scene.duration.toFixed(1)}s</span></button>) : <p className="text-sm text-gray-500">Drop images here to start.</p>}</div>
    </section>
  </main>
}
