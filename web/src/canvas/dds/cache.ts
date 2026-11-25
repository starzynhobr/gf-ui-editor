import DdsWorker from './worker?worker&inline'

type BitmapRequest = (bitmap: ImageBitmap | null) => void

export class TextureCache {
  private workers = new Map<string, { worker: Worker; pending: Map<number, BitmapRequest> }>()
  private files = new Map<string, Promise<ImageBitmap | null>>()
  private nextId = 0

  load(base: string, name: string, dds = true): Promise<ImageBitmap | null> {
    // TextureCache in the classic editor looks up file names in the XML directory.
    if (!name || /[/\\]/.test(name) || name === '.' || name === '..') return Promise.resolve(null)
    const url = this.url(base, name)
    let result = this.files.get(url)
    if (!result) {
      const { worker, pending } = this.workerFor(base)
      result = new Promise((resolve) => {
        const id = this.nextId++
        pending.set(id, resolve)
        worker.postMessage({ id, url, dds })
      })
      this.files.set(url, result)
    }
    return result
  }

  invalidate(base: string, name: string) {
    this.files.delete(this.url(base, name))
  }

  dispose() {
    for (const { worker, pending } of this.workers.values()) {
      worker.terminate()
      for (const resolve of pending.values()) resolve(null)
    }
    this.workers.clear()
    for (const result of this.files.values()) void result.then((bitmap) => bitmap?.close())
    this.files.clear()
  }

  private workerFor(base: string) {
    const existing = this.workers.get(base)
    if (existing) return existing
    // In WebView2 the worker must start after its host has been mapped. A later
    // host mapping is unavailable to a worker that is already running.
    const worker = new DdsWorker()
    const pending = new Map<number, BitmapRequest>()
    worker.onmessage = ({ data }) => {
      const resolve = pending.get(data.id)
      if (resolve) resolve(data.bitmap ?? null)
      else data.bitmap?.close()
      pending.delete(data.id)
    }
    worker.onerror = () => {
      for (const resolve of pending.values()) resolve(null)
      pending.clear()
      worker.terminate()
      this.workers.delete(base)
    }
    const entry = { worker, pending }
    this.workers.set(base, entry)
    return entry
  }

  private url(base: string, name: string) {
    return new URL(encodeURIComponent(name.toLowerCase()), base).href
  }
}
