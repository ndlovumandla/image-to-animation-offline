import { sceneStarts } from './timeline'
import type { Project, Scene, Stroke, Transition } from './types'
import type { RenderAsset } from './assetRegistry'
import { getHand } from './handRegistry'

export interface FrameState { scene?: Scene; localTime: number; progress: number; drawProgress: number; fillOpacity: number }
export interface ActiveTransition { transition: Transition; from: Scene; to: Scene; progress: number }
const clamp01 = (value: number) => Math.max(0, Math.min(1, value))

export function frameState(project: Project, timeSec: number): FrameState {
  const starts = sceneStarts(project.scenes)
  let index = project.scenes.findIndex((scene, i) => timeSec < starts[i] + scene.duration)
  if (index < 0 && project.scenes.length) index = project.scenes.length - 1
  if (index < 0) return { localTime: 0, progress: 0, drawProgress: 0, fillOpacity: 0 }
  const scene = project.scenes[index]; const localTime = Math.max(0, Math.min(scene.duration, timeSec - starts[index])); const normalized = clamp01(localTime / scene.duration)
  const progress = scene.progressStart + normalized * (scene.progressEnd - scene.progressStart)
  return { scene, localTime, progress, drawProgress: clamp01(progress / 0.75), fillOpacity: scene.sketchSettings.fillMode === 'none' ? 0 : clamp01((progress - 0.65) / 0.35) }
}

function drawPartialStroke(context: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D, stroke: Stroke, length: number) {
  if (length <= 0 || stroke.points.length < 2) return undefined
  let tip=stroke.points[0]
  context.beginPath(); context.moveTo(stroke.points[0].x, stroke.points[0].y); let remaining = length
  for (let i = 1; i < stroke.points.length && remaining > 0; i += 1) { const a = stroke.points[i - 1]; const b = stroke.points[i]; const segment = Math.hypot(b.x - a.x, b.y - a.y); if (remaining >= segment) { context.lineTo(b.x, b.y);tip=b; remaining -= segment } else { const ratio = segment ? remaining / segment : 0;tip={x:a.x+(b.x-a.x)*ratio,y:a.y+(b.y-a.y)*ratio}; context.lineTo(tip.x,tip.y); remaining = 0 } }
  context.stroke();return tip
}

function drawHand(context:CanvasRenderingContext2D|OffscreenCanvasRenderingContext2D,x:number,y:number,style:'classic'|'left'|'marker',imageHeight:number){
  const artwork=getHand(style)
  if(artwork){context.save();context.translate(x,y);if(style==='marker')context.filter='sepia(.4) saturate(.75) brightness(.8)';const height=Math.max(60,Math.min(imageHeight*.56,330)),width=artwork.width/artwork.height*height;if(style==='left'){context.scale(-1,1);context.drawImage(artwork,-width,0,width,height)}else context.drawImage(artwork,0,0,width,height);context.restore();return}
  context.save();context.translate(x,y);if(style==='left')context.scale(-1,1);context.rotate(-.55)
  context.fillStyle=style==='marker'?'#82502f':'#e7b985';context.strokeStyle='#5b3727';context.lineWidth=2
  context.beginPath();context.roundRect(14,8,70,38,16);context.fill();context.stroke()
  context.fillStyle=style==='marker'?'#18181b':'#f4f4f5';context.beginPath();context.roundRect(-46,-5,75,14,6);context.fill();context.stroke()
  context.fillStyle='#1e3a8a';context.fillRect(-55,-5,14,14);context.restore()
}

export function transitionState(project: Project, timeSec: number): ActiveTransition | undefined {
  const starts = sceneStarts(project.scenes)
  for (const transition of project.transitions) {
    if (transition.type === 'none' || transition.duration <= 0) continue
    const fromIndex = project.scenes.findIndex((scene) => scene.id === transition.fromSceneId); const toIndex = fromIndex + 1
    if (fromIndex < 0 || project.scenes[toIndex]?.id !== transition.toSceneId) continue
    const end = starts[fromIndex] + project.scenes[fromIndex].duration; const begin = end - transition.duration
    if (timeSec >= begin && timeSec < end) return { transition, from: project.scenes[fromIndex], to: project.scenes[toIndex], progress: clamp01((timeSec - begin) / transition.duration) }
  }
}

function drawScene(context: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D, scene: Scene, asset: RenderAsset, progress: number): void {
  const data = asset.sketchData; const scale = Math.min(context.canvas.width / data.width, context.canvas.height / data.height); const x = (context.canvas.width - data.width * scale) / 2; const y = (context.canvas.height - data.height * scale) / 2
  context.save(); context.translate(x, y); context.scale(scale, scale); context.lineCap = 'round'; context.lineJoin = 'round'; context.strokeStyle = scene.sketchSettings.style === 'marker' ? '#263238' : '#101114'; context.lineWidth = scene.sketchSettings.lineWidth / scale
  let remaining = data.totalLength * clamp01(progress / 0.75)
  let tip:{x:number;y:number}|undefined
  for (const stroke of data.strokes) { if (remaining <= 0) break; tip=drawPartialStroke(context, stroke, Math.min(stroke.length, remaining))??tip; remaining -= stroke.length }
  if(scene.sketchSettings.showHand&&tip&&progress<.76)drawHand(context,tip.x,tip.y,scene.sketchSettings.handStyle??'classic',data.height)
  const fillOpacity = scene.sketchSettings.fillMode === 'none' ? 0 : clamp01((progress - 0.65) / 0.35)
  if (fillOpacity > 0) { context.globalAlpha *= fillOpacity; context.drawImage(asset.image, 0, 0, data.width, data.height) }
  context.restore()
}

export function renderFrame(context: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D, project: Project, assets: ReadonlyMap<string, RenderAsset>, timeSec: number): void {
  context.save(); context.setTransform(1, 0, 0, 1, 0, 0); context.fillStyle = project.background; context.fillRect(0, 0, context.canvas.width, context.canvas.height)
  const state = frameState(project, timeSec); if (!state.scene) { context.restore(); return }
  const asset = assets.get(state.scene.assetId); if (!asset) { context.restore(); return }
  drawScene(context, state.scene, asset, state.progress)
  const active = transitionState(project, timeSec); const nextAsset = active && assets.get(active.to.assetId)
  if (active && nextAsset) {
    context.save()
    if (active.transition.type === 'fade' || active.transition.type === 'dissolve') context.globalAlpha = active.transition.type==='dissolve' ? active.progress*active.progress*(3-2*active.progress) : active.progress
    if (active.transition.type === 'slide' || active.transition.type === 'push') context.translate(context.canvas.width * (1 - active.progress), 0)
    if (active.transition.type === 'wipe') { context.beginPath(); context.rect(0, 0, context.canvas.width * active.progress, context.canvas.height); context.clip() }
    if(active.transition.type==='zoom'){const scale=.7+.3*active.progress;context.translate(context.canvas.width/2,context.canvas.height/2);context.scale(scale,scale);context.translate(-context.canvas.width/2,-context.canvas.height/2);context.globalAlpha=active.progress}
    if(active.transition.type==='blur'){context.filter=`blur(${(1-active.progress)*18}px)`;context.globalAlpha=active.progress}
    context.fillStyle = project.background; context.fillRect(0, 0, context.canvas.width, context.canvas.height)
    drawScene(context, active.to, nextAsset, active.to.progressStart)
    context.restore()
  }
  context.restore()
}
