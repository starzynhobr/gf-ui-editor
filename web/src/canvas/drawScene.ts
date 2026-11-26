import type { CanvasDocument, CanvasElement, CanvasRect, CanvasTextMode } from '../bridge'
import type { Handle } from './geometry'

export interface SceneOptions {
  outlines: boolean
  labels: boolean
  preview: boolean
  sample: boolean
  text: CanvasTextMode
  short: string
  long: string
  buttonState?: string
}

type Images = ReadonlyMap<string, ImageBitmap | null>
type Rows = ReturnType<typeof sceneRows>

export const canvasBackground = '#0d0f13'

export function sceneRows(document: CanvasDocument, preview: boolean) {
  return document.elements.map((element) => {
    const [x, y, w, h] = element.geometry
    const [dx, dy] = preview ? document.preview.offsets[element.index] : [0, 0]
    const textureBox: CanvasRect = [x + dx, y + dy, Math.max(1, w), Math.max(1, h)]
    const box = (preview && element.index === 0 && document.preview.content) || textureBox
    return { element, box, textureBox }
  })
}

function validUv(uv: CanvasRect | null | undefined): uv is CanvasRect {
  return !!uv && uv[2] > 0 && uv[3] > 0
}

function drawCrop(ctx: CanvasRenderingContext2D, image: ImageBitmap, uv: CanvasRect, box: CanvasRect) {
  // Canvas clips out-of-bounds source pixels proportionally; Pillow pads them with transparency.
  ctx.drawImage(image, ...uv, ...box)
}

export function drawsRootTexture(element: CanvasElement | undefined, images: Images) {
  if (!element?.texture || !validUv(element.uv)) return false
  const image = images.get(element.texture.toLowerCase())
  if (!image) return false
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 16
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  ctx.imageSmoothingEnabled = false
  drawCrop(ctx, image, element.uv, [0, 0, 16, 16])
  return ctx.getImageData(0, 0, 16, 16).data.some((value, index) => index % 4 === 3 && value > 8)
}

// Keep the Qt/Pillow operation order: composite at UV size and resize to layout size
// before applying the view's zoom. Weak keys release the prepared cuts with their atlas.
const cuts = new WeakMap<ImageBitmap, Map<string, HTMLCanvasElement>>()

function drawTexture(
  ctx: CanvasRenderingContext2D, element: CanvasElement, box: CanvasRect, images: Images,
  sample: boolean, state?: string,
) {
  if (sample && element.sample_icon) {
    const [name, uv] = element.sample_icon
    const image = images.get(name.toLowerCase())
    if (image) {
      drawCrop(ctx, image, uv, box)
      return
    }
  }
  const atlas = element.texture && images.get(element.texture.toLowerCase())
  if (!atlas) return
  const uv = (state && element.button_uvs[state]) || element.uv
  const progress = element.progress_offset
  const thumb = element.geometry[2] && element.geometry[3] ? element.button_uvs.ThumbUV : null
  const [x, y, width, height] = box
  if (!validUv(uv) && !validUv(thumb)) return
  if (!validUv(thumb) && validUv(uv) && !progress && uv[2] === width && uv[3] === height) {
    drawCrop(ctx, atlas, uv, box)
    return
  }
  const key = JSON.stringify([uv, progress, thumb, width, height])
  let variants = cuts.get(atlas)
  if (!variants) cuts.set(atlas, variants = new Map())
  let cut = variants.get(key)
  if (!cut) {
    cut = document.createElement('canvas')
    cut.width = width
    cut.height = height
    const canvas = cut.getContext('2d')!
    canvas.imageSmoothingEnabled = false
    const dest: CanvasRect = [0, 0, width, height]
    if (validUv(uv)) {
      if (progress && !thumb) {
        const composited = document.createElement('canvas')
        const source: CanvasRect = [0, 0, uv[2], uv[3]]
        composited.width = source[2]
        composited.height = source[3]
        const paint = composited.getContext('2d')!
        drawCrop(paint, atlas, uv, source)
        drawCrop(paint, atlas, [uv[0] + progress[0], uv[1] + progress[1], uv[2], uv[3]], source)
        canvas.drawImage(composited, ...dest)
      } else {
        drawCrop(canvas, atlas, uv, dest)
      }
    }
    if (validUv(thumb)) {
      const thumbBox: CanvasRect = height >= width
        ? [0, 0, width, Math.min(Math.max(24, thumb[3]), height)]
        : [0, 0, Math.min(Math.max(24, thumb[2]), width), height]
      drawCrop(canvas, atlas, thumb, thumbBox)
    }
    variants.set(key, cut)
  }
  ctx.drawImage(cut, x, y)
}

