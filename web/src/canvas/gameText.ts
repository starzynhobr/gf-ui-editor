import { useEffect, useState } from 'react'
import { call } from '../bridge'

export type TextRequest = [
  text: string, color: string, outline: boolean, multiline: boolean, align: string, width: number, height: number,
]

interface Raster {
  image: HTMLImageElement
  left: number
  top: number
}

export type TextMasks = ReadonlyMap<string, Raster>
type EncodedRaster = [left: number, top: number, png: string]

const cacheEntries = 2048
const rasters = new Map<string, Promise<Raster>>()
const emptyMasks: TextMasks = new Map()

async function decode([left, top, png]: EncodedRaster): Promise<Raster> {
  const image = new Image()
  image.src = `data:image/png;base64,${png}`
  await image.decode()
  return { image, left, top }
}

export async function loadTextMasks(requests: ReadonlyMap<string, TextRequest>): Promise<TextMasks> {
  const missing = [...requests].filter(([key]) => !rasters.has(key))
  if (missing.length) {
    const batch = call<EncodedRaster[]>('canvas_text_masks', missing.map(([, request]) => request))
    missing.forEach(([key], index) => {
      const raster = batch.then((response) => decode(response[index]))
      rasters.set(key, raster)
      void raster.catch(() => { if (rasters.get(key) === raster) rasters.delete(key) })
    })
  }
  const result = Promise.all([...requests.keys()].map(async (key) => {
    const raster = rasters.get(key)!
    rasters.delete(key)
    rasters.set(key, raster)
    return [key, await raster] as const
  }))
  while (rasters.size > cacheEntries) rasters.delete(rasters.keys().next().value!)
  return new Map(await result)
}

export function useGameTextMasks(requests: ReadonlyMap<string, TextRequest>) {
  const [result, setResult] = useState<{ requests: typeof requests; masks: TextMasks; error?: string }>()
  useEffect(() => {
    if (!requests.size) return
    let active = true
    void loadTextMasks(requests).then(
      (masks) => { if (active) setResult({ requests, masks }) },
      (error) => { if (active) setResult({ requests, masks: emptyMasks, error: String(error) }) },
    )
    return () => { active = false }
  }, [requests])
  return {
    masks: result?.masks ?? emptyMasks,
    loading: requests.size > 0 && result?.requests !== requests,
    error: result?.requests === requests ? result.error : undefined,
  }
}

export function drawGameText(ctx: CanvasRenderingContext2D, masks: TextMasks, request: TextRequest, x: number, y: number) {
  const raster = masks.get(JSON.stringify(request))
  if (raster) ctx.drawImage(raster.image, x + raster.left, y + raster.top)
}
