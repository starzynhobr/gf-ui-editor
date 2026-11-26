// Prévia de uma resolução: as janelas desenhadas como no Preview do jogo (as mesmas funções
// do canvas, só importadas) numa tela do tamanho alvo, com o contorno de cada pedaço que o
// editor reposicionou. Ampliada, deixa arrastar um pedaço: o ajuste vale só nesta resolução.
import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { canvasBackgroundBase, type CanvasDocument, type CanvasPoint, type CanvasRect } from '../bridge'
import { drawReferenceLayer, drawScreen, type SceneOptions } from '../canvas/drawScene'
import { useCanvasPalette } from '../canvas/palette'
import type { TextureCache } from '../canvas/dds/cache'
import type { PieceInfo, SceneLayer, Size, WindowInfo } from './resolutionsApi'

type Images = Map<string, ImageBitmap | null>

const OPTIONS: SceneOptions = {
  sample: false, text: 'off', short: '', long: '', outlines: false, labels: false, preview: true, textMasks: new Map(),
}

export interface Drag {
  file: string
  piece: PieceInfo
  start: CanvasPoint
  delta: CanvasPoint
}

/** Texturas de todas as cenas, por pasta (base) e nome. */
function useLayerImages(cache: TextureCache | null, layers: SceneLayer[]) {
  const [images, setImages] = useState(new Map<string, Images>())
  const wanted = useMemo(() => {
    const names = new Map<string, Set<string>>()
    for (const { base, scene } of layers) {
      if (!base) continue
      const set = names.get(base) ?? new Set<string>()
      for (const element of scene.elements) if (element.texture && element.uv) set.add(element.texture.toLowerCase())
      names.set(base, set)
    }
    return JSON.stringify([...names].map(([base, set]) => [base, [...set].sort()]))
  }, [layers])
  useEffect(() => {
    if (!cache) return
    let active = true
    const loaded = new Map<string, Images>()
    const pending: Promise<void>[] = []
    for (const [base, names] of JSON.parse(wanted) as [string, string[]][]) {
      const map: Images = new Map()
      loaded.set(base, map)
      for (const name of names) {
        pending.push(cache.load(base, name, name.endsWith('.dds')).then((bitmap) => void map.set(name, bitmap)))
      }
    }
    void Promise.all(pending).then(() => active && setImages(loaded))
    return () => {
      active = false
    }
  }, [cache, wanted])
  return images
}