function drawText(ctx: CanvasRenderingContext2D, element: CanvasElement, box: CanvasRect, options: SceneOptions) {
  const entry = element.texts[options.text]
  const text = (options.sample && element.sample_text) || ('value' in entry ? entry.value : options[entry.sample])
  if (!text) return
  const props = element.text_props
  const outline = props.FontStyle === '1'
  const multiline = props.MultiLine === '1'
  const align = element.button ? '1' : props.TextAlign
  const [x, y, width, height] = box
  ctx.font = '11px Arial'
  ctx.letterSpacing = outline ? '1px' : '0px'
  ctx.textBaseline = 'alphabetic'
  ctx.textAlign = align === '1' ? 'center' : align === '2' ? 'right' : 'left'
  const tx = x + (align === '1' ? width / 2 : align === '2' ? width : 0)
  let ty = y + (multiline ? 10 : Math.floor((height - 13) / 2) + 10)
  const number = Number(props.FontColor ?? 0xffffff)
  const bgr = Number.isInteger(number) ? number : 0xffffff
  const color = `rgb(${bgr & 255},${(bgr >> 8) & 255},${(bgr >> 16) & 255})`
  const lines: string[] = []
  for (const paragraph of text.split(/\r?\n/)) {
    if (!multiline) {
      lines.push(paragraph)
      continue
    }
    let line = ''
    for (const word of paragraph.split(/\s+/)) {
      const candidate = line ? `${line} ${word}` : word
      if (line && ctx.measureText(candidate).width > width) {
        lines.push(line)
        line = word
      } else {
        line = candidate
      }
    }
    lines.push(line)
  }
  for (const line of lines) {
    if (outline) {
      ctx.fillStyle = '#000'
      for (const dx of [-1, 0, 1]) {
        for (const dy of [-1, 0, 1]) {
          if (dx || dy) ctx.fillText(line, tx + dx, ty + dy)
        }
      }
    }
    ctx.fillStyle = color
    ctx.fillText(line, tx, ty)
    ty += 13
  }
}

export function drawDots(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.fillStyle = canvasBackground
  ctx.fillRect(0, 0, width, height)
  // A cosmetic 1.4 px Qt point centered on integer coordinates covers four pixels.
  ctx.fillStyle = '#181a21'
  for (let x = 7; x < width; x += 16) {
    for (let y = 7; y < height; y += 16) ctx.fillRect(x, y, 2, 2)
  }
}

