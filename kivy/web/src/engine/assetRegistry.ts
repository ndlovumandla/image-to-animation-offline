import type { SketchData } from './types'

export interface RenderAsset { image: CanvasImageSource; sketchData: SketchData }

class AssetRegistry {
  private readonly values = new Map<string, RenderAsset>()
  set(id: string, asset: RenderAsset): void { this.values.set(id, asset) }
  get(id: string): RenderAsset | undefined { return this.values.get(id) }
  snapshot(): ReadonlyMap<string, RenderAsset> { return new Map(this.values) }
  clear(): void { this.values.clear() }
}

export const assetRegistry = new AssetRegistry()
