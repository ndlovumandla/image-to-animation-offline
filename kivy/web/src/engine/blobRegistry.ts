class BlobRegistry {
  private readonly blobs = new Map<string, Blob>()
  set(id: string, blob: Blob): void { this.blobs.set(id, blob) }
  get(id: string): Blob | undefined { return this.blobs.get(id) }
  entries(): IterableIterator<[string, Blob]> { return this.blobs.entries() }
  clear(): void { this.blobs.clear() }
}
export const blobRegistry = new BlobRegistry()
