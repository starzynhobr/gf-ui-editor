import { decodeDds } from './decode'
import { decodeTga } from './tga'

const worker = self as unknown as {
  onmessage: (event: MessageEvent<{ id: number; url: string; dds: boolean }>) => void
  postMessage: (message: object, transfer?: Transferable[]) => void
}

worker.onmessage = async ({ data }) => {
  const { id, url, dds } = data
  try {
    // WebView2's file:// document rejects the dynamic hosts in page fetch and
    // image requests, but allows them from this inline dedicated worker.
    const response = await fetch(url, { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    let image: Blob | ImageData
    if (dds) {
      const { rgba, width, height } = decodeDds(await response.arrayBuffer())
      image = new ImageData(rgba, width, height)
    } else if (url.toLowerCase().endsWith('.tga')) {
      const { rgba, width, height } = decodeTga(await response.arrayBuffer())
      image = new ImageData(rgba, width, height)
    } else {
      image = await response.blob()
    }
    const bitmap = await createImageBitmap(image)
    worker.postMessage({ id, bitmap }, [bitmap])
  } catch (error) {
    worker.postMessage({ id, error: String(error) })
  }
}
