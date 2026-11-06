export type OpenMediaKind = 'image' | 'audio' | 'sketch'

export interface OpenMediaResult {
  id: string
  kind: OpenMediaKind
  title: string
  url: string
  thumbnail?: string
  creator?: string
  license?: string
  licenseUrl?: string
  sourceUrl?: string
  provider: 'Wikimedia Commons' | 'Openverse'
}

type CommonsPage = {
  pageid: number
  title: string
  canonicalurl?: string
  imageinfo?: Array<{
    url: string
    thumburl?: string
    mime?: string
    descriptionurl?: string
    extmetadata?: Record<string, { value?: string }>
  }>
}

const stripHtml = (value = '') => {
  const element = document.createElement('div')
  element.innerHTML = value
  return element.textContent?.trim() || ''
}

function commonsQuery(query: string, kind: OpenMediaKind) {
  const typeHint = kind === 'audio' ? 'filetype:audio' : kind === 'sketch' ? '(sketch OR "line art" OR drawing OR illustration)' : ''
  return [query.trim(), typeHint].filter(Boolean).join(' ')
}

export async function searchCommons(query: string, kind: OpenMediaKind, limit = 40): Promise<OpenMediaResult[]> {
  const params = new URLSearchParams({
    action: 'query', format: 'json', formatversion: '2', origin: '*',
    generator: 'search', gsrsearch: commonsQuery(query, kind), gsrnamespace: '6', gsrlimit: String(limit),
    prop: 'imageinfo|info', inprop: 'url', iiprop: 'url|mime|extmetadata', iiurlwidth: '420',
  })
  const response = await fetch(`/commons/w/api.php?${params}`)
  if (!response.ok) throw new Error(`Commons search failed (${response.status})`)
  const payload = await response.json() as { query?: { pages?: CommonsPage[] } }
  return (payload.query?.pages ?? []).flatMap((page): OpenMediaResult[] => {
    const info = page.imageinfo?.[0]
    if (!info?.url) return []
    const mime = info.mime ?? ''
    if (kind === 'audio' && !mime.startsWith('audio/')) return []
    if (kind !== 'audio' && !mime.startsWith('image/')) return []
    const meta = info.extmetadata ?? {}
    return [{
      id: `commons-${page.pageid}`,
      kind,
      title: page.title.replace(/^File:/, ''),
      url: info.url,
      thumbnail: info.thumburl ?? (kind === 'audio' ? undefined : info.url),
      creator: stripHtml(meta.Artist?.value || meta.Credit?.value),
      license: stripHtml(meta.LicenseShortName?.value || meta.UsageTerms?.value) || 'See source',
      licenseUrl: meta.LicenseUrl?.value,
      sourceUrl: info.descriptionurl ?? page.canonicalurl,
      provider: 'Wikimedia Commons',
    }]
  })
}

async function searchOpenverse(query: string, kind: 'image' | 'audio', limit = 40): Promise<OpenMediaResult[]> {
  const params = new URLSearchParams({ q: query, page_size: String(limit), license_type: 'commercial,modification', mature: 'false' })
  const response = await fetch(`/openverse/v1/${kind === 'image' ? 'images' : 'audio'}/?${params}`)
  if (!response.ok) throw new Error(`Openverse search failed (${response.status})`)
  const payload = await response.json() as { results?: Array<{ id: string; title: string; url: string; thumbnail?: string; creator?: string; license?: string; license_url?: string; foreign_landing_url?: string }> }
  return (payload.results ?? []).filter((item) => item.url).map((item) => ({
    id: `openverse-${item.id}`, kind, title: item.title || 'Untitled', url: item.url,
    thumbnail: item.thumbnail, creator: item.creator, license: item.license,
    licenseUrl: item.license_url, sourceUrl: item.foreign_landing_url, provider: 'Openverse',
  }))
}

export async function searchOpenMedia(query: string, kind: OpenMediaKind, limit = 40): Promise<{ results: OpenMediaResult[]; notice?: string }> {
  if (!query.trim()) return { results: [] }
  if (kind === 'sketch') {
    const results = await searchCommons(query, kind, limit)
    return { results, notice: 'Sketches come from Wikimedia Commons. Check each item’s license before publishing.' }
  }
  const attempts = await Promise.allSettled([
    searchCommons(query, kind, limit),
    searchOpenverse(query, kind, limit),
  ])
  const merged = attempts.flatMap((attempt) => attempt.status === 'fulfilled' ? attempt.value : [])
  const unique = [...new Map(merged.map((item) => [item.url, item])).values()].slice(0, limit)
  if (unique.length) return { results: unique, notice: attempts.some((attempt) => attempt.status === 'rejected') ? 'One catalog was unavailable; showing results from the other open catalog.' : undefined }
  throw new Error('Open media search is temporarily unavailable. Your uploaded media still works offline.')
}
