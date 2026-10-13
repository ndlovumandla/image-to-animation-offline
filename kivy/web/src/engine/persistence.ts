import { openDB, type DBSchema } from 'idb'
import JSZip from 'jszip'
import type { Project } from './types'
import { blobRegistry } from './blobRegistry'
import { assetRegistry } from './assetRegistry'
import { audioRegistry } from './audioRegistry'
import { decodeAudio } from './audioProcessor'

interface StudioDB extends DBSchema {
  projects: { key: string; value: Project }
  assets: { key: string; value: Blob }
}
const db = openDB<StudioDB>('sketch-video-studio', 1, { upgrade(database) { database.createObjectStore('projects'); database.createObjectStore('assets') } })

export async function saveProject(project: Project): Promise<void> {
  const database = await db; const transaction = database.transaction(['projects', 'assets'], 'readwrite'); await transaction.objectStore('projects').put(structuredClone(project), 'current')
  for (const [id, blob] of blobRegistry.entries()) await transaction.objectStore('assets').put(blob, id)
  await transaction.done
}
export async function restoreProject(context: AudioContext): Promise<Project | undefined> {
  const database = await db; const project = await database.get('projects', 'current'); if (!project) return undefined
  blobRegistry.clear(); assetRegistry.clear(); audioRegistry.clear()
  for (const asset of Object.values(project.assets)) {
    const blob = await database.get('assets', asset.id); if (!blob) throw new Error(`Missing saved asset: ${asset.name}`); blobRegistry.set(asset.id, blob)
    if (asset.kind === 'image') { if (!asset.sketchData) throw new Error(`Missing sketch data: ${asset.name}`); assetRegistry.set(asset.id, { image: await createImageBitmap(blob), sketchData: asset.sketchData }) }
    else { const decoded = await decodeAudio(blob, context); audioRegistry.set(asset.id, decoded.buffer); asset.waveform = decoded.waveform }
  }
  return project
}
export async function exportProject(project: Project): Promise<Blob> {
  const zip = new JSZip(); zip.file('project.json', JSON.stringify(project)); const folder = zip.folder('assets')!
  for (const asset of Object.values(project.assets)) { const blob = blobRegistry.get(asset.id); if (!blob) throw new Error(`Asset unavailable: ${asset.name}`); folder.file(asset.id, blob) }
  return zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
}
export async function importProject(file: Blob, context: AudioContext): Promise<Project> {
  const zip = await JSZip.loadAsync(file); const entry = zip.file('project.json'); if (!entry) throw new Error('Invalid project: project.json is missing'); const project = JSON.parse(await entry.async('text')) as Project
  if (!project.id || !Array.isArray(project.scenes) || !project.assets) throw new Error('Invalid project document')
  blobRegistry.clear(); assetRegistry.clear(); audioRegistry.clear()
  for (const asset of Object.values(project.assets)) { const zipped = zip.file(`assets/${asset.id}`); if (!zipped) throw new Error(`Project asset is missing: ${asset.name}`); const blob = await zipped.async('blob'); blobRegistry.set(asset.id, blob); if (asset.kind === 'image') { if (!asset.sketchData) throw new Error(`Missing sketch data: ${asset.name}`); assetRegistry.set(asset.id, { image: await createImageBitmap(blob), sketchData: asset.sketchData }) } else { const decoded = await decodeAudio(blob, context); audioRegistry.set(asset.id, decoded.buffer); asset.waveform = decoded.waveform } }
  await saveProject(project); return project
}
