import { useEffect, useRef } from 'react'
import type { WaveformLevel } from '../engine/types'

export function Waveform({ levels }: { levels: WaveformLevel[] }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current; if (!canvas) return
    const draw = () => {
      const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2),width=Math.max(1,Math.round(rect.width*dpr)),height=Math.max(1,Math.round(rect.height*dpr))
      if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height}
      const context=canvas.getContext('2d');if(!context)return;context.clearRect(0,0,width,height)
      const level=[...levels].sort((a,b)=>a.min.length-b.min.length).find(item=>item.min.length>=width)??levels.at(-1);if(!level)return
      const middle=height/2,gradient=context.createLinearGradient(0,0,0,height);gradient.addColorStop(0,'#0f766e');gradient.addColorStop(.5,'#14b8a6');gradient.addColorStop(1,'#0f766e');context.fillStyle=gradient
      context.strokeStyle='rgba(15,118,110,.4)';context.lineWidth=1;context.beginPath();context.moveTo(0,Math.round(middle)+.5);context.lineTo(width,Math.round(middle)+.5);context.stroke()
      for(let x=0;x<width;x++){const index=Math.min(level.min.length-1,Math.floor(x/width*level.min.length));const peak=Math.max(Math.abs(level.max[index]),Math.abs(level.min[index]));const amplified=Math.min(1,Math.pow(peak,0.72)*1.35);const half=Math.max(1,amplified*(middle-2));context.fillRect(x,middle-half,Math.max(1,dpr),half*2)}
    }
    draw();const observer=new ResizeObserver(draw);observer.observe(canvas);return()=>observer.disconnect()
  }, [levels])
  return <canvas ref={ref} data-testid="waveform" className="h-full w-full" />
}
