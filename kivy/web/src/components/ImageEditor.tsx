import { useEffect, useRef, useState } from 'react'
import { Canvas, Circle, FabricImage, FabricObject, Rect, Textbox, loadSVGFromString, util } from 'fabric'

type IconHit = { prefix: string; name: string }
type MediaHit = { id: string; title: string; thumbnail: string; url: string; creator?: string; license?: string }
type Props = { source: Blob; name: string; onClose(): void; onCommit(file: File): Promise<void> }

export default function ImageEditor({ source, name, onClose, onCommit }: Props) {
  const elementRef = useRef<HTMLCanvasElement>(null)
  const editorRef = useRef<Canvas | null>(null)
  const [query, setQuery] = useState('education')
  const [icons, setIcons] = useState<IconHit[]>([])
  const [media, setMedia] = useState<MediaHit[]>([])
  const [resultType, setResultType] = useState<'graphics'|'photos'>('graphics')
  const [busy, setBusy] = useState('')
  const [fill, setFill] = useState('#6d28d9')

  useEffect(() => {
    if (!elementRef.current) return
    const canvas = new Canvas(elementRef.current, { width: 960, height: 540, backgroundColor: '#ffffff', preserveObjectStacking: true })
    editorRef.current = canvas
    const url = URL.createObjectURL(source)
    void FabricImage.fromURL(url).then((image) => {
      const scale = Math.min(960 / (image.width || 1), 540 / (image.height || 1))
      image.set({ left: 480, top: 270, originX: 'center', originY: 'center', scaleX: scale, scaleY: scale, name: 'Background image' })
      canvas.add(image); canvas.setActiveObject(image); canvas.renderAll()
    }).finally(() => URL.revokeObjectURL(url))
    return () => { editorRef.current = null; canvas.dispose() }
  }, [source])

  const expandedQuery = () => {
    const normalized=query.trim().toLowerCase(), synonyms:Record<string,string>= { 'cloud thought':'thought bubble', 'thought cloud':'thought bubble', school:'education learning', teacher:'education classroom', idea:'idea lightbulb', speech:'speech bubble', science:'science education laboratory' }
    return synonyms[normalized] ? `${query} ${synonyms[normalized]}` : query
  }
  async function searchElements() {
    setBusy('Searching elements…')
    try {
      if(resultType==='graphics'){
        const response = await fetch(`https://api.iconify.design/search?query=${encodeURIComponent(expandedQuery())}&limit=64`)
        if (!response.ok) throw new Error('Element search failed')
        const data = await response.json() as { icons: string[] }
        setIcons(data.icons.map((value) => { const [prefix, name] = value.split(':'); return { prefix, name } }))
      } else {
        const params=new URLSearchParams({q:expandedQuery(),page_size:'40',license_type:'commercial,modification',mature:'false'})
        const response=await fetch(`https://api.openverse.org/v1/images/?${params}`);if(!response.ok)throw new Error('Open media search failed')
        const data=await response.json() as {results:MediaHit[]};setMedia(data.results.filter(item=>item.thumbnail&&item.url))
      }
    } catch (error) { setBusy(error instanceof Error ? error.message : 'Element search failed'); return }
    setBusy('')
  }

  async function addMedia(item:MediaHit){const canvas=editorRef.current;if(!canvas)return;setBusy('Adding open image…');try{const response=await fetch(item.url);if(!response.ok)throw new Error('Image download failed');const blob=await response.blob(),url=URL.createObjectURL(blob);const image=await FabricImage.fromURL(url,{crossOrigin:'anonymous'});URL.revokeObjectURL(url);image.set({left:330,top:150,name:item.title});image.scaleToWidth(Math.min(420,image.width||420));canvas.add(image);canvas.setActiveObject(image);canvas.renderAll()}catch(error){setBusy(error instanceof Error?error.message:'Image download failed');return}setBusy('')}

  async function addIcon(icon: IconHit) {
    const canvas = editorRef.current; if (!canvas) return
    setBusy('Adding element…')
    try {
      const response = await fetch(`https://api.iconify.design/${icon.prefix}/${icon.name}.svg?height=160&color=${encodeURIComponent(fill)}`)
      const svg = await response.text()
      const parsed = await loadSVGFromString(svg)
      const objects = parsed.objects.filter((item): item is FabricObject => Boolean(item))
      const group = util.groupSVGElements(objects, parsed.options)
      group.set({ left: 400, top: 190, name: `${icon.prefix}:${icon.name}` }); group.scaleToWidth(160)
      canvas.add(group); canvas.setActiveObject(group); canvas.renderAll()
    } finally { setBusy('') }
  }

  function addText() { const canvas=editorRef.current; if(!canvas)return; const text=new Textbox('Double-click to edit', { left:300, top:220, width:360, fontSize:42, fontWeight:'bold', fill, textAlign:'center', name:'Text' }); canvas.add(text);canvas.setActiveObject(text);canvas.renderAll() }
  function addShape(kind:'rect'|'circle') { const canvas=editorRef.current;if(!canvas)return; const shape=kind==='rect'?new Rect({left:360,top:190,width:240,height:140,rx:18,ry:18,fill,name:'Rectangle'}):new Circle({left:390,top:170,radius:100,fill,name:'Circle'});canvas.add(shape);canvas.setActiveObject(shape);canvas.renderAll() }
  function deleteSelected(){const c=editorRef.current;if(!c)return;c.getActiveObjects().forEach(o=>c.remove(o));c.discardActiveObject();c.renderAll()}
  function layer(direction:'up'|'down'){const c=editorRef.current,o=c?.getActiveObject();if(!c||!o)return;direction==='up'?c.bringObjectForward(o):c.sendObjectBackwards(o);c.renderAll()}
  function updateSelectedColor(color:string){setFill(color);const c=editorRef.current,o=c?.getActiveObject();if(o){o.set('fill',color);c?.renderAll()}}

  async function replaceSelectedImage(blob:Blob, selected:FabricImage){const canvas=editorRef.current;if(!canvas)return;const url=URL.createObjectURL(blob),replacement=await FabricImage.fromURL(url);URL.revokeObjectURL(url);replacement.set({left:selected.left,top:selected.top,scaleX:selected.getScaledWidth()/(replacement.width||1),scaleY:selected.getScaledHeight()/(replacement.height||1),angle:selected.angle,originX:selected.originX,originY:selected.originY,name:'AI background removed'});canvas.remove(selected);canvas.add(replacement);canvas.setActiveObject(replacement);canvas.renderAll()}
  async function magicRemove() {
    const canvas=editorRef.current, selected=canvas?.getActiveObject(); if(!canvas || !(selected instanceof FabricImage)){setBusy('Select an image first');return}
    setBusy('AI is separating the subject…')
    await new Promise<void>((resolve)=>requestAnimationFrame(()=>resolve()))
    try {
      const selectedCanvas=selected.toCanvasElement(),input=await new Promise<Blob|null>(resolve=>selectedCanvas.toBlob(resolve,'image/png'))
      if(input){try{const body=new FormData();body.append('file',input,'image.png');const response=await fetch('http://127.0.0.1:7000/api/remove?model=u2net&alpha_matting=true',{method:'POST',body,signal:AbortSignal.timeout(45_000)});if(response.ok){await replaceSelectedImage(await response.blob(),selected);setBusy('AI background removed');return}}catch{/* Offline fallback below. */}}
      const sourceElement=selected.getElement() as CanvasImageSource
      const width=selected.width || 1,height=selected.height || 1, work=document.createElement('canvas');work.width=width;work.height=height
      const ctx=work.getContext('2d',{willReadFrequently:true})!;ctx.drawImage(sourceElement,0,0,width,height)
      const image=ctx.getImageData(0,0,width,height),data=image.data, seen=new Uint8Array(width*height),queue=[0,width-1,(height-1)*width,height*width-1]
      const samples=queue.map(i=>[data[i*4],data[i*4+1],data[i*4+2]]), tolerance=48
      for(let head=0;head<queue.length;head++){const i=queue[head];if(i<0||i>=width*height||seen[i])continue;seen[i]=1;const x=i%width,y=Math.floor(i/width),p=i*4;const match=samples.some(s=>Math.abs(data[p]-s[0])+Math.abs(data[p+1]-s[1])+Math.abs(data[p+2]-s[2])<tolerance*3);if(!match)continue;data[p+3]=0;if(x>0)queue.push(i-1);if(x<width-1)queue.push(i+1);if(y>0)queue.push(i-width);if(y<height-1)queue.push(i+width)}
      ctx.putImageData(image,0,0); const replacement=new FabricImage(work, { left:selected.left,top:selected.top,scaleX:selected.scaleX,scaleY:selected.scaleY,angle:selected.angle,originX:selected.originX,originY:selected.originY,name:'Background removed' });canvas.remove(selected);canvas.add(replacement);canvas.setActiveObject(replacement);canvas.renderAll();setBusy('Background removed')
    } catch { setBusy('Could not remove this background') }
  }

  async function apply() { const canvas=editorRef.current;if(!canvas)return;setBusy('Preparing sketch scene…');canvas.discardActiveObject();canvas.renderAll();const blob=await new Promise<Blob|null>(resolve=>canvas.getElement().toBlob(resolve,'image/png'));if(!blob){setBusy('Could not render image');return}await onCommit(new File([blob],`${name.replace(/\.[^.]+$/,'')}-edited.png`,{type:'image/png'}));onClose() }

  useEffect(()=>{const timer=setTimeout(()=>void searchElements(),query==='education'?0:400);return()=>clearTimeout(timer)},[query,resultType])
  return <div className="fixed inset-0 z-[100] flex flex-col bg-[#eef0f4]">
    <header className="flex h-14 items-center gap-3 bg-gradient-to-r from-[#121338] to-[#7c3aed] px-4 text-white"><button onClick={onClose} className="rounded px-3 py-2 hover:bg-white/15">← Video editor</button><strong>Image editor</strong><span className="text-sm text-white/70">{name}</span><div className="ml-auto flex gap-2"><button onClick={()=>{editorRef.current?.discardActiveObject();editorRef.current?.renderAll()}} className="rounded px-3 py-2 hover:bg-white/15">Preview</button><button onClick={()=>void apply()} className="rounded bg-white px-4 py-2 font-semibold text-violet-700">Use in video</button></div></header>
    <div className="flex min-h-0 flex-1"><aside className="w-80 shrink-0 overflow-y-auto border-r bg-white p-4"><h2 className="text-lg font-semibold">Elements</h2><div className="relative mt-3"><span className="pointer-events-none absolute left-3 top-2.5 text-slate-400">⌕</span><input aria-label="Search elements" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void searchElements()}} className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-10 shadow-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100" placeholder="Search icons, photos, ideas…"/><button aria-label="Clear search" onClick={()=>setQuery('')} className="absolute right-2 top-1.5 rounded px-2 py-1 text-slate-400 hover:bg-slate-100">×</button></div><div className="mt-2 flex gap-1 overflow-x-auto">{['thought cloud','arrows','school','people','science'].map(term=><button key={term} onClick={()=>setQuery(term)} className="whitespace-nowrap rounded-full bg-slate-100 px-2.5 py-1 text-xs hover:bg-violet-100">{term}</button>)}</div><div className="mt-3 flex border-b"><button onClick={()=>setResultType('graphics')} className={`flex-1 border-b-2 py-2 text-sm font-medium ${resultType==='graphics'?'border-violet-600 text-violet-700':'border-transparent text-slate-500'}`}>Graphics</button><button onClick={()=>setResultType('photos')} className={`flex-1 border-b-2 py-2 text-sm font-medium ${resultType==='photos'?'border-violet-600 text-violet-700':'border-transparent text-slate-500'}`}>Open photos</button></div>{resultType==='graphics'?<div className="mt-3 grid grid-cols-4 gap-2">{icons.map(icon=><button key={`${icon.prefix}:${icon.name}`} title={icon.name} onClick={()=>void addIcon(icon)} className="aspect-square rounded-lg border bg-slate-50 p-2 hover:border-violet-500"><img alt={icon.name} src={`https://api.iconify.design/${icon.prefix}/${icon.name}.svg`}/></button>)}</div>:<div className="mt-3 grid grid-cols-2 gap-2">{media.map(item=><button key={item.id} title={`${item.title} — ${item.creator??'Unknown creator'} — ${item.license??'open license'}`} onClick={()=>void addMedia(item)} className="group relative aspect-square overflow-hidden rounded-lg bg-slate-100"><img alt={item.title} loading="lazy" src={item.thumbnail} className="h-full w-full object-cover"/><span className="absolute inset-x-0 bottom-0 truncate bg-black/65 p-1 text-[10px] text-white opacity-0 group-hover:opacity-100">{item.title}</span></button>)}</div>}<p className="mt-4 text-[11px] leading-4 text-slate-500">Graphics: Iconify open-source collections. Photos: Openverse Creative Commons/public-domain catalog. Verify the source license before publishing.</p></aside>
      <div className="flex min-w-0 flex-1 flex-col"><div className="flex h-12 shrink-0 items-center gap-2 border-b bg-white px-3"><button onClick={addText} className="rounded bg-slate-100 px-3 py-1.5 text-sm">+ Text</button><button onClick={()=>addShape('rect')} className="rounded bg-slate-100 px-3 py-1.5 text-sm">▭ Shape</button><button onClick={()=>addShape('circle')} className="rounded bg-slate-100 px-3 py-1.5 text-sm">○ Circle</button><label className="flex items-center gap-2 rounded bg-slate-100 px-2 py-1 text-sm">Color <input aria-label="Element color" type="color" value={fill} onChange={e=>updateSelectedColor(e.target.value)}/></label><span className="h-6 border-l"/><button onClick={()=>void magicRemove()} className="rounded bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-700">✦ Magic remover</button><button onClick={()=>layer('up')} className="rounded px-2 py-1 text-sm hover:bg-slate-100">Forward</button><button onClick={()=>layer('down')} className="rounded px-2 py-1 text-sm hover:bg-slate-100">Backward</button><button onClick={deleteSelected} className="rounded px-2 py-1 text-sm text-red-600 hover:bg-red-50">Delete</button></div>
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-8"><div className="overflow-hidden bg-white shadow-2xl"><canvas ref={elementRef}/></div></div>{busy&&<div role="status" className="absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full bg-black/75 px-4 py-2 text-sm text-white">{busy}</div>}
      </div><aside className="w-56 shrink-0 border-l bg-white p-4"><h3 className="font-semibold">Edit image</h3><p className="mt-2 text-xs leading-5 text-slate-500">Select any object to move, resize, rotate, recolor or arrange it. Double-click text to type.</p><div className="mt-4 rounded-lg bg-violet-50 p-3 text-xs text-violet-800"><strong>Magic remover</strong><br/>Best for photos and diagrams with a mostly uniform outer background. It runs entirely on your device.</div></aside></div>
  </div>
}
