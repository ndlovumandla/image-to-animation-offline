import { useEffect, useMemo, useRef, useState } from 'react'
import { projectDuration, sceneStarts } from '../engine/timeline'
import { timeToPx, pxToTime } from '../engine/timeScale'
import { useProjectStore } from '../store/projectStore'
import { Waveform } from './Waveform'
import type { TransitionType } from '../engine/types'
import { AssetThumbnail } from './AssetThumbnail'

interface Props { playhead: number; onSeek(time: number): void }
type Selection = { kind: 'scene' | 'clip'; id: string } | null
const HEADER_WIDTH = 176

export function Timeline({ playhead, onSeek }: Props) {
  const project = useProjectStore((state) => state.project)
  const actions = useMemo(() => useProjectStore.getState(), [])
  const [pxPerSecond, setPxPerSecond] = useState(80)
  const [selection, setSelection] = useState<Selection>(null)
  const [snapGuide, setSnapGuide] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const starts = sceneStarts(project.scenes); const duration = Math.max(1, projectDuration(project)); const contentWidth = Math.max(900, HEADER_WIDTH + timeToPx(duration, pxPerSecond) + 160)
  const snapPoints = useMemo(() => [playhead, ...starts, ...project.scenes.map((scene, index) => starts[index] + scene.duration), ...project.audioTracks.flatMap((track) => track.clips.flatMap((clip) => [clip.start, clip.start + clip.sourceOut - clip.sourceIn]))], [playhead, starts, project.scenes, project.audioTracks])
  const snap = (time: number, altKey: boolean) => { if (altKey) return time; const candidates = [...snapPoints, Math.round(time)]; const nearest = candidates.reduce((best, point) => Math.abs(point - time) < Math.abs(best - time) ? point : best, candidates[0] ?? time); return Math.abs(nearest - time) * pxPerSecond <= 8 ? nearest : time }

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); event.shiftKey ? actions.redo() : actions.undo(); return }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd' && selection?.kind === 'scene') { event.preventDefault(); actions.duplicateScene(selection.id); return }
      if (event.key === 'Delete' && selection) { selection.kind === 'scene' ? actions.deleteScene(selection.id) : actions.deleteClip(selection.id); setSelection(null); return }
      if (event.key.toLowerCase() === 's' && selection) { selection.kind === 'scene' ? actions.splitScene(selection.id, playhead) : actions.splitClip(selection.id, playhead); return }
      if (event.key === '+' || event.key === '=') setPxPerSecond((value) => Math.min(400, value * 1.25))
      if (event.key === '-') setPxPerSecond((value) => Math.max(10, value / 1.25))
      if (selection?.kind === 'clip' && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) { const track = project.audioTracks.find((item) => item.clips.some((clip) => clip.id === selection.id)); const clip = track?.clips.find((item) => item.id === selection.id); if (track && clip) actions.moveClip(clip.id, track.id, clip.start + (event.key === 'ArrowRight' ? 1 : -1) / project.fps) }
    }
    window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler)
  }, [actions, playhead, project, selection])

  const beginHorizontalDrag = (event: React.PointerEvent, onCommit: (deltaSec: number, altKey: boolean) => void) => {
    event.preventDefault(); event.stopPropagation(); const origin = event.clientX; const draggableParent = (event.currentTarget as HTMLElement).closest('[draggable="true"]'); draggableParent?.setAttribute('draggable', 'false')
    const move = (moveEvent: PointerEvent) => { const raw = (moveEvent.clientX - origin) / pxPerSecond; const snapped = snap(raw, moveEvent.altKey); setSnapGuide(snapped !== raw ? snapped : null) }
    const up = (upEvent: PointerEvent) => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); draggableParent?.setAttribute('draggable', 'true'); setSnapGuide(null); onCommit((upEvent.clientX - origin) / pxPerSecond, upEvent.altKey) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up, { once: true })
  }
  const tickStep = pxPerSecond >= 160 ? 0.5 : pxPerSecond >= 60 ? 1 : pxPerSecond >= 25 ? 5 : 10
  const ticks = Array.from({ length: Math.ceil(duration / tickStep) + 1 }, (_, index) => index * tickStep)
  useEffect(() => { const viewport = scrollRef.current; if (!viewport) return; const x = HEADER_WIDTH + timeToPx(playhead, pxPerSecond); if (x > viewport.scrollLeft + viewport.clientWidth - 80) viewport.scrollTo({ left: x - viewport.clientWidth + 120, behavior: 'smooth' }) }, [playhead, pxPerSecond])
  const selectedClip = selection?.kind === 'clip' ? project.audioTracks.flatMap((track) => track.clips).find((clip) => clip.id === selection.id) : undefined

  return <section className="flex h-full min-h-0 flex-col overflow-hidden bg-[#e7e9ee]" data-testid="timeline">
    <div className="flex h-10 shrink-0 items-center justify-between border-b border-gray-300 bg-white px-3">
      <div className="flex gap-2">
        <button onClick={() => { if (selection) selection.kind === 'scene' ? actions.splitScene(selection.id, playhead) : actions.splitClip(selection.id, playhead) }} className="rounded bg-gray-100 px-3 py-1 text-sm">Split</button>
        <button onClick={() => selection?.kind === 'scene' && actions.duplicateScene(selection.id)} className="rounded bg-gray-100 px-3 py-1 text-sm">Duplicate</button>
        <button onClick={() => { if (selection) selection.kind === 'scene' ? actions.deleteScene(selection.id) : actions.deleteClip(selection.id) }} className="rounded bg-gray-100 px-3 py-1 text-sm">Delete</button>
        {selectedClip && <><button aria-label="Mute selected clip" aria-pressed={selectedClip.muted} onClick={() => actions.setClipMuted(selectedClip.id, !selectedClip.muted)} className="rounded bg-gray-100 px-3 py-1 text-sm">{selectedClip.muted ? 'Unmute clip' : 'Mute clip'}</button><label className="flex items-center gap-1 text-xs">Clip volume<input aria-label="Selected clip volume" type="range" min="0" max="2" step="0.05" value={selectedClip.volume} onChange={(event) => actions.setClipVolume(selectedClip.id, Number(event.target.value))} /></label></>}
      </div>
      <label className="flex items-center gap-2 text-sm">Zoom <input aria-label="Timeline zoom" type="range" min="10" max="400" value={pxPerSecond} onChange={(event) => setPxPerSecond(Number(event.target.value))} /></label>
    </div>
    <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
      <div className="relative" style={{ width: contentWidth }}>
        <div data-testid="ruler" className="relative h-8 cursor-crosshair border-b border-gray-300 bg-[#f6f7f9]" onPointerDown={(event) => { const rect = event.currentTarget.getBoundingClientRect(); onSeek(pxToTime(event.clientX - rect.left - HEADER_WIDTH, pxPerSecond)) }}>
          {ticks.map((tick) => <div key={tick} className="absolute bottom-0 h-3 border-l border-gray-400 text-[10px] text-gray-600" style={{ left: HEADER_WIDTH + timeToPx(tick, pxPerSecond) }}><span className="absolute -top-4 left-1">{tick}s</span></div>)}
        </div>
        <div className="relative flex h-20 items-stretch border-b border-gray-300 bg-white" data-testid="scene-lane">
          <div className="sticky left-0 z-20 w-44 shrink-0 border-r border-gray-300 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-600">Video</div>
          {project.scenes.map((scene, index) => <div key={scene.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const id = event.dataTransfer.getData('scene'); if (id) actions.reorderScene(id, index) }} onClick={() => setSelection({ kind: 'scene', id: scene.id })} data-testid="scene-block" className={`relative shrink-0 overflow-hidden rounded-lg border-2 bg-violet-100 ${selection?.id === scene.id ? 'border-violet-600' : 'border-white'}`} style={{ width: timeToPx(scene.duration, pxPerSecond) }}>
            {index > 0 && <div data-testid="scene-left-handle" className="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize bg-violet-400/40" onPointerDown={(event) => beginHorizontalDrag(event, (delta) => actions.resizeSceneLeft(scene.id, delta))} />}
            <div draggable data-testid="scene-drag" onDragStart={(event) => event.dataTransfer.setData('scene', scene.id)} className="relative h-full cursor-grab"><AssetThumbnail assetId={scene.assetId} /><span className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] text-white">{scene.duration.toFixed(1)}s</span><span className="absolute left-1 top-1 rounded bg-black/55 px-1 text-[10px] text-white">{index + 1}</span></div>
            <div data-testid="scene-right-handle" className="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize bg-violet-500/50" onPointerDown={(event) => beginHorizontalDrag(event, (delta, alt) => { const targetEnd = snap(starts[index] + scene.duration + delta, alt); actions.resizeScene(scene.id, targetEnd - starts[index]) })} />
          </div>)}
          {project.scenes.slice(0, -1).map((scene, index) => { const transition = project.transitions.find((item) => item.fromSceneId === scene.id); const types: TransitionType[] = ['none', 'fade', 'slide', 'wipe']; const current = transition?.type ?? 'none'; return <button key={`transition-${scene.id}`} data-testid="transition-marker" title={`Transition: ${current}`} className="absolute -top-4 z-30 h-8 min-w-8 -translate-x-1/2 rounded-full border border-violet-400 bg-white px-1 text-[10px] uppercase shadow" style={{ left: HEADER_WIDTH + timeToPx(starts[index] + scene.duration, pxPerSecond) }} onClick={(event) => { event.stopPropagation(); actions.setTransition(scene.id, types[(types.indexOf(current) + 1) % types.length]) }}>{current === 'none' ? '+' : current}</button> })}
        </div>
        {project.audioTracks.map((track) => <div key={track.id} data-testid="timeline-audio-lane" className="relative h-20 border-b border-gray-300 bg-[#f1f3f5]" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const id = event.dataTransfer.getData('clip'); const rect = event.currentTarget.getBoundingClientRect(); if (id) actions.moveClip(id, track.id, snap(pxToTime(event.clientX - rect.left - HEADER_WIDTH, pxPerSecond), event.altKey)) }}>
          <div className="sticky left-0 z-20 flex h-full w-44 items-center gap-2 border-r border-gray-300 bg-white/95 px-2 text-xs"><span className="max-w-16 truncate">{track.name}</span><button aria-label={`Timeline mute ${track.name}`} onClick={() => actions.setTrackMuted(track.id, !track.muted)}>{track.muted ? '🔇' : '🔊'}</button><input aria-label={`Timeline volume ${track.name}`} className="w-16" type="range" min="0" max="2" step="0.05" value={track.volume} onChange={(event) => actions.setTrackVolume(track.id, Number(event.target.value))} /></div>
          {track.clips.map((clip) => { const asset = project.assets[clip.assetId]; return <div key={clip.id} onClick={() => setSelection({ kind: 'clip', id: clip.id })} data-testid="audio-clip" className={`absolute top-2 h-16 overflow-hidden rounded-lg border-2 bg-teal-100 ${selection?.id === clip.id ? 'border-teal-700' : 'border-teal-300'}`} style={{ left: HEADER_WIDTH + timeToPx(clip.start, pxPerSecond), width: timeToPx(clip.sourceOut - clip.sourceIn, pxPerSecond) }}>
            <div data-testid="clip-left-handle" className="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize bg-teal-700/40" onPointerDown={(event) => beginHorizontalDrag(event, (delta) => actions.trimClip(clip.id, 'left', delta))} />
            <div draggable data-testid="clip-drag" onDragStart={(event) => event.dataTransfer.setData('clip', clip.id)} className="h-full cursor-grab px-2"><span className="absolute z-10 text-[10px]">{asset?.name}</span>{asset?.waveform && <Waveform levels={asset.waveform} />}</div>
            <div data-testid="clip-right-handle" className="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize bg-teal-700/40" onPointerDown={(event) => beginHorizontalDrag(event, (delta) => actions.trimClip(clip.id, 'right', delta))} />
          </div>})}
        </div>)}
        <div data-testid="playhead" className="pointer-events-none absolute bottom-0 top-0 z-30 w-px bg-red-500" style={{ left: HEADER_WIDTH + timeToPx(playhead, pxPerSecond) }}><div className="-ml-1.5 h-3 w-3 rotate-45 bg-red-500" /></div>
        {snapGuide !== null && <div className="pointer-events-none absolute inset-y-0 z-40 border-l border-dashed border-blue-500" style={{ left: HEADER_WIDTH + timeToPx(snapGuide, pxPerSecond) }} />}
      </div>
    </div>
  </section>
}
