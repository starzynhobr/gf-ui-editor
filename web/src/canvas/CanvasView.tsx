import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent, RefObject } from 'react'
import { Group, Layer, Shape, Stage } from 'react-konva/lib/ReactKonvaCore.js'
import {
  canvasAssetBase, canvasBackgroundBase, on,
  type CanvasDocument, type CanvasElement, type CanvasPoint, type CanvasRect, type CanvasTextMode,
} from '../bridge'
import { applyCanvasEdits, checkExternalChange, ensureDoc, select, useDoc } from '../doc/store'
import { drawDots, drawScene, drawsRootTexture, sceneRows, type SceneOptions } from './drawScene'
import {
  between, contains, draftScene, intersects, moves, resizeHandles, resizes, visibleRows,
  type Axis, type GeometryEdit, type Handle,
} from './geometry'
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
const editLabels = {
  pt: ['Mover', 'Redimensionar', 'Área invisível da janela', 'O XML mudou no disco. Recarregar e descartar as alterações não salvas?', 'O XML aberto foi removido do disco.'],
  en: ['Move', 'Resize', 'Invisible window area', 'The XML changed on disk. Reload and discard unsaved changes?', 'The open XML was removed from disk.'],
  es: ['Mover', 'Redimensionar', 'Área invisible de la ventana', 'El XML cambió en el disco. ¿Recargar y descartar los cambios sin guardar?', 'El XML abierto se eliminó del disco.'],
  fr: ['Déplacer', 'Redimensionner', 'Zone invisible de la fenêtre', 'Le XML a changé sur le disque. Recharger et abandonner les modifications non enregistrées ?', 'Le XML ouvert a été supprimé du disque.'],
}
const imageKey = (name: string) => name.toLowerCase()
type TexturesChanged = { base: string; names: string[] }

interface View {
  x: number
  y: number
  scale: number
}

type Gesture = {
  id: number
  start: CanvasPoint
  origin: CanvasPoint
  mode: 'pan' | 'box' | 'move' | 'resize'
  handle?: Handle
  indexes: number[]
  target: number | null
  axis?: Axis
  moved: boolean
  edits: GeometryEdit[]
  document: CanvasDocument
}

