class AudioRegistry {
  private readonly buffers = new Map<string, AudioBuffer>()
  set(id: string, buffer: AudioBuffer): void { this.buffers.set(id, buffer) }
  get(id: string): AudioBuffer | undefined { return this.buffers.get(id) }
  clear(): void { this.buffers.clear() }
}
export const audioRegistry = new AudioRegistry()
