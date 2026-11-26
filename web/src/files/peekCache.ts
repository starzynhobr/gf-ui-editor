// Dados do cartão de prévia da lista de Texturas, com cache: cada textura é decodificada uma vez
// (TextureCache do canvas, só importado) e guardada como miniatura pequena. O bitmap grande é
// descartado logo, para passar o mouse em muitas texturas não encher a memória.
import { canvasAssetBase, on } from '../bridge'
import { TextureCache } from '../canvas/dds/cache'
import HeaderWorker from './headerWorker?worker&inline'
import type { TextureHeader } from './textureHeader'

export const THUMB_WIDTH = 232
export const THUMB_HEIGHT = 168
const MAX_ENTRIES = 160

export interface TexturePeekData {
  thumb: ImageBitmap | null
  width: number
  height: number
  format: string
}

type Pending = Map<number, (header: TextureHeader | null) => void>

const bases = new Map<string, Promise<string>>()
const entries = new Map<string, Promise<TexturePeekData | null>>()
const ready = new Map<string, TexturePeekData>() // caminho completo → dados já prontos
const workers = new Map<string, { worker: Worker; pending: Pending }>()
let textures: TextureCache | null = null
let nextId = 0
let unsubscribe: (() => void) | null = null

const folderOf = (path: string) => path.replace(/[\\/][^\\/]*$/, '').toLowerCase()
export const fileName = (path: string) => path.replace(/^.*[\\/]/, '')
const keyOf = (base: string, name: string) => `${base}|${name.toLowerCase()}`

function baseFor(path: string): Promise<string> {
  const folder = folderOf(path)
  let base = bases.get(folder)
  if (!base) {
    // asset_base usa a pasta do arquivo pedido (a da UI do projeto, com as camadas).
    base = canvasAssetBase(path)
    base.catch(() => bases.delete(folder))
    bases.set(folder, base)
  }
  return base
}

function watchChanges() {
  if (unsubscribe) return
  unsubscribe = on('canvas_textures_changed', (payload) => {
    const { base, names } = payload as { base: string; names: string[] }
    for (const name of names) forget(base, name)
  })
}

function forget(base: string, name: string) {
  const key = keyOf(base, name)
  const entry = entries.get(key)
  if (!entry) return
  entries.delete(key)
  void entry.then((data) => {
    if (!data) return
    for (const [path, value] of ready) if (value === data) ready.delete(path)
    data.thumb?.close()
  })
}

function headerFor(base: string, name: string): Promise<TextureHeader | null> {
  let entry = workers.get(base)
  if (!entry) {
    // Como o do canvas: o worker nasce depois de o host da pasta existir.
    const worker = new HeaderWorker()
    const pending: Pending = new Map()
    worker.onmessage = ({ data }) => {
      pending.get(data.id)?.(data.header ?? null)
      pending.delete(data.id)
    }
    worker.onerror = () => {
      for (const resolve of pending.values()) resolve(null)
      pending.clear()
      worker.terminate()
      workers.delete(base)
    }
    entry = { worker, pending }
    workers.set(base, entry)
  }
  const { worker, pending } = entry
  return new Promise((resolve) => {
    const id = nextId++
    pending.set(id, resolve)
    worker.postMessage({ id, url: new URL(encodeURIComponent(name.toLowerCase()), base).href, name })
  })
}

async function thumbnail(base: string, name: string): Promise<{ thumb: ImageBitmap | null; width: number; height: number }> {
  textures ??= new TextureCache()
  const bitmap = await textures.load(base, name, name.toLowerCase().endsWith('.dds'))
  // A miniatura fica no nosso cache; o original sai do TextureCache e da memória.
  textures.invalidate(base, name)
  if (!bitmap) return { thumb: null, width: 0, height: 0 }
  const { width, height } = bitmap
  const scale = Math.min(1, THUMB_WIDTH / width, THUMB_HEIGHT / height)
  try {
    const thumb = scale === 1
      ? bitmap
      : await createImageBitmap(bitmap, {
        resizeWidth: Math.max(1, Math.round(width * scale)),
        resizeHeight: Math.max(1, Math.round(height * scale)),
        resizeQuality: 'high',
      })
    if (thumb !== bitmap) bitmap.close()
    return { thumb, width, height }
  } catch {
    return { thumb: bitmap, width, height }
  }
}

/** Miniatura, dimensões e formato de uma textura (caminho completo). null: não deu para ler. */
export function loadTexturePeek(path: string): Promise<TexturePeekData | null> {
  const name = fileName(path)
  return baseFor(path).then((base) => {
    watchChanges()
    const key = keyOf(base, name)
    let entry = entries.get(key)
    if (!entry) {
      entry = Promise.all([thumbnail(base, name), headerFor(base, name)]).then(([image, header]) => {
        if (!image.thumb && !header) return null
        return {
          thumb: image.thumb,
          width: header?.width ?? image.width,
          height: header?.height ?? image.height,
          format: header?.format ?? fileName(name).replace(/^.*\./, '').toUpperCase(),
        }
      })
      entry.then((data) => {
        if (!data) entries.delete(key)
        else if (entries.get(key) === entry) ready.set(path.toLowerCase(), data)
      }, () => entries.delete(key))
      entries.set(key, entry)
      while (entries.size > MAX_ENTRIES) {
        const oldest = entries.keys().next().value as string
        const [oldBase, oldName] = oldest.split('|')
        forget(oldBase, oldName)
      }
    } else {
      // Mais recente no fim (o mais antigo sai primeiro).
      entries.delete(key)
      entries.set(key, entry)
    }
    return entry
  }).catch(() => null)
}

/** Já carregada? O cartão mostra na hora, sem passar por "Carregando…". */
export function cachedPeek(path: string): TexturePeekData | undefined {
  return ready.get(path.toLowerCase())
}
