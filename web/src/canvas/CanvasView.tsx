import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent, RefObject } from 'react'
import { Group, Layer, Shape, Stage } from 'react-konva/lib/ReactKonvaCore.js'
import {
  canvasAssetBase, canvasBackgroundBase, on, openCanvasDocument,
  type CanvasDocument, type CanvasElement, type CanvasPoint, type CanvasRect, type CanvasTextMode,
} from '../bridge'
import { drawDots, drawScene, sceneRows, type SceneOptions } from './drawScene'
import { TextureCache } from './dds/cache'
import './canvas.css'

export interface CanvasViewProps {
  path: string | null
  language?: string
  resolution?: CanvasPoint
  onSelect?: (element: CanvasElement | null) => void
}

const labels = {
  pt: ['Nenhum XML aberto', 'Carregando XML…', 'Contornos', 'IDs', 'Tela', 'Fundo', 'Personagem', 'Texto', 'Sem texto', 'Jogo', 'XML', 'Curto', 'Longo', 'Enquadrar', 'Texto', 'Texto de exemplo bem comprido para testar o espaço', 'Texturas indisponíveis', 'Normal', 'Foco', 'Pressionado', 'Desativado'],
  en: ['No XML open', 'Loading XML…', 'Outlines', 'IDs', 'Screen', 'Background', 'Character', 'Text', 'No text', 'Game', 'XML', 'Short', 'Long', 'Fit', 'Text', 'A rather long sample text to test the space', 'Unavailable textures', 'Normal', 'Focused', 'Pressed', 'Disabled'],
  es: ['Ningún XML abierto', 'Cargando XML…', 'Contornos', 'IDs', 'Pantalla', 'Fondo', 'Personaje', 'Texto', 'Sin texto', 'Juego', 'XML', 'Corto', 'Largo', 'Ajustar', 'Texto', 'Texto de ejemplo bastante largo para probar el espacio', 'Texturas no disponibles', 'Normal', 'En foco', 'Pulsado', 'Desactivado'],
  fr: ['Aucun XML ouvert', 'Chargement du XML…', 'Contours', 'ID', 'Écran', 'Fond', 'Personnage', 'Texte', 'Sans texte', 'Jeu', 'XML', 'Court', 'Long', 'Ajuster', 'Texte', 'Un texte assez long pour tester la place disponible', 'Textures indisponibles', 'Normal', 'Survol', 'Appuyé', 'Désactivé'],
}
const textModes: CanvasTextMode[] = ['off', 'game', 'xml', 'short', 'long']
const buttonStates = ['FocusUV', 'DownUV', 'DisableUV']
const imageKey = (name: string) => name.toLowerCase()
type TexturesChanged = { base: string; names: string[] }

interface View {
  x: number
  y: number
  scale: number
}

function fit([x, y, width, height]: CanvasRect, size: CanvasPoint): View {
  const scale = Math.max(0.05, Math.min(16, (size[0] - 40) / width, (size[1] - 44) / height))
  return { x: Math.round((size[0] - width * scale) / 2 - x * scale), y: Math.round((size[1] - height * scale) / 2 - y * scale), scale }
}

function useTextureCache() {
  const cache = useRef<TextureCache | null>(null)
  useEffect(() => {
    const current = new TextureCache()
    cache.current = current
    const unsubscribe = on('canvas_textures_changed', (payload) => {
      const { base, names } = payload as TexturesChanged
      for (const name of names) current.invalidate(base, name)
    })
    return () => {
      unsubscribe()
      cache.current = null
      current.dispose()
    }
  }, [])
  return cache
}

function useTextures(
  cache: RefObject<TextureCache | null>,
  base: string | undefined,
  document: CanvasDocument | undefined,
  sample: boolean,
) {
  const [images, setImages] = useState(new Map<string, ImageBitmap | null>())
  const names = useMemo(() => {
    const names = new Set<string>()
    for (const element of document?.elements ?? []) {
      if (element.texture && (element.uv || element.button_uvs.ThumbUV)) names.add(imageKey(element.texture))
      if (sample && element.sample_icon) names.add(imageKey(element.sample_icon[0]))
    }
    return names
  }, [document, sample])
  useEffect(() => {
    const current = cache.current
    const loaded = new Map<string, ImageBitmap | null>()
    setImages(loaded)
    if (!base || !current) return
    let active = true
    let frame = 0
    const requests = new Map<string, Promise<ImageBitmap | null>>()
    const load = (name: string) => {
      const request = current.load(base, name)
      requests.set(name, request)
      void request.then((bitmap) => {
        if (!active || requests.get(name) !== request) return
        loaded.set(name, bitmap)
        if (!frame) {
          frame = requestAnimationFrame(() => {
            frame = 0
            setImages(new Map(loaded))
          })
        }
      })
    }
    const unsubscribe = on('canvas_textures_changed', (payload) => {
      const changed = payload as TexturesChanged
      if (changed.base !== base) return
      for (const name of changed.names) {
        // The displayed scene retains the previous bitmap until its replacement is ready.
        if (names.has(name)) load(name)
      }
    })
    for (const name of names) load(name)
    return () => {
      active = false
      unsubscribe()
      cancelAnimationFrame(frame)
    }
  }, [base, cache, names])
  return { images, loading: [...names].some((name) => !images.has(name)) }
}

