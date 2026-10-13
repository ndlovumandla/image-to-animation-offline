import type { SketchData } from './types'

export async function processSketch(file: Blob, detail: number, onProgress?: (progress: number) => void): Promise<{ image: ImageBitmap; sketchData: SketchData }> {
  onProgress?.(0.05)
  const source = await createImageBitmap(file)
  const renderImage = await createImageBitmap(file)
  const worker = new Worker(new URL('./sketchWorker.ts', import.meta.url), { type: 'module' })
  try {
    const sketchData = await new Promise<SketchData>((resolve, reject) => {
      worker.onmessage = (event: MessageEvent<SketchData>) => resolve(event.data)
      worker.onerror = (event) => reject(new Error(event.message || 'Sketch worker failed'))
      worker.postMessage({ bitmap: source, detail }, [source])
    })
    onProgress?.(1); return { image: renderImage, sketchData }
  } catch (error) { renderImage.close(); throw error } finally { worker.terminate() }
}
