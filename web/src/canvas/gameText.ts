const font = '11px Arial'
const lineHeight = 12
const margin = 2
const cachePixels = 4 * 1024 * 1024
const cacheEntries = 2048
// Arial's hinted Qt advances at 11 px where rounding Canvas metrics differs.
const hintedAdvances: Record<string, number> = {
  '!': 2, A: 8, C: 7, D: 7, E: 6, F: 6, G: 8, H: 7, I: 2, J: 5,
  M: 8, N: 7, O: 8, P: 6, Q: 8, R: 7, T: 6, U: 7, V: 8, Y: 8,
  f: 4, k: 5, m: 8, w: 10, '|': 2,
}

interface Raster {
  image: HTMLCanvasElement
  left: number
  top: number
}

const rasters = new Map<string, Raster>()
let pixels = 0

function wrap(text: string, width: number, measure: (line: string) => number) {
  const lines: string[] = []
  for (const paragraph of text.split(/\r?\n/)) {
    let line = ''
    for (const word of paragraph.split(/\s+/)) {
      const candidate = line ? `${line} ${word}` : word
      if (line && measure(candidate) > width) {
        lines.push(line)
        line = word
      } else {
        line = candidate
      }
    }
    lines.push(line)
  }
  return lines
}

function rasterize(text: string, color: string, outline: boolean, multiline: boolean, align: string, width: number, height: number): Raster {
  const mask = document.createElement('canvas')
  const ctx = mask.getContext('2d', { willReadFrequently: true })!
  const setFont = () => {
    ctx.font = font
    ctx.letterSpacing = outline ? '1px' : '0px'
  }
  const glyphs = (line: string) => {
    // The classic font advances in whole game pixels. Keep contextual shaping
    // for scripts where individual glyphs cannot be positioned independently.
    const latin = /^[\u0020-\u024f]*$/.test(line)
    const parts = latin ? [...line] : [line]
    let pen = 0
    return parts.map((part) => {
      const metrics = ctx.measureText(part)
      const x = pen
      pen += (latin && part in hintedAdvances)
        ? hintedAdvances[part] + Number(outline)
        : Math.round(metrics.width)
      return { part, x, metrics, end: pen }
    })
  }
  const measure = (line: string) => glyphs(line).at(-1)?.end ?? 0
  setFont()
  const lines = multiline ? wrap(text, width, measure) : text.split(/\r?\n/)
  const firstBaseline = (multiline ? 0 : Math.trunc((height - lines.length * lineHeight) / 2)) + 10
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity
  const positioned = lines.flatMap((line, i) => {
    const parts = glyphs(line)
    const advance = parts.at(-1)?.end ?? 0
    const offset = Math.floor(align === '1' ? (width - advance) / 2 : align === '2' ? width - advance : 0)
    const y = firstBaseline + i * lineHeight
    return parts.map(({ part, x, metrics }) => {
      x += offset
      left = Math.min(left, x - metrics.actualBoundingBoxLeft)
      top = Math.min(top, y - metrics.actualBoundingBoxAscent)
      right = Math.max(right, x + metrics.actualBoundingBoxRight)
      bottom = Math.max(bottom, y + metrics.actualBoundingBoxDescent)
      return { part, x, y }
    })
  })
  if (!positioned.length) return { image: mask, left: 0, top: 0 }
  left = Math.floor(left) - margin
  top = Math.floor(top) - margin
  mask.width = Math.ceil(right) + margin - left
  mask.height = Math.ceil(bottom) + margin - top
  setFont()
  // Chromium positions Arial coverage slightly to the right of Qt's bitmap.
  for (const { part, x, y } of positioned) ctx.fillText(part, x - left - .75, y - top)

  // GameTextItem uses monochrome glyphs. Build the outline from the same
  // pixels as the fill so zoom cannot reposition the individual copies.
  const data = ctx.getImageData(0, 0, mask.width, mask.height)
  for (let alpha = 3; alpha < data.data.length; alpha += 4) {
    data.data[alpha] = data.data[alpha] >= 144 ? 255 : 0
  }
  ctx.putImageData(data, 0, 0)

  const image = document.createElement('canvas')
  image.width = mask.width
  image.height = mask.height
  const paint = image.getContext('2d')!
  if (outline) {
    for (const dx of [-1, 0, 1]) {
      for (const dy of [-1, 0, 1]) {
        if (dx || dy) paint.drawImage(mask, dx, dy)
      }
    }
  }
  ctx.globalCompositeOperation = 'source-in'
  ctx.fillStyle = color
  ctx.fillRect(0, 0, mask.width, mask.height)
  paint.drawImage(mask, 0, 0)
  return { image, left, top }
}

export function drawGameText(
  ctx: CanvasRenderingContext2D, text: string, color: string, outline: boolean, multiline: boolean, align: string,
  x: number, y: number, width: number, height: number,
) {
  const key = JSON.stringify([text, font, color, outline, multiline, align, width, height])
  let raster = rasters.get(key)
  if (raster) rasters.delete(key)
  else {
    raster = rasterize(text, color, outline, multiline, align, width, height)
    pixels += raster.image.width * raster.image.height
  }
  rasters.set(key, raster)
  while (rasters.size > cacheEntries || pixels > cachePixels) {
    const [oldKey, { image }] = rasters.entries().next().value!
    pixels -= image.width * image.height
    rasters.delete(oldKey)
  }
  ctx.drawImage(raster.image, x + raster.left, y + raster.top)
}