export default function CanvasView({ path, language, resolution, onSelect }: CanvasViewProps) {
  const locale = (language ?? document.documentElement.lang).slice(0, 2).toLowerCase()
  const t = labels[locale as keyof typeof labels] ?? labels.pt
  const viewport = useRef<HTMLDivElement>(null)
  const drag = useRef<{ id: number; x: number; y: number; moved: boolean; select: boolean } | null>(null)
  const [size, setSize] = useState<CanvasPoint>([0, 0])
  const [view, setView] = useState<View>({ x: 0, y: 0, scale: 1 })
  const [loaded, setLoaded] = useState<{ path: string; scene: CanvasDocument; base: string }>()
  const [error, setError] = useState<{ path: string; message: string }>()
  const [options, setOptions] = useState<SceneOptions>(() => ({
    outlines: true, labels: false, preview: false, sample: true, text: 'off', short: t[14], long: t[15],
  }))
  const [showBackground, setShowBackground] = useState(true)
  const [background, setBackground] = useState<ImageBitmap | null>()
  const [selected, setSelected] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const [resolutionWidth, resolutionHeight] = resolution ?? []
  const current = loaded?.path === path ? loaded : undefined
  const scene = current?.scene
  const rows = useMemo(() => scene && sceneRows(scene, options.preview), [scene, options.preview])
  const cache = useTextureCache()
  const { images, loading } = useTextures(cache, current?.base, scene, options.sample)
  const bounds = options.preview ? scene?.preview.screen : scene?.bounds

  useEffect(() => {
    setSelected(null)
    setError(undefined)
    setLoaded(undefined)
    if (!path) return
    let disposed = false
    const explicitResolution: CanvasPoint | undefined = resolutionWidth && resolutionHeight
      ? [resolutionWidth, resolutionHeight] : undefined
    void Promise.all([openCanvasDocument(path, explicitResolution), canvasAssetBase(path)]).then(
      ([scene, base]) => { if (!disposed) setLoaded({ path, scene, base }) },
      (reason) => { if (!disposed) setError({ path, message: String(reason) }) },
    )
    return () => { disposed = true }
  }, [path, resolutionWidth, resolutionHeight])

  const backgroundFile = scene?.preview.background
  const wantsBackground = options.preview && showBackground
  useEffect(() => {
    setBackground(undefined)
    if (!wantsBackground || !backgroundFile) return
    let disposed = false
    void canvasBackgroundBase()
      .then((base) => cache.current?.load(base, backgroundFile, false))
      .then((image) => { if (!disposed) setBackground(image ?? null) })
      .catch(() => { if (!disposed) setBackground(null) })
    return () => { disposed = true }
  }, [wantsBackground, backgroundFile, cache])

  useLayoutEffect(() => {
    if (!viewport.current) return
    const observer = new ResizeObserver(([entry]) => {
      setSize([Math.floor(entry.contentRect.width), Math.floor(entry.contentRect.height)])
    })
    observer.observe(viewport.current)
    return () => observer.disconnect()
  }, [])

  useLayoutEffect(() => {
    if (bounds && size[0] && size[1]) setView(fit(bounds, size))
  }, [bounds, size])

  useEffect(() => {
    const node = viewport.current
    if (!node) return
    const wheel = (event: WheelEvent) => {
      if (!scene) return
      event.preventDefault()
      const rect = node.getBoundingClientRect()
      const x = event.clientX - rect.left
      const y = event.clientY - rect.top
      setView((old) => {
        const scale = Math.max(0.05, Math.min(16, old.scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15)))
        const ratio = scale / old.scale
        return { scale, x: x - (x - old.x) * ratio, y: y - (y - old.y) * ratio }
      })
    }
    node.addEventListener('wheel', wheel, { passive: false })
    return () => node.removeEventListener('wheel', wheel)
  }, [scene])

  function select(element: CanvasElement | null) {
    setSelected(element?.index ?? null)
    setOptions((old) => ({ ...old, buttonState: undefined }))
    onSelect?.(element)
  }

  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!rows || ![0, 1, 2].includes(event.button)) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false, select: event.button === 0 }
  }

  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current
    if (!start || start.id !== event.pointerId) return
    const dx = event.clientX - start.x
    const dy = event.clientY - start.y
    if (!start.moved && Math.hypot(dx, dy) < 3) return
    drag.current = { ...start, x: event.clientX, y: event.clientY, moved: true }
    setDragging(true)
    setView((old) => ({ ...old, x: old.x + dx, y: old.y + dy }))
  }

  function pointerUp(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current
    drag.current = null
    setDragging(false)
    if (!start?.select || start.moved || start.id !== event.pointerId || !rows) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - rect.left - view.x) / view.scale
    const y = (event.clientY - rect.top - view.y) / view.scale
    const hit = rows.findLast(({ box: [left, top, width, height] }) =>
      x >= left && x <= left + width && y >= top && y <= top + height)
    select(hit?.element ?? null)
  }

  const missing = [...images].filter(([, image]) => !image).map(([name]) => name)
  const button = selected !== null && scene?.elements[selected]?.button_uvs
  const hasSample = scene?.elements.some((element) => element.sample_text || element.sample_icon)
  const toggle = (key: 'outlines' | 'labels' | 'preview' | 'sample') =>
    setOptions((old) => ({ ...old, [key]: !old[key] }))
  return (
    <section className="gf-canvas"
      aria-busy={!!path && error?.path !== path && (!scene || loading || (wantsBackground && !!backgroundFile && background === undefined))}>
      {scene && <div className="gf-canvas-toolbar">
        <button aria-pressed={options.outlines} onClick={() => toggle('outlines')}>{t[2]}</button>
        <button aria-pressed={options.labels} onClick={() => toggle('labels')}>{t[3]}</button>
        <button aria-pressed={options.preview} onClick={() => toggle('preview')}>{t[4]}</button>
        {options.preview && backgroundFile && <button aria-pressed={showBackground} onClick={() => setShowBackground(!showBackground)}>{t[5]}</button>}
        {hasSample && <button aria-pressed={options.sample} onClick={() => toggle('sample')}>{t[6]}</button>}
        <select aria-label={t[7]} value={options.text}
          onChange={(event) => setOptions({ ...options, text: event.target.value as CanvasTextMode })}>
          {textModes.map((mode, index) => <option key={mode} value={mode}>{t[index + 8]}</option>)}
        </select>
        {button && buttonStates.some((state) => button[state]) &&
          <select aria-label={t[17]} value={options.buttonState ?? ''}
            onChange={(event) => setOptions({ ...options, buttonState: event.target.value || undefined })}>
            <option value="">{t[17]}</option>
            {buttonStates.map((state, index) => button[state] && <option key={state} value={state}>{t[18 + index]}</option>)}
          </select>}
        <button onClick={() => bounds && setView(fit(bounds, size))}>{t[13]} · {Math.round(view.scale * 100)}%</button>
        {!!missing.length && <output title={missing.join(', ')}>{t[16]} ({missing.length})</output>}
      </div>}
      <div ref={viewport} className="gf-canvas-viewport" style={{ cursor: dragging ? 'grabbing' : scene ? 'grab' : undefined }}
        onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}
        onLostPointerCapture={() => { drag.current = null; setDragging(false) }}
        onContextMenu={(event) => event.preventDefault()}>
        {scene && rows && size[0] > 0 && size[1] > 0 ?
          <Stage width={size[0]} height={size[1]} listening={false}>
            <Layer listening={false}>
              <Shape sceneFunc={(context) => drawDots(context._context, ...size)} />
            </Layer>
            <Layer listening={false}>
              <Group x={view.x} y={view.y} scaleX={view.scale} scaleY={view.scale}>
                <Shape sceneFunc={(context) => drawScene(context._context, scene, rows, images,
                  { ...options, short: t[14], long: t[15] }, wantsBackground ? background ?? null : null, view.scale, selected)} />
              </Group>
            </Layer>
          </Stage>
          : <div className="gf-canvas-status" role={error?.path === path ? 'alert' : 'status'}>
            {!path ? t[0] : error?.path === path ? error.message : t[1]}
          </div>}
      </div>
    </section>
  )
}
