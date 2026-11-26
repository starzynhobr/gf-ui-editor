import type { CanvasDocument, CanvasElement, CanvasRect, CanvasTextMode } from '../bridge'
import { kindLabel, gameColorToHex } from '../elements/kinds'
import { drawGameText } from './gameText'
import type { Handle } from './geometry'
import type { CanvasPalette } from './palette'

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

function drawText(ctx: CanvasRenderingContext2D, element: CanvasElement, box: CanvasRect, options: SceneOptions, fallback = '') {
  const entry = element.texts[options.text]
  const text = (options.sample && element.sample_text) || ('value' in entry ? entry.value : options[entry.sample]) || fallback
  if (!text) return
  const props = element.text_props
  drawGameText(ctx, text, gameColorToHex(props.FontColor), props.FontStyle === '1', props.MultiLine === '1',
    element.button ? '1' : props.TextAlign ?? '0', ...box)
}

export function drawDots(ctx: CanvasRenderingContext2D, width: number, height: number, palette: CanvasPalette) {
  ctx.fillStyle = palette.surface
  ctx.fillRect(0, 0, width, height)
  // A cosmetic 1.4 px Qt point centered on integer coordinates covers four pixels.
  ctx.fillStyle = palette.grid
  for (let x = 7; x < width; x += 16) {
    for (let y = 7; y < height; y += 16) ctx.fillRect(x, y, 2, 2)
  }
}

export function drawScreen(
  ctx: CanvasRenderingContext2D, screen: CanvasRect, background: ImageBitmap | null, scale: number,
  palette: CanvasPalette,
) {
  ctx.save()
  const [x, y, width, height] = screen
  ctx.fillStyle = palette.surface
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
  ctx.strokeStyle = palette.frame
  ctx.strokeRect(x, y, width, height)
  ctx.font = `${12 / scale}px Arial`
  ctx.fillStyle = palette.frame
  ctx.fillText(`${width} × ${height}`, x, y + height + 15 / scale)
  ctx.restore()
}

export function drawReferenceLayer(
  ctx: CanvasRenderingContext2D, document: CanvasDocument, images: Images, screen: CanvasRect, options: SceneOptions,
) {
  const rows = sceneRows(document, false).filter(({ element }) => element.visible)
  const [x, y] = document.preview.screen
  const layerOptions = { ...options, text: options.text === 'game' ? 'game' : 'off' } as const
  ctx.save()
  ctx.translate(screen[0] - x, screen[1] - y)
  ctx.imageSmoothingEnabled = false
  for (const { element, box } of rows) drawTexture(ctx, element, box, images, options.sample)
  for (const { element, box } of rows) drawText(ctx, element, box, layerOptions, element.layer_text)
  ctx.restore()
}

function drawLabels(
  ctx: CanvasRenderingContext2D, rows: Rows, selected: number | null, pixelRatio: number, palette: CanvasPalette,
) {
  const camera = ctx.getTransform()
  const project = (row: Rows[number]) => [
    Math.round((row.box[0] * camera.a + camera.e) / pixelRatio) + 2,
    Math.round((row.box[1] * camera.d + camera.f) / pixelRatio) + 1,
  ]
  const width = ctx.canvas.width / pixelRatio
  const height = ctx.canvas.height / pixelRatio
  ctx.save()
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  ctx.font = '12px Arial'
  ctx.textBaseline = 'top'
  ctx.lineJoin = 'round'
  ctx.lineWidth = 2
  ctx.strokeStyle = '#18150a'
  ctx.fillStyle = palette.label
  const occupied = new Set<number>()
  const columns = Math.ceil(width / 16)
  const primary = rows.find(({ element }) => element.index === selected)
  const ordered = primary ? [primary, ...rows.filter((row) => row !== primary)] : rows
  const labels: { label: string; x: number; y: number }[] = []
  for (const row of ordered) {
    const [x, y] = project(row)
    if (x < 0 || x >= width || y < 0 || y + 16 > height) continue
    const { id, kind, ctrl_type, texts } = row.element
    const text = ('value' in texts.game && texts.game.value) || ('value' in texts.xml && texts.xml.value) || ''
    const label = [id, kindLabel(kind, ctrl_type), text.trim().replace(/\s+/g, ' ')].filter(Boolean).join(' · ')
    const w = Math.min(width - x, Math.ceil(ctx.measureText(label).width) + 2)
    // Reserve screen-space cells so IDs on nearby elements don't overlap at small zooms.
    const cells: number[] = []
    for (let iy = Math.floor(y / 16); iy <= Math.floor((y + 15) / 16); iy++) {
      for (let ix = Math.floor(x / 16); ix <= Math.floor((x + w - 1) / 16); ix++) cells.push(iy * columns + ix)
    }
    if (cells.some((cell) => occupied.has(cell))) continue
    for (const cell of cells) occupied.add(cell)
    labels.push({ label, x, y })
  }
  for (const { label, x, y } of labels.reverse()) {
    ctx.strokeText(label, x, y)
    ctx.fillText(label, x, y)
  }
  ctx.restore()
}

