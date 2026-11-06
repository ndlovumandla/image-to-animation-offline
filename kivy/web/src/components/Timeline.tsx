import { useEffect, useMemo, useRef, useState } from 'react'
import { MIN_SCENE_DURATION, projectDuration, sceneStarts } from '../engine/timeline'
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
  const [splitError, setSplitError] = useState<string | null>(null)
  const [snapGuide, setSnapGuide] = useState<number | null>(null)
  const [transitionEdit, setTransitionEdit] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const starts = sceneStarts(project.scenes); const duration = Math.max(1, projectDuration(project)); const contentWidth = Math.max(900, HEADER_WIDTH + timeToPx(duration, pxPerSecond) + 160)
  const snapPoints = useMemo(() => [playhead, ...starts, ...project.scenes.map((scene, index) => starts[index] + scene.duration), ...project.audioTracks.flatMap((track) => track.clips.flatMap((clip) => [clip.start, clip.start + clip.sourceOut - clip.sourceIn]))], [playhead, starts, project.scenes, project.audioTracks])
  const snap = (time: number, altKey: boolean) => { if (altKey) return time; const candidates = [...snapPoints, Math.round(time)]; const nearest = candidates.reduce((best, point) => Math.abs(point - time) < Math.abs(best - time) ? point : best, candidates[0] ?? time); return Math.abs(nearest - time) * pxPerSecond <= 8 ? nearest : time }
  const splitAtPlayhead = () => {
    setSplitError(null)
    try {
      const current = useProjectStore.getState().project
      if (selection?.kind === 'clip') {
        const selectedTrack = current.audioTracks.find((track) => track.clips.some((clip) => clip.id === selection.id))
        const selected = selectedTrack?.clips.find((clip) => clip.id === selection.id)
        const target = selected && playhead > selected.start + .001 && playhead < selected.start + selected.sourceOut - selected.sourceIn - .001
          ? selected
          : selectedTrack?.clips.find((clip) => playhead > clip.start + .001 && playhead < clip.start + clip.sourceOut - clip.sourceIn - .001)
        if (!target) throw new Error('Move the playhead inside the selected audio clip before splitting')
        setSelection({ kind: 'clip', id: actions.splitClip(target.id, playhead) })
        return
      }
      const currentStarts = sceneStarts(current.scenes)
      const target = current.scenes.find((scene, index) => playhead >= currentStarts[index] + MIN_SCENE_DURATION && playhead <= currentStarts[index] + scene.duration - MIN_SCENE_DURATION)
      if (!target) throw new Error('Move the playhead at least 0.5 seconds from a scene edge before splitting')
      setSelection({ kind: 'scene', id: actions.splitScene(target.id, playhead) })
    } catch (error) {
      setSplitError(error instanceof Error ? error.message : 'Could not split at the playhead')
    }
  }

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); event.shiftKey ? actions.redo() : actions.undo(); return }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd' && selection?.kind === 'scene') { event.preventDefault(); actions.duplicateScene(selection.id); return }
      if (event.key === 'Delete' && selection) { selection.kind === 'scene' ? actions.deleteScene(selection.id) : actions.deleteClip(selection.id); setSelection(null); return }
      if (event.key.toLowerCase() === 's' && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) { event.preventDefault(); splitAtPlayhead(); return }
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
        <button onClick={splitAtPlayhead} className="rounded bg-gray-100 px-3 py-1 text-sm">Split</button>
        <button onClick={() => selection?.kind === 'scene' && actions.duplicateScene(selection.id)} className="rounded bg-gray-100 px-3 py-1 text-sm">Duplicate</button>
        <button onClick={() => { if (selection) selection.kind === 'scene' ? actions.deleteScene(selection.id) : actions.deleteClip(selection.id) }} className="rounded bg-gray-100 px-3 py-1 text-sm">Delete</button>
        {selectedClip && <><button aria-label="Mute selected clip" aria-pressed={selectedClip.muted} onClick={() => actions.setClipMuted(selectedClip.id, !selectedClip.muted)} className="rounded bg-gray-100 px-3 py-1 text-sm">{selectedClip.muted ? 'Unmute clip' : 'Mute clip'}</button><label className="flex items-center gap-1 text-xs">Clip volume<input aria-label="Selected clip volume" type="range" min="0" max="2" step="0.05" value={selectedClip.volume} onChange={(event) => actions.setClipVolume(selectedClip.id, Number(event.target.value))} /></label></>}
      </div>
      {splitError && <span role="alert" className="mx-3 truncate text-xs text-red-600">{splitError}</span>}
      <label className="flex items-center gap-2 text-sm">Zoom <input aria-label="Timeline zoom" type="range" min="10" max="400" value={pxPerSecond} onChange={(event) => setPxPerSecond(Number(event.target.value))} /></label>
    </div>
    <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
      <div className="relative" style={{ width: contentWidth }}>
        <div data-testid="ruler" className="relative h-8 cursor-crosshair border-b border-gray-300 bg-[#f6f7f9]" onPointerDown={(event) => { const rect = event.currentTarget.getBoundingClientRect(); onSeek(pxToTime(event.clientX - rect.left - HEADER_WIDTH, pxPerSecond)) }}>
          {ticks.map((tick) => <div key={tick} className="absolute bottom-0 h-3 border-l border-gray-400 text-[10px] text-gray-600" style={{ left: HEADER_WIDTH + timeToPx(tick, pxPerSecond) }}><span className="absolute -top-4 left-1">{tick}s</span></div>)}
        </div>
        <div className="relative flex h-20 items-stretch border-b border-gray-300 bg-white" data-testid="scene-lane" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const assetId=event.dataTransfer.getData('asset'); if(assetId && project.assets[assetId]?.kind==='image') actions.addSceneFromAsset(assetId) }}>
          <div className="sticky left-0 z-20 w-44 shrink-0 border-r border-gray-300 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-600">Video</div>
          {project.scenes.map((scene, index) => {
            const hasRegions=scene.sketchSettings.enabled!==false&&scene.sketchRegions.length>0
            const sketchMinimum=Math.max(.1,scene.sketchRegions.length*.1)
            return <div key={scene.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); event.stopPropagation(); const id = event.dataTransfer.getData('scene'); const assetId=event.dataTransfer.getData('asset'); if (id) actions.reorderScene(id, index); else if(assetId && project.assets[assetId]?.kind==='image') actions.addSceneFromAsset(assetId,index) }} onClick={() => setSelection({ kind: 'scene', id: scene.id })} data-testid="scene-block" className={`relative shrink-0 overflow-visible rounded-lg border-2 bg-violet-100 ${selection?.id === scene.id ? 'border-violet-600' : 'border-white'}`} style={{ width: timeToPx(scene.duration, pxPerSecond) }}>
              {index > 0 && <div data-testid="scene-left-handle" className="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize bg-violet-400/40" onPointerDown={(event) => beginHorizontalDrag(event, (delta) => actions.resizeSceneLeft(scene.id, delta))} />}
              <div draggable data-testid="scene-drag" onDragStart={(event) => event.dataTransfer.setData('scene', scene.id)} className="relative h-full cursor-grab overflow-hidden rounded-lg">
                <AssetThumbnail assetId={scene.assetId} />
                {hasRegions&&<div className="pointer-events-none absolute inset-0 z-20" data-testid="sketch-region-track">{scene.sketchRegions.map((region,regionIndex)=>{const elapsed=scene.sketchRegions.slice(0,regionIndex).reduce((sum,item)=>sum+item.duration,0),left=elapsed/scene.duration*100,width=region.duration/scene.duration*100,boundary=(elapsed+region.duration)/scene.duration*100;return <div key={region.id} data-testid="sketch-region-segment" title={`${region.name}: ${region.duration.toFixed(3)} seconds`} className="absolute inset-y-0 border-r-2" style={{left:`${left}%`,width:`${width}%`,backgroundColor:`${region.color}33`,borderRightColor:region.color}}><span className="absolute left-1 top-6 max-w-[calc(100%-4px)] truncate rounded bg-white/90 px-1 text-[9px] font-semibold text-slate-800">R{regionIndex+1} · {region.duration.toFixed(2)}s</span>{regionIndex<scene.sketchRegions.length-1&&<button data-testid="sketch-region-boundary" role="slider" aria-label={`Scene ${index+1} region ${regionIndex+1} boundary`} aria-valuemin={Math.round((elapsed+.1)*1000)} aria-valuemax={Math.round((elapsed+region.duration+scene.sketchRegions[regionIndex+1].duration-.1)*1000)} aria-valuenow={Math.round(boundary/100*scene.duration*1000)} title={`Drag to time ${region.name} and ${scene.sketchRegions[regionIndex+1].name}`} className="pointer-events-auto absolute -right-2 inset-y-0 z-40 w-4 cursor-ew-resize border-x border-white bg-slate-900/70 shadow hover:bg-violet-700 focus:bg-violet-700 focus:outline-none" onClick={event=>event.stopPropagation()} onKeyDown={event=>{if(event.key!=='ArrowLeft'&&event.key!=='ArrowRight')return;event.preventDefault();actions.resizeSketchRegionBoundary(scene.id,regionIndex,(event.key==='ArrowRight'?1:-1)*(event.shiftKey?.1:.01))}} onPointerDown={event=>beginHorizontalDrag(event,delta=>actions.resizeSketchRegionBoundary(scene.id,regionIndex,delta))}/>}</div>})}</div>}
                {scene.sketchSettings.enabled!==false&&!hasRegions&&<div data-testid="sketch-duration-bar" title={`Sketch completes in ${(scene.sketchDuration??scene.duration).toFixed(3)} seconds`} className="absolute bottom-0 left-0 h-1.5 bg-cyan-400" style={{width:`${Math.min(100,(scene.sketchDuration??scene.duration)/scene.duration*100)}%`}}/>}
                <span className="absolute bottom-2 right-1 z-30 rounded bg-black/70 px-1.5 py-0.5 text-[10px] text-white">{scene.sketchSettings.enabled===false?`Scene ${scene.duration.toFixed(1)}s · Sketch off`:hasRegions?`${scene.sketchRegions.length} regions · ${(scene.sketchDuration??scene.duration).toFixed(2)}s`:`Scene ${scene.duration.toFixed(1)}s · Draw ${(scene.sketchDuration??scene.duration).toFixed(1)}s`}</span><span className="absolute left-1 top-1 z-30 rounded bg-black/55 px-1 text-[10px] text-white">{index + 1}</span>
              </div>
              {scene.sketchSettings.enabled!==false&&<div data-testid="sketch-duration-handle" role="slider" tabIndex={0} aria-label={`Scene ${index+1} sketch completion`} aria-valuemin={Math.round(sketchMinimum*1000)} aria-valuemax={Math.round(scene.duration*1000)} aria-valuenow={Math.round((scene.sketchDuration??scene.duration)*1000)} title={`Drag to set sketch completion: ${(scene.sketchDuration??scene.duration).toFixed(3)}s`} className="absolute bottom-0 z-30 h-6 w-3 -translate-x-1/2 cursor-ew-resize rounded-t bg-cyan-600 shadow ring-2 ring-white focus:outline-none focus:ring-violet-600" style={{left:`${Math.min(100,(scene.sketchDuration??scene.duration)/scene.duration*100)}%`}} onClick={event=>event.stopPropagation()} onKeyDown={(event)=>{if(event.key!=='ArrowLeft'&&event.key!=='ArrowRight'&&event.key!=='Home'&&event.key!=='End')return;event.preventDefault();const current=scene.sketchDuration??scene.duration,next=event.key==='Home'?sketchMinimum:event.key==='End'?scene.duration:current+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?.1:.01);actions.setSketchDurationMs(scene.id,Math.round(next*1000))}} onPointerDown={(event)=>{event.stopPropagation();const initial=scene.sketchDuration??scene.duration;beginHorizontalDrag(event,(delta,alt)=>{const raw=Math.max(sketchMinimum,Math.min(scene.duration,initial+delta)),target=alt?raw:snap(starts[index]+raw,false)-starts[index];actions.setSketchDurationMs(scene.id,Math.round(Math.max(sketchMinimum,Math.min(scene.duration,target))*1000))})}}/>}
              <div data-testid="scene-right-handle" className="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize bg-violet-500/50" onPointerDown={(event) => beginHorizontalDrag(event, (delta, alt) => { const targetEnd = snap(starts[index] + scene.duration + delta, alt); actions.resizeScene(scene.id, targetEnd - starts[index]) })} />
            </div>
          })}
          <div data-testid="image-drop-zone" className="m-2 flex min-w-40 items-center justify-center rounded-lg border-2 border-dashed border-violet-300 px-4 text-center text-xs font-medium text-violet-700">Drag an uploaded image here</div>
          {project.scenes.slice(0, -1).map((scene, index) => { const transition = project.transitions.find((item) => item.fromSceneId === scene.id); const current = transition?.type ?? 'none',duration=transition?.duration??.5; return <div key={`transition-${scene.id}`} className="absolute -top-4 z-30 -translate-x-1/2" style={{ left: HEADER_WIDTH + timeToPx(starts[index] + scene.duration, pxPerSecond) }}><button data-testid="transition-marker" title={`Transition: ${current}`} className="h-8 min-w-8 rounded-full border border-violet-400 bg-white px-1 text-[10px] uppercase shadow" onClick={(event) => { event.stopPropagation();setTransitionEdit(transitionEdit===scene.id?null:scene.id) }}>{current === 'none' ? '+' : current}</button>{transitionEdit===scene.id&&<div className="absolute left-1/2 top-9 z-50 w-64 -translate-x-1/2 rounded-xl border bg-white p-3 text-left shadow-xl" onClick={e=>e.stopPropagation()}><label className="text-xs font-semibold">Style<select aria-label="Transition style" className="mt-1 w-full rounded border p-2" value={current} onChange={e=>actions.setTransition(scene.id,e.target.value as TransitionType,duration)}>{['none','fade','dissolve','slide','push','wipe','zoom','blur'].map(type=><option key={type}>{type}</option>)}</select></label><label className="mt-3 block text-xs font-semibold">Duration: {duration.toFixed(3)}s<input aria-label="Transition duration" className="mt-1 w-full" type="range" min="0.1" max={Math.min(3,scene.duration/2,project.scenes[index+1].duration/2)} step="0.001" value={duration} onChange={e=>actions.setTransition(scene.id,current,Number(e.target.value))}/></label><button className="mt-3 w-full rounded bg-violet-600 py-2 text-xs font-semibold text-white" onClick={()=>actions.setAllTransitions(current,duration)}>Apply to all scenes</button></div>}</div> })}
        </div>
        {project.audioTracks.map((track) => <div key={track.id} data-testid="timeline-audio-lane" className="relative h-20 border-b border-gray-300 bg-[#f1f3f5]" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const id = event.dataTransfer.getData('clip'),assetId=event.dataTransfer.getData('asset'); const rect = event.currentTarget.getBoundingClientRect(),at=snap(pxToTime(event.clientX - rect.left - HEADER_WIDTH, pxPerSecond), event.altKey); if (id) actions.moveClip(id, track.id, at); else if(assetId && project.assets[assetId]?.kind==='audio') actions.addAudioFromAsset(assetId,at,track.id) }}>
          <div className="sticky left-0 z-20 flex h-full w-44 items-center gap-2 border-r border-gray-300 bg-white/95 px-2 text-xs"><span className="max-w-16 truncate">{track.name}</span><button aria-label={`Timeline mute ${track.name}`} onClick={() => actions.setTrackMuted(track.id, !track.muted)}>{track.muted ? '🔇' : '🔊'}</button><input aria-label={`Timeline volume ${track.name}`} className="w-16" type="range" min="0" max="2" step="0.05" value={track.volume} onChange={(event) => actions.setTrackVolume(track.id, Number(event.target.value))} /></div>
          {track.clips.map((clip) => { const asset = project.assets[clip.assetId]; return <div key={clip.id} onClick={() => setSelection({ kind: 'clip', id: clip.id })} data-testid="audio-clip" className={`absolute top-2 h-16 overflow-hidden rounded-lg border-2 bg-teal-100 ${selection?.id === clip.id ? 'border-teal-700' : 'border-teal-300'}`} style={{ left: HEADER_WIDTH + timeToPx(clip.start, pxPerSecond), width: timeToPx(clip.sourceOut - clip.sourceIn, pxPerSecond) }}>
            <div data-testid="clip-left-handle" className="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize bg-teal-700/40" onPointerDown={(event) => beginHorizontalDrag(event, (delta) => actions.trimClip(clip.id, 'left', delta))} />
            <div draggable data-testid="clip-drag" onDragStart={(event) => event.dataTransfer.setData('clip', clip.id)} className="h-full cursor-grab px-2"><span className="absolute z-10 text-[10px]">{asset?.name}</span>{asset?.waveform && <Waveform levels={asset.waveform} />}</div>
            <div data-testid="clip-right-handle" className="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize bg-teal-700/40" onPointerDown={(event) => beginHorizontalDrag(event, (delta) => actions.trimClip(clip.id, 'right', delta))} />
          </div>})}
        </div>)}
        <div data-testid="audio-drop-zone" className="relative flex h-16 items-center border-b border-gray-300 bg-[#eef7f6]" onDragOver={(event)=>event.preventDefault()} onDrop={(event)=>{event.preventDefault();const assetId=event.dataTransfer.getData('asset');if(assetId&&project.assets[assetId]?.kind==='audio'){const rect=event.currentTarget.getBoundingClientRect();actions.addAudioFromAsset(assetId,Math.max(0,pxToTime(event.clientX-rect.left-HEADER_WIDTH,pxPerSecond)))}}}>
          <div className="sticky left-0 z-20 flex h-full w-44 shrink-0 items-center border-r border-gray-300 bg-white/95 px-3 text-xs font-semibold text-slate-600">＋ Audio track</div>
          <div className="ml-3 rounded-lg border-2 border-dashed border-teal-400 px-5 py-2 text-xs font-medium text-teal-800">Drag uploaded audio here to create a track</div>
        </div>
        <div data-testid="playhead" className="pointer-events-none absolute bottom-0 top-0 z-30 w-px bg-red-500" style={{ left: HEADER_WIDTH + timeToPx(playhead, pxPerSecond) }}><div className="-ml-1.5 h-3 w-3 rotate-45 bg-red-500" /></div>
        {snapGuide !== null && <div className="pointer-events-none absolute inset-y-0 z-40 border-l border-dashed border-blue-500" style={{ left: HEADER_WIDTH + timeToPx(snapGuide, pxPerSecond) }} />}
      </div>
    </div>
  </section>
}
