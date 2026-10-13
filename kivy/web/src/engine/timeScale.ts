export const MIN_PX_PER_SECOND = 10
export const MAX_PX_PER_SECOND = 400

export function clampZoom(pxPerSecond: number): number {
  return Math.min(MAX_PX_PER_SECOND, Math.max(MIN_PX_PER_SECOND, pxPerSecond))
}
export function timeToPx(timeSec: number, pxPerSecond: number): number { return Math.max(0, timeSec) * clampZoom(pxPerSecond) }
export function pxToTime(px: number, pxPerSecond: number): number { return Math.max(0, px) / clampZoom(pxPerSecond) }