export function drawScene(
  ctx: CanvasRenderingContext2D, document: CanvasDocument, rows: Rows, images: Images,
  options: SceneOptions, palette: CanvasPalette, pixelRatio: number, selected: number | null,
  selection: number[], handles: Handle[], marquee: CanvasRect | null, ghost: CanvasRect | null, ghostLabel: string,
) {
  ctx.save()
  const { preview } = document
  const camera = ctx.getTransform()
  const scale = camera.a / pixelRatio
  const left = -camera.e / camera.a
  const top = -camera.f / camera.d
  const right = left + ctx.canvas.width / camera.a
  const bottom = top + ctx.canvas.height / camera.d
  const inView = ([x, y, width, height]: CanvasRect) =>
    x <= right && x + width >= left && y <= bottom && y + height >= top
  ctx.imageSmoothingEnabled = false
  for (const { element, textureBox, box } of rows) {
    // Like Qt, inspect all XML controls, including ones whose Visible flag starts at 0.
    if (options.outlines && inView(box)) {
      ctx.fillStyle = palette.outline
      ctx.globalAlpha = .03137
      ctx.fillRect(...box)
      ctx.strokeStyle = palette.outline
      ctx.globalAlpha = .43137
      ctx.lineWidth = 1 / scale
      ctx.setLineDash([4 / scale, 2 / scale])
      ctx.strokeRect(...box)
      ctx.setLineDash([])
      ctx.globalAlpha = 1
    }
    if (inView(textureBox)) {
      drawTexture(ctx, element, textureBox, images, options.sample, element.index === selected ? options.buttonState : undefined)
    }
  }
  if (options.preview && options.sample && preview.drawn) {
    ctx.lineWidth = 1 / scale
    ctx.strokeStyle = palette.character
    ctx.setLineDash([4 / scale, 2 / scale])
    ctx.strokeRect(...preview.drawn)
    ctx.setLineDash([])
  }
  for (const { element, box } of rows) drawText(ctx, element, box, options)
  if (ghost) {
    ctx.fillStyle = palette.ghost
    ctx.globalAlpha = .15
    ctx.fillRect(...ghost)
    ctx.globalAlpha = 1
    ctx.strokeStyle = palette.ghost
    ctx.lineWidth = 1 / scale
    ctx.setLineDash([4 / scale, 2 / scale])
    ctx.strokeRect(...ghost)
    ctx.setLineDash([])
    ctx.font = `${12 / scale}px Arial`
    ctx.fillStyle = palette.ghost
    ctx.fillText(ghostLabel, ghost[0] + 3 / scale, ghost[1] + 13 / scale)
  }
  const marked = new Set(selection)
  for (const { element, box } of rows) {
    if (!marked.has(element.index)) continue
    ctx.lineWidth = 2 / scale
    ctx.strokeStyle = palette.selection
    ctx.strokeRect(...box)
    if (options.preview && element.index === 0 && preview.frame) ctx.strokeRect(...preview.frame)
  }
  for (const { point: [x, y] } of handles) {
    ctx.fillStyle = palette.selection
    const radius = 5 / scale
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2)
  }
  if (marquee) {
    ctx.fillStyle = palette.outline
    ctx.strokeStyle = palette.outline
    ctx.lineWidth = 1 / scale
    ctx.globalAlpha = .16
    ctx.fillRect(...marquee)
    ctx.globalAlpha = 1
    ctx.strokeRect(...marquee)
  }
  if (options.labels) drawLabels(ctx, rows, selected, pixelRatio, palette)
  ctx.restore()
}
