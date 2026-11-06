import { afterEach, describe, expect, it, vi } from 'vitest'
import { createId } from './id'

describe('createId',()=>{
  afterEach(()=>vi.unstubAllGlobals())

  it('works when randomUUID is unavailable on a plain-HTTP LAN origin',()=>{
    vi.stubGlobal('crypto',{getRandomValues:(bytes:Uint8Array)=>bytes.fill(7)})
    expect(createId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })

  it('still works in an older WebView without Web Crypto',()=>{
    vi.stubGlobal('crypto',undefined)
    expect(createId()).toMatch(/^[0-9a-f-]{36}$/)
  })
})