const arrows: Record<string, CanvasPoint> = {
  ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
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
  const keys = useMemo(() => {
    const names = new Set<string>()
    for (const element of document?.elements ?? []) {
      if (element.texture && (element.uv || element.button_uvs.ThumbUV)) names.add(imageKey(element.texture))
      if (sample && element.sample_icon) names.add(imageKey(element.sample_icon[0]))
    }
    return JSON.stringify([...names])
  }, [document, sample])
  const names = useMemo(() => new Set<string>(JSON.parse(keys)), [keys])
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
  const editText = editLabels[locale as keyof typeof editLabels] ?? editLabels.pt
  const viewport = useRef<HTMLDivElement>(null)
  const drag = useRef<Gesture | null>(null)
  const committing = useRef<CanvasDocument | null>(null)
  const space = useRef(false)
  const [size, setSize] = useState<CanvasPoint>([0, 0])
  const [view, setView] = useState<View>({ x: 0, y: 0, scale: 1 })
  const [loaded, setLoaded] = useState<{ path: string; base: string }>()
  const [error, setError] = useState<{ path: string; message: string }>()
  const [options, setOptions] = useState<SceneOptions>(() => ({
    outlines: true, labels: false, preview: false, sample: true, text: 'off', short: t[14], long: t[15],
  }))
  const [showBackground, setShowBackground] = useState(true)
  const [background, setBackground] = useState<ImageBitmap | null>()
  const [draft, setDraft] = useState<GeometryEdit[]>([])
  const [marquee, setMarquee] = useState<CanvasRect | null>(null)
  const [cursor, setCursor] = useState('default')
  const { path: openPath, doc, selection, hidden, locked, isolated, error: documentError } = useDoc()
  const [resolutionWidth, resolutionHeight] = resolution ?? []
  const current = loaded?.path === path ? loaded : undefined
  const scene = openPath === path ? doc ?? undefined : undefined
  const draftSource = drag.current?.document ?? committing.current
  const drawn = useMemo(
    () => scene && (draft.length && scene === draftSource ? draftScene(scene, draft, options.preview) : scene),
    [scene, draft, draftSource, options.preview],
  )
  const rows = useMemo(
    () => drawn ? visibleRows(sceneRows(drawn, options.preview), hidden, isolated) : [],
    [drawn, options.preview, hidden, isolated],
  )
  const frame = options.preview ? drawn?.preview.frame ?? null : null
  const handles = useMemo(() => resizeHandles(rows, selection, locked, frame), [rows, selection, locked, frame])
  const selected = selection[0] ?? null
  const cache = useTextureCache()
  const { images, loading } = useTextures(cache, current?.base, scene, options.sample)
  const bounds = options.preview ? scene?.preview.screen : scene?.bounds
  const root = scene?.elements[0]
  const rootBackground = useMemo(() => drawsRootTexture(root, images), [root, images])
  const ghost = options.preview && !rootBackground && rows.some(({ element }) => element.index === 0)
    ? scene?.ghost_area ?? null : null

  useEffect(() => {
    cancelGesture()
    setError(undefined)
    setLoaded(undefined)
    let disposed = false
    const explicitResolution: CanvasPoint | undefined = resolutionWidth && resolutionHeight
      ? [resolutionWidth, resolutionHeight] : undefined
    void Promise.all([ensureDoc(path, explicitResolution), path ? canvasAssetBase(path) : null]).then(
      ([, base]) => { if (!disposed && path && base) setLoaded({ path, base }) },
      (reason) => { if (!disposed && path) setError({ path, message: String(reason) }) },
    )
    return () => { disposed = true }
  }, [path, resolutionWidth, resolutionHeight])

  useEffect(() => {
    if (!path || !scene) return
    const timer = window.setInterval(() => {
      if (drag.current) return
      void checkExternalChange(path, (missing) => {
        if (!missing) return window.confirm(editText[3])
        window.alert(editText[4])
        return false
      }).catch(() => undefined)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [path, !!scene, editText])

  useEffect(() => {
    setOptions((old) => old.buttonState === undefined ? old : { ...old, buttonState: undefined })
  }, [selected])

  useEffect(() => {
    onSelect?.(selected === null ? null : scene?.elements[selected] ?? null)
  }, [selected, scene, onSelect])

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

  const framing = useRef<{ path: string | null; preview: boolean; size: CanvasPoint; bounds: CanvasRect } | null>(null)
  useLayoutEffect(() => {
    if (!bounds || !size[0] || !size[1]) return
    const previous = framing.current
    if (!previous || previous.path !== path || previous.preview !== options.preview || previous.size !== size) {
      setView(fit(bounds, size))
    } else if (options.preview) {
      const dx = previous.bounds[0] - bounds[0]
      const dy = previous.bounds[1] - bounds[1]
      if (dx || dy) setView((old) => ({ ...old, x: old.x + dx * old.scale, y: old.y + dy * old.scale }))
    }
    framing.current = { path, preview: options.preview, size, bounds }
  }, [path, options.preview, bounds, size])

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

  function scenePoint(event: PointerEvent<HTMLDivElement>): CanvasPoint {
    const rect = event.currentTarget.getBoundingClientRect()
    return [(event.clientX - rect.left - view.x) / view.scale, (event.clientY - rect.top - view.y) / view.scale]
  }

  function handleAt(point: CanvasPoint) {
    const radius = 9 / view.scale
    return handles.findLast(({ point: [x, y] }) =>
      Math.abs(point[0] - x) <= radius && Math.abs(point[1] - y) <= radius)
  }

  function activeIndexes(indexes: number[]) {
    const allowed = new Set(rows.map(({ element }) => element.index))
    return indexes.filter((index) => allowed.has(index) && !locked.includes(index))
  }

  function cancelGesture() {
    drag.current = null
    setDraft([])
    setMarquee(null)
    setCursor('default')
  }

  function editGeometry(makeEdits: (doc: CanvasDocument) => GeometryEdit[], label: string) {
    return applyCanvasEdits(makeEdits, label, options.preview, rootBackground).catch(() => undefined)
  }

  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!scene || drag.current || committing.current || ![0, 1, 2].includes(event.button)) return
    event.preventDefault()
    event.currentTarget.focus({ preventScroll: true })
    event.currentTarget.setPointerCapture(event.pointerId)
    const point = scenePoint(event)
    const pan = event.button !== 0 || space.current
    const handle = pan ? undefined : handleAt(point)
    const rootRow = rows.find(({ element }) => element.index === 0)
    const additive = event.ctrlKey || event.shiftKey || event.metaKey
    const hit = rows.findLast(({ box }) => contains(box, point))
    const target = frame && rootRow && selected === 0 && !additive && contains(frame, point)
      ? 0 : hit?.element.index ?? null
    let indexes = activeIndexes(selection)
    let mode: Gesture['mode'] = pan ? 'pan' : 'box'
    if (handle) {
      mode = 'resize'
      if (frame) indexes = handle.index === 0 ? [0] : indexes.filter((index) => index !== 0)
    } else if (!pan && target !== null) {
      if (!selection.includes(target)) select([target], additive ? 'add' : 'replace')
      indexes = activeIndexes(useDoc.getState().selection)
      mode = 'move'
      if (locked.includes(target)) indexes = []
    }
    drag.current = {
      id: event.pointerId, start: [event.clientX, event.clientY], origin: pan ? [view.x, view.y] : point,
      mode, handle, indexes, target, moved: false, edits: [], document: scene,
    }
    if (pan) setCursor('grabbing')
  }

  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current
    if (!start) {
      const point = scenePoint(event)
      const handle = handleAt(point)
      if (handle) {
        const [x, y] = handle.axes
        setCursor(!x ? 'ns-resize' : !y ? 'ew-resize' : x === y ? 'nwse-resize' : 'nesw-resize')
      } else {
        setCursor(space.current ? 'grab' : rows.some(({ box }) => contains(box, point)) ? 'move' : 'default')
      }
      return
    }
    if (start.id !== event.pointerId) return
    const dx = event.clientX - start.start[0]
    const dy = event.clientY - start.start[1]
    if (!start.moved && Math.hypot(dx, dy) < 3) return
    start.moved = true
    const delta: CanvasPoint = [dx / view.scale, dy / view.scale]
    if (start.mode === 'pan') {
      setView((old) => ({ ...old, x: start.origin[0] + dx, y: start.origin[1] + dy }))
    } else if (start.mode === 'box') {
      setMarquee(between(start.origin, scenePoint(event)))
    } else if (start.handle) {
      start.edits = resizes(start.document, start.indexes, start.handle, delta, event.shiftKey, options.preview)
      setDraft(start.edits)
    } else {
      start.axis = event.shiftKey ? start.axis ?? (Math.abs(dx) >= Math.abs(dy) ? 'horizontal' : 'vertical') : undefined
      if (start.axis === 'horizontal') delta[1] = 0
      if (start.axis === 'vertical') delta[0] = 0
      start.edits = moves(start.document, start.indexes, delta)
      setDraft(start.edits)
    }
  }

  function pointerUp(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current
    if (!start || start.id !== event.pointerId) return
    drag.current = null
    setMarquee(null)
    setCursor('default')
    const additive = event.ctrlKey || event.shiftKey || event.metaKey
    if (start.mode === 'box') {
      const box = between(start.origin, scenePoint(event))
      const hits = start.moved ? rows.filter((row) => intersects(row.box, box)).toReversed() : []
      select(hits.map(({ element }) => element.index), additive ? 'add' : 'replace')
    } else if (start.edits.length) {
      committing.current = start.document
      void editGeometry(() => start.edits, editText[start.mode === 'resize' ? 1 : 0]).finally(() => {
        committing.current = null
        setDraft([])
      })
    } else if (start.mode === 'move' && start.target !== null && !start.moved && !additive) {
      select([start.target])
    }
  }

  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.code === 'Space') {
      event.preventDefault()
      space.current = true
      setCursor('grab')
    }
    if (event.key === 'Escape' && drag.current) cancelGesture()
    const direction = arrows[event.key]
    if (!direction || !scene || drag.current || committing.current) return
    event.preventDefault()
    event.stopPropagation()
    const indexes = activeIndexes(selection)
    const step = event.shiftKey ? 10 : 1
    void editGeometry((latest) => moves(latest, indexes, [direction[0] * step, direction[1] * step]), editText[0])
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
        {documentError && <output title={documentError}>{documentError}</output>}
      </div>}
      <div ref={viewport} className="gf-canvas-viewport" tabIndex={0} style={{ cursor }}
        onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}
        onLostPointerCapture={() => { if (drag.current) cancelGesture() }} onPointerCancel={cancelGesture}
        onKeyDown={keyDown}
        onKeyUp={(event) => { if (event.code === 'Space') { space.current = false; setCursor('default') } }}
        onBlur={() => { space.current = false }}
        onContextMenu={(event) => event.preventDefault()}>
        {drawn && size[0] > 0 && size[1] > 0 ?
          <Stage width={size[0]} height={size[1]} listening={false}>
            <Layer listening={false}>
              <Shape sceneFunc={(context) => drawDots(context._context, ...size)} />
            </Layer>
            <Layer listening={false}>
              <Group x={view.x} y={view.y} scaleX={view.scale} scaleY={view.scale}>
                <Shape sceneFunc={(context) => drawScene(context._context, drawn, rows, images,
                  { ...options, short: t[14], long: t[15] }, wantsBackground ? background ?? null : null, view.scale,
                  selected, selection, handles, marquee, ghost, editText[2])} />
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
