// Ponte com o Python (pywebview js_api). Contrato em vault/web-bridge.md.
//
// Front -> Python: `await api.nome(args)` chama WebApi.nome no web_shell.py.
// Python -> front: `on("evento", fn)`; o Python chama window.__gf.emit(evento, dados).

type Handler = (payload: unknown) => void

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> }
    __gf: { emit: (event: string, payload: unknown) => void }
  }
}

const handlers = new Map<string, Set<Handler>>()

window.__gf = {
  emit(event, payload) {
    handlers.get(event)?.forEach((handler) => handler(payload))
  },
}

export function on(event: string, handler: Handler): () => void {
  if (!handlers.has(event)) handlers.set(event, new Set())
  handlers.get(event)!.add(handler)
  return () => handlers.get(event)?.delete(handler)
}

const ready: Promise<void> = new Promise((resolve) => {
  if (window.pywebview?.api) resolve()
  else window.addEventListener('pywebviewready', () => resolve(), { once: true })
})

/** Chama um método do WebApi (Python). Erros do Python viram exceção aqui. */
export async function call<T = unknown>(method: string, ...args: unknown[]): Promise<T> {
  await ready
  const fn = window.pywebview?.api?.[method]
  if (!fn) throw new Error(`WebApi.${method} não existe`)
  return (await fn(...args)) as T
}

export interface AppInfo {
  version: string
  language: string
  dev: boolean
}

export type CanvasRect = [x: number, y: number, width: number, height: number]
export type CanvasPoint = [x: number, y: number]
export type CanvasTextMode = 'off' | 'game' | 'xml' | 'short' | 'long'

export interface CanvasElement {
  index: number
  id: string
  parent: string | null
  kind: string
  ctrl_type: string | null
  geometry: CanvasRect
  texture: string | null
  uv: CanvasRect | null
  button_uvs: Record<string, CanvasRect>
  progress_offset: CanvasPoint | null
  visible: boolean
  text_props: Record<string, string>
  button: boolean
  texts: Record<CanvasTextMode, { value: string } | { sample: 'short' | 'long' }>
  sample_text: string
  sample_icon: [string, CanvasRect] | null
}

export interface CanvasDocument {
  elements: CanvasElement[]
  bounds: CanvasRect
  preview: {
    screen: CanvasRect
    root_on_screen: CanvasPoint
    offsets: CanvasPoint[]
    frame: CanvasRect | null
    content: CanvasRect | null
    drawn: CanvasRect | null
    background: string | null
  }
}

export const openCanvasDocument = (path: string, resolution?: CanvasPoint) =>
  call<CanvasDocument>('open_document', path, resolution ?? null)
export const canvasAssetBase = (path: string) => call<string>('asset_base', path)
export const canvasBackgroundBase = () => call<string>('canvas_background_base')
