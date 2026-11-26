// Lê só o começo de um .dds/.tga. Fica num worker pelo mesmo motivo do decodificador do canvas:
// o WebView2 recusa os hosts de assets em fetch da página, mas aceita de um worker dedicado.
import { HEADER_BYTES, describeTexture } from './textureHeader'

const worker = self as unknown as {
  onmessage: (event: MessageEvent<{ id: number; url: string; name: string }>) => void
  postMessage: (message: object) => void
}

async function head(url: string): Promise<Uint8Array> {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const reader = response.body?.getReader()
  if (!reader) return new Uint8Array(await response.arrayBuffer())
  const chunks: Uint8Array[] = []
  let size = 0
  while (size < HEADER_BYTES) {
    const { done, value } = await reader.read()
    if (done || !value) break
    chunks.push(value)
    size += value.byteLength
  }
  void reader.cancel().catch(() => undefined)
  const bytes = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    bytes.set(chunk, offset)
    offset += chunk.byteLength
  }
  return bytes
}

worker.onmessage = async ({ data }) => {
  const { id, url, name } = data
  try {
    worker.postMessage({ id, header: describeTexture(await head(url), name) })
  } catch {
    worker.postMessage({ id, header: null })
  }
}
