import { useEffect, useRef } from 'react'
import type { WaveformLevel } from '../engine/types'

export function Waveform({ levels }: { levels: WaveformLevel[] }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current; const context = canvas?.getContext('2d'); if (!canvas || !context) return
    context.clearRect(0, 0, canvas.width, canvas.height); const level = levels.find((item) => item.min.length >= canvas.width) ?? levels[0]; if (!level) return
    context.fillStyle = '#0f766e'; const middle = canvas.height / 2
    for (let x = 0; x < canvas.width; x += 1) { const index = Math.min(level.min.length - 1, Math.floor(x / canvas.width * level.min.length)); const top = middle - level.max[index] * middle; const bottom = middle - level.min[index] * middle; context.fillRect(x, top, 1, Math.max(1, bottom - top)) }
  }, [levels])
  return <canvas ref={ref} data-testid="waveform" width={800} height={72} className="h-full w-full" />
}