export function drawScene(
  ctx: CanvasRenderingContext2D, document: CanvasDocument, rows: Rows, images: Images,
  options: SceneOptions, background: ImageBitmap | null, scale: number, selected: number | null,
  selection = selected === null ? [] : [selected], handles: Handle[] = [],
  marquee: CanvasRect | null = null, ghost: CanvasRect | null = null, ghostLabel = '',
) {
  ctx.save()
  const { preview } = document
  const camera = ctx.getTransform()
  const left = -camera.e / camera.a
  const top = -camera.f / camera.d
  const right = left + ctx.canvas.width / camera.a
  const bottom = top + ctx.canvas.height / camera.d
  const inView = ([x, y, width, height]: CanvasRect) =>
    x <= right && x + width >= left && y <= bottom && y + height >= top
  if (options.preview) {
    const [x, y, width, height] = preview.screen
    ctx.fillStyle = canvasBackground
    ctx.fillRect(x, y, width, height)
    if (background) {
      const ratio = Math.max(width / background.width, height / background.height)
      const w = background.width * ratio
      const h = background.height * ratio
      ctx.save()
      ctx.beginPath()
      ctx.rect(x, y, width, height)
      ctx.clip()
      ctx.imageSmoothingEnabled = true
      ctx.drawImage(background, x + (width - w) / 2, y + (height - h) / 2, w, h)
      ctx.restore()
    }
    ctx.lineWidth = 1 / scale
    ctx.strokeStyle = '#7c8799'
    ctx.strokeRect(x, y, width, height)
    ctx.font = `${12 / scale}px Arial`
    ctx.fillStyle = '#7c8799'
    ctx.fillText(`${width} × ${height}`, x, y + height + 15 / scale)
  }
  ctx.imageSmoothingEnabled = false
  for (const { element, textureBox, box } of rows) {
    // Like Qt, inspect all XML controls, including ones whose Visible flag starts at 0.
    if (options.outlines && inView(box)) {
      ctx.fillStyle = 'rgba(40,150,220,0.03137)'
      ctx.fillRect(...box)
      ctx.strokeStyle = 'rgba(90,190,255,0.43137)'
      ctx.lineWidth = 1 / scale
      ctx.setLineDash([4 / scale, 2 / scale])
      ctx.strokeRect(...box)
      ctx.setLineDash([])
    }
    if (inView(textureBox)) {
      drawTexture(ctx, element, textureBox, images, options.sample, element.index === selected ? options.buttonState : undefined)
    }
    if (options.labels) {
      ctx.font = `${12 / scale}px Arial`
      ctx.fillStyle = '#ffeb78'
      ctx.fillText(`${element.id} · ${element.ctrl_type ?? element.kind}`, box[0] + 2 / scale, box[1] + 12 / scale)
    }
  }
  if (options.preview && options.sample && preview.drawn) {
    ctx.lineWidth = 1 / scale
    ctx.strokeStyle = '#41dcff'
    ctx.setLineDash([4 / scale, 2 / scale])
    ctx.strokeRect(...preview.drawn)
    ctx.setLineDash([])
  }
  for (const { element, box } of rows) drawText(ctx, element, box, options)
  if (ghost) {
    ctx.fillStyle = 'rgba(246,142,76,0.15)'
    ctx.fillRect(...ghost)
    ctx.strokeStyle = '#f68e4c'
    ctx.lineWidth = 1 / scale
    ctx.setLineDash([4 / scale, 2 / scale])
    ctx.strokeRect(...ghost)
    ctx.setLineDash([])
    ctx.font = `${12 / scale}px Arial`
    ctx.fillStyle = '#f68e4c'
    ctx.fillText(ghostLabel, ghost[0] + 3 / scale, ghost[1] + 13 / scale)
  }
  const marked = new Set(selection)
  for (const { element, box } of rows) {
    if (!marked.has(element.index)) continue
    ctx.lineWidth = 2 / scale
    ctx.strokeStyle = '#ffbe1e'
    ctx.strokeRect(...box)
    if (options.preview && element.index === 0 && preview.frame) ctx.strokeRect(...preview.frame)
  }
  for (const { point: [x, y] } of handles) {
    ctx.fillStyle = '#ffbe1e'
    const radius = 5 / scale
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2)
  }
  if (marquee) {
    ctx.fillStyle = 'rgba(90,190,255,0.16)'
    ctx.strokeStyle = '#5abeff'
    ctx.lineWidth = 1 / scale
    ctx.fillRect(...marquee)
    ctx.strokeRect(...marquee)
  }
  ctx.restore()
}
