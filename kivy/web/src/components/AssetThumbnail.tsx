import { useEffect, useState } from 'react'
import { blobRegistry } from '../engine/blobRegistry'

export function AssetThumbnail({ assetId, className = '' }: { assetId: string; className?: string }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    const blob = blobRegistry.get(assetId)
    if (!blob) return
    const next = URL.createObjectURL(blob)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [assetId])
  return url ? <img src={url} alt="" draggable={false} className={`h-full w-full object-cover ${className}`} /> : <div className={`grid h-full w-full place-items-center bg-slate-100 text-xl text-slate-400 ${className}`}>✦</div>
}
