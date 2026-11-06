/**
 * Creates UUID-shaped stable IDs in both secure and insecure browser contexts.
 * `crypto.randomUUID()` is unavailable on some browsers when the editor is
 * opened through a plain-HTTP LAN address, while `getRandomValues()` is more
 * widely available. The final fallback keeps the editor usable on older WebViews.
 */
export function createId(): string {
  const cryptoApi=globalThis.crypto
  if(typeof cryptoApi?.randomUUID==='function')return cryptoApi.randomUUID()

  const bytes=new Uint8Array(16)
  if(typeof cryptoApi?.getRandomValues==='function')cryptoApi.getRandomValues(bytes)
  else for(let index=0;index<bytes.length;index++)bytes[index]=Math.floor(Math.random()*256)

  bytes[6]=(bytes[6]&0x0f)|0x40
  bytes[8]=(bytes[8]&0x3f)|0x80
  const hex=Array.from(bytes,value=>value.toString(16).padStart(2,'0'))
  return `${hex.slice(0,4).join('')}-${hex.slice(4,6).join('')}-${hex.slice(6,8).join('')}-${hex.slice(8,10).join('')}-${hex.slice(10).join('')}`
}
