const hands = new Map<string, ImageBitmap>()
let loading: Promise<void> | undefined

async function makeTransparentHand(): Promise<ImageBitmap> {
  const [handResponse, maskResponse] = await Promise.all([fetch('/hands/classic.png'), fetch('/hands/classic-mask.png')])
  if (!handResponse.ok || !maskResponse.ok) throw new Error('Drawing-hand artwork is unavailable')
  const [hand, mask] = await Promise.all([createImageBitmap(await handResponse.blob()), createImageBitmap(await maskResponse.blob())])
  const canvas = new OffscreenCanvas(hand.width, hand.height)
  const context = canvas.getContext('2d')!
  context.drawImage(hand, 0, 0)
  context.globalCompositeOperation = 'destination-in'
  context.drawImage(mask, 0, 0, hand.width, hand.height)
  hand.close(); mask.close()
  return createImageBitmap(await canvas.convertToBlob({ type: 'image/png' }))
}

export function loadHands(): Promise<void> {
  if (!loading) loading = makeTransparentHand().then((image) => { hands.set('classic', image) }).catch(() => undefined)
  return loading
}

export const getHand = (style: 'classic' | 'left' | 'marker') => hands.get('classic')
