import type { Point, SketchData, Stroke } from './types'

interface Request { bitmap: ImageBitmap; detail: number }

function simplify(points: Point[], tolerance = 1.5): Point[] {
  if (points.length <= 2) return points
  const first = points[0]; const last = points.at(-1)!
  let maxDistance = 0; let index = 0
  const dx = last.x - first.x; const dy = last.y - first.y; const denominator = dx * dx + dy * dy
  for (let i = 1; i < points.length - 1; i += 1) {
    const p = points[i]; const t = denominator ? Math.max(0, Math.min(1, ((p.x - first.x) * dx + (p.y - first.y) * dy) / denominator)) : 0
    const distance = Math.hypot(p.x - (first.x + t * dx), p.y - (first.y + t * dy))
    if (distance > maxDistance) { maxDistance = distance; index = i }
  }
  if (maxDistance <= tolerance) return [first, last]
  return [...simplify(points.slice(0, index + 1), tolerance).slice(0, -1), ...simplify(points.slice(index), tolerance)]
}

function strokeLength(points: Point[]): number { let length = 0; for (let i = 1; i < points.length; i += 1) length += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y); return length }

function processImage(data: ImageData, detail: number): SketchData {
  const { width, height } = data; const gray = new Float32Array(width * height); const blurred = new Float32Array(width * height)
  for (let i = 0; i < gray.length; i += 1) gray[i] = data.data[i * 4] * 0.299 + data.data[i * 4 + 1] * 0.587 + data.data[i * 4 + 2] * 0.114
  const kernel = [1, 2, 1, 2, 4, 2, 1, 2, 1]
  for (let y = 1; y < height - 1; y += 1) for (let x = 1; x < width - 1; x += 1) { let sum = 0; let k = 0; for (let yy = -1; yy <= 1; yy += 1) for (let xx = -1; xx <= 1; xx += 1) sum += gray[(y + yy) * width + x + xx] * kernel[k++]; blurred[y * width + x] = sum / 16 }
  const edges = new Uint8Array(width * height); const threshold = 150 - Math.max(0, Math.min(1, detail)) * 110
  for (let y = 1; y < height - 1; y += 1) for (let x = 1; x < width - 1; x += 1) {
    const i = y * width + x
    const gx = -blurred[i - width - 1] + blurred[i - width + 1] - 2 * blurred[i - 1] + 2 * blurred[i + 1] - blurred[i + width - 1] + blurred[i + width + 1]
    const gy = -blurred[i - width - 1] - 2 * blurred[i - width] - blurred[i - width + 1] + blurred[i + width - 1] + 2 * blurred[i + width] + blurred[i + width + 1]
    if (Math.hypot(gx, gy) >= threshold) edges[i] = 1
  }
  const visited = new Uint8Array(edges.length); const strokes: Stroke[] = []; const neighbors = [[-1,-1],[0,-1],[1,-1],[-1,0],[1,0],[-1,1],[0,1],[1,1]]
  for (let y = 1; y < height - 1; y += 1) for (let x = 1; x < width - 1; x += 1) {
    const origin = y * width + x; if (!edges[origin] || visited[origin]) continue
    const points: Point[] = []; let cx = x; let cy = y
    while (true) {
      const current = cy * width + cx; visited[current] = 1; points.push({ x: cx, y: cy })
      let next: [number, number] | undefined
      for (const [dx, dy] of neighbors) { const nx = cx + dx; const ny = cy + dy; const ni = ny * width + nx; if (edges[ni] && !visited[ni]) { next = [nx, ny]; break } }
      if (!next) break; [cx, cy] = next
    }
    if (points.length >= 5) { const clean = simplify(points); const length = strokeLength(clean); if (length >= 4) strokes.push({ points: clean, length }) }
  }
  strokes.sort((a, b) => b.length - a.length || a.points[0].y - b.points[0].y || a.points[0].x - b.points[0].x)
  return { strokes, totalLength: strokes.reduce((sum, stroke) => sum + stroke.length, 0), width, height }
}

self.onmessage = (event: MessageEvent<Request>) => {
  const { bitmap, detail } = event.data; const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height)); const width = Math.max(1, Math.round(bitmap.width * scale)); const height = Math.max(1, Math.round(bitmap.height * scale))
  const canvas = new OffscreenCanvas(width, height); const context = canvas.getContext('2d', { willReadFrequently: true })!; context.drawImage(bitmap, 0, 0, width, height); bitmap.close()
  self.postMessage(processImage(context.getImageData(0, 0, width, height), detail))
}