function useBackground(cache: TextureCache | null, name: string | null | undefined) {
  const [image, setImage] = useState<ImageBitmap | null>(null)
  useEffect(() => {
    if (!cache || !name) return
    let active = true
    void canvasBackgroundBase()
      .then((base) => cache.load(base, name, false))
      .then((bitmap) => active && setImage(bitmap))
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [cache, name])
  return image
}

/** A cena com os elementos do pedaço arrastado deslocados (o resto da janela fica). */
function shifted(scene: CanvasDocument, indexes: number[], [dx, dy]: CanvasPoint): CanvasDocument {
  const moving = new Set(indexes)
  return {
    ...scene,
    elements: scene.elements.map((element) => {
      if (!moving.has(element.index)) return element
      const [x, y, w, h] = element.geometry
      return { ...element, geometry: [x + dx, y + dy, w, h] as CanvasRect }
    }),
  }
}

/** O pedaço sob o ponto: primeiro os que o editor moveu (ou a pessoa ajustou), depois o HUD;
 * entre eles, o menor (o que está "por cima" de uma janela grande). */
export function pieceAt(windows: WindowInfo[], [x, y]: CanvasPoint): { file: string; piece: PieceInfo } | null {
  const hits: { file: string; piece: PieceInfo; rank: number; area: number }[] = []
  for (const window of windows) {
    for (const piece of window.pieces) {
      const [px, py, pw, ph] = piece.rect
      if (x < px || x > px + pw || y < py || y > py + ph) continue
      const rank = piece.moved || piece.adjusted ? 0 : window.hud ? 1 : window.moves ? 2 : -1
      if (rank >= 0) hits.push({ file: window.file, piece, rank, area: pw * ph })
    }
  }
  hits.sort((a, b) => a.rank - b.rank || a.area - b.area)
  return hits[0] ? { file: hits[0].file, piece: hits[0].piece } : null
}

function cssColor(name: string, fallback: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

export function ResolutionPreview({
  size, layers, windows, cache, interactive = false, highlight = null, adjustedLabel = '', onAdjust, className = '',
}: {
  size: Size
  layers: SceneLayer[]
  windows: WindowInfo[]
  cache: TextureCache | null
  interactive?: boolean
  highlight?: string | null
  adjustedLabel?: string
  onAdjust?: (file: string, piece: PieceInfo, point: CanvasPoint) => void
  className?: string
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const palette = useCanvasPalette()
  const images = useLayerImages(cache, layers)
  const background = useBackground(cache, layers.find((layer) => layer.scene.preview.background)?.scene.preview.background)
  const [drag, setDragState] = useState<Drag | null>(null)
  // O arraste vive numa ref: eventos que chegam antes do próximo render (mouse rápido) já o veem.
  const dragRef = useRef<Drag | null>(null)
  const setDrag = (next: Drag | null) => {
    dragRef.current = next
    setDragState(next)
  }
  const [hover, setHover] = useState<string | null>(null)
  const [width, height] = size

  // Desenha: fundo, janelas do HUD, janelas que mudam e os contornos dos pedaços.
  useEffect(() => {
    const element = canvas.current
    const ctx = element?.getContext('2d')
    if (!element || !ctx) return
    const ratio = window.devicePixelRatio || 1
    const shown = element.clientWidth || 320
    const scale = shown / width
    element.width = Math.round(shown * ratio)
    element.height = Math.round(shown * (height / width) * ratio)
    ctx.setTransform(scale * ratio, 0, 0, scale * ratio, 0, 0)
    const screen: CanvasRect = [0, 0, width, height]
    drawScreen(ctx, screen, background, scale, palette)
    const order = [...layers].sort((a, b) => Number(isMover(windows, a.name)) - Number(isMover(windows, b.name)))
    for (const layer of order) {
      const scene = drag && drag.file === layer.name ? shifted(layer.scene, drag.piece.indexes, drag.delta) : layer.scene
      drawReferenceLayer(ctx, scene, images.get(layer.base) ?? new Map(), screen, OPTIONS)
    }
    const accent = cssColor('--color-accent', '#4c8dff')
    const gold = cssColor('--color-gold', '#e5b453')
    ctx.lineWidth = 2 / scale
    ctx.font = `${12 / scale}px system-ui, sans-serif`
    for (const window of windows) {
      for (const piece of window.pieces) {
        const moving = drag && drag.file === window.file && drag.piece.key === piece.key
        const lit = highlight === window.file || hover === `${window.file}|${piece.key}` || !!moving
        // Contorno no que o editor mexeu (ou a pessoa ajustou); o resto só sob o mouse.
        if (!lit && !piece.moved && !piece.adjusted) continue
        const [x, y, w, h] = piece.rect
        const box: CanvasRect = moving ? [x + drag.delta[0], y + drag.delta[1], w, h] : [x, y, w, h]
        ctx.strokeStyle = piece.adjusted ? gold : accent
        ctx.globalAlpha = lit ? 1 : 0.75
        ctx.setLineDash(piece.adjusted ? [] : [6 / scale, 4 / scale])
        ctx.strokeRect(...box)
        if (lit) {
          ctx.globalAlpha = 0.12
          ctx.fillStyle = piece.adjusted ? gold : accent
          ctx.fillRect(...box)
        }
        ctx.globalAlpha = 1
        ctx.setLineDash([])
        if (interactive && (lit || piece.adjusted)) {
          const label = piece.adjusted ? `${window.file} · ${adjustedLabel}` : window.file
          ctx.fillStyle = piece.adjusted ? gold : accent
          ctx.fillText(label, box[0], Math.max(12 / scale, box[1] - 4 / scale))
        }
      }
    }
  }, [layers, windows, images, background, palette, drag, hover, highlight, width, height, interactive, adjustedLabel])

  const toScreen = (event: PointerEvent<HTMLCanvasElement>): CanvasPoint => {
    const bounds = event.currentTarget.getBoundingClientRect()
    const scale = (bounds.width || 1) / width
    return [(event.clientX - bounds.left) / scale, (event.clientY - bounds.top) / scale]
  }

  return (
    <canvas
      ref={canvas}
      data-testid={interactive ? 'resolution-stage' : 'resolution-thumb'}
      className={`block w-full rounded-md ${interactive ? (drag ? 'cursor-grabbing' : hover ? 'cursor-grab' : '') : ''} ${className}`}
      style={{ aspectRatio: `${width} / ${height}` }}
      onPointerDown={interactive ? (event) => {
        const point = toScreen(event)
        const hit = pieceAt(windows, point)
        if (!hit) return
        try {
          event.currentTarget.setPointerCapture(event.pointerId)
        } catch {
          // Ponteiro que o navegador não conhece (sintético): o arraste segue sem captura.
        }
        setDrag({ ...hit, start: point, delta: [0, 0] })
      } : undefined}
      onPointerMove={interactive ? (event) => {
        const point = toScreen(event)
        const current = dragRef.current
        if (current) {
          setDrag({ ...current, delta: [Math.round(point[0] - current.start[0]), Math.round(point[1] - current.start[1])] })
          return
        }
        const hit = pieceAt(windows, point)
        setHover(hit ? `${hit.file}|${hit.piece.key}` : null)
      } : undefined}
      onPointerUp={interactive ? () => {
        const current = dragRef.current
        if (!current) return
        setDrag(null)
        const [dx, dy] = current.delta
        if (dx || dy) onAdjust?.(current.file, current.piece, [current.piece.rect[0] + dx, current.piece.rect[1] + dy])
      } : undefined}
      onPointerLeave={interactive ? () => !dragRef.current && setHover(null) : undefined}
    />
  )
}

function isMover(windows: WindowInfo[], file: string) {
  return windows.some((window) => window.file === file && window.moves)
}
