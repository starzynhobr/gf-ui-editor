import { decodeDds } from '../web/src/canvas/dds/decode'

self.onmessage = async ({ data: files }: MessageEvent<[base: string, file: string][]>) => {
  try {
    const hashes = []
    for (const [base, name] of files) {
      const response = await fetch(new URL(encodeURIComponent(name), base))
        .catch((error) => { throw new Error(`${base}${name}: ${error}`) })
      if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`)
      const { rgba } = decodeDds(await response.arrayBuffer())
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', rgba))
      hashes.push(Array.from(digest, (byte) => byte.toString(16).padStart(2, '0')).join(''))
    }
    self.postMessage({ hashes })
  } catch (error) {
    self.postMessage({ error: String(error) })
  }
}
