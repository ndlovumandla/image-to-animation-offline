const hands = new Map<string, ImageBitmap>()
let loading: Promise<void> | undefined

async function makeTransparentHand(): Promise<ImageBitmap> {
  const [handResponse, maskResponse] = await Promise.all([fetch('/hands/classic.png'), fetch('/hands/classic-mask.png')])
  if (!handResponse.ok || !maskResponse.ok) throw new Error('Drawing-hand artwork is unavailable')
  const [hand, mask] = await Promise.all([createImageBitmap(await handResponse.blob()), createImageBitmap(await maskResponse.blob())])
  const maskCanvas = new OffscreenCanvas(mask.width, mask.height)
  const maskContext = maskCanvas.getContext('2d')!
  maskContext.drawImage(mask, 0, 0)
  const maskPixels = maskContext.getImageData(0, 0, mask.width, mask.height).data
  let left = mask.width, top = mask.height, right = 0, bottom = 0
  for (let y = 0; y < mask.height; y += 1) for (let x = 0; x < mask.width; x += 1) {
    if (maskPixels[(y * mask.width + x) * 4] > 127) { left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y) }
  }
  const width = right - left + 1, height = bottom - top + 1
  const canvas = new OffscreenCanvas(width, height)
  const context = canvas.getContext('2d')!
  context.drawImage(hand, left, top, width, height, 0, 0, width, height)
  context.globalCompositeOperation = 'destination-in'
  context.drawImage(mask, left, top, width, height, 0, 0, width, height)
  hand.close(); mask.close()
  return createImageBitmap(await canvas.convertToBlob({ type: 'image/png' }))
}

export function loadHands(): Promise<void> {
  if (!loading) loading = makeTransparentHand().then((image) => { hands.set('classic', image) }).catch(() => undefined)
  return loading
}

export const getHand = (style: 'classic' | 'left' | 'marker') => hands.get('classic')
