import { projectDuration, sceneStarts } from './engine/timeline'
import { useProjectStore } from './store/projectStore'

export function App() {
  const project = useProjectStore((state) => state.project)
  const undo = useProjectStore((state) => state.undo)
  const redo = useProjectStore((state) => state.redo)
  return <main className="min-h-screen p-8">
    <header className="mx-auto flex max-w-5xl items-center justify-between rounded-xl bg-white p-4 shadow-sm">
      <div><h1 className="text-xl font-semibold">{project.name}</h1><p className="text-sm text-gray-500">Engine harness · {projectDuration(project).toFixed(2)} seconds</p></div>
      <div className="flex gap-2"><button className="rounded bg-gray-100 px-3 py-2" onClick={undo}>Undo</button><button className="rounded bg-gray-100 px-3 py-2" onClick={redo}>Redo</button></div>
    </header>
    <section className="mx-auto mt-6 max-w-5xl rounded-xl bg-white p-6 shadow-sm">
      <h2 className="font-medium">P0 project model</h2>
      <pre className="mt-3 overflow-auto rounded bg-gray-950 p-4 text-sm text-gray-100">{JSON.stringify(sceneStarts(project.scenes), null, 2)}</pre>
    </section>
  </main>
}
