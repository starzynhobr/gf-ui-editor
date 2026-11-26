import { useEffect, useState } from 'react'
import { canvasAssetBase, on } from '../bridge'
import { TextureCache } from '../canvas/dds/cache'

export function useAtlasTexture(path: string, name: string) {
  const [bitmap, setBitmap] = useState<ImageBitmap | null>()
  useEffect(() => {
    if (!name) return
    const cache = new TextureCache()
    let active = true
    let revision = 0
    const start = async () => {
      const base = await canvasAssetBase(path)
      if (!active) return
      const load = async () => {
        const request = ++revision
        const image = await cache.load(base, name, name.toLowerCase().endsWith('.dds'))
        if (active && request === revision) setBitmap(image)
      }
      unsubscribe = on('canvas_textures_changed', (payload) => {
        const changed = payload as { base: string; names: string[] }
        if (changed.base === base && changed.names.includes(name.toLowerCase())) {
          cache.invalidate(base, name)
          void load()
        }
      })
      await load()
    }
    let unsubscribe: (() => void) | undefined
    void start().catch(() => { if (active) setBitmap(null) })
    return () => {
      active = false
      unsubscribe?.()
      cache.dispose()
    }
  }, [path, name])
  return bitmap
}
