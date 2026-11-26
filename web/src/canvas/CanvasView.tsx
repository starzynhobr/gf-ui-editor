import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, MouseEvent, PointerEvent, ReactNode, RefObject } from 'react'
import { Group, Layer, Shape, Stage } from 'react-konva/lib/ReactKonvaCore.js'
import {
  call, canvasAssetBase, canvasBackgroundBase, on,
  type CanvasDocument, type CanvasElement, type CanvasPoint, type CanvasPreference, type CanvasPreferences,
  type CanvasRect, type TextEditsChanged,
} from '../bridge'
import { applyCanvasEdits, applyCanvasPreference, checkExternalChange, ensureDoc, refreshGameTexts, select, useDoc } from '../doc/store'
import { AtlasHost } from '../atlas/AtlasHost'
import { useShell } from '../store'
import { CanvasToolbar } from './CanvasToolbar'
import { drawDots, drawReferenceLayer, drawScene, drawScreen, drawsRootTexture, sceneRows, sceneTextRequests, type SceneOptions } from './drawScene'
import {
  between, contains, draftScene, intersects, moves, resizeHandles, resizes, visibleRows,
  type Axis, type GeometryEdit, type Handle,
} from './geometry'
import { useGameTextMasks } from './gameText'
import { TextureCache } from './dds/cache'
import { useCanvasPalette } from './palette'
import './canvas.css'

export interface CanvasViewProps {
  path: string | null
  language?: string
  resolution?: CanvasPoint
  onSelect?: (element: CanvasElement | null) => void
  /** Controle sob o mouse parado (sem gesto em andamento); null ao sair, arrastar, rolar ou editar.
   * `rect` é o retângulo do controle na janela (px de clientX/clientY); `box`, na cena. */
  onHover?: (hover: CanvasHover | null) => void
  /** Botões extras na barra flutuante (antes dos avisos). */
  toolbarExtra?: ReactNode
}

export interface CanvasHover {
  element: CanvasElement
  box: CanvasRect
  rect: CanvasRect
  pointer: CanvasPoint
}

const labels = {
  pt: ['Nenhum XML aberto', 'Carregando XML…', 'Texto', 'Texto de exemplo bem comprido para testar o espaço', 'Texturas indisponíveis'],
  en: ['No XML open', 'Loading XML…', 'Text', 'A rather long sample text to test the space', 'Unavailable textures'],
  es: ['Ningún XML abierto', 'Cargando XML…', 'Texto', 'Texto de ejemplo bastante largo para probar el espacio', 'Texturas no disponibles'],
  fr: ['Aucun XML ouvert', 'Chargement du XML…', 'Texte', 'Un texte assez long pour tester la place disponible', 'Textures indisponibles'],
}
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

interface ReferenceScene {
  name: string
  base: string
  scene: CanvasDocument
}

interface CanvasLayers {
  names: string[]
  scenes: ReferenceScene[]
  inProject: boolean
}

const noLayers: CanvasLayers = { names: [], scenes: [], inProject: false }

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

function zoomAt(view: View, target: number, [x, y]: CanvasPoint): View {
  const scale = Math.max(0.05, Math.min(16, target))
  const ratio = scale / view.scale
  return { scale, x: x - (x - view.x) * ratio, y: y - (y - view.y) * ratio }
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
      const request = current.load(base, name, name.endsWith('.dds'))
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

function ReferenceLayer({ layer, cache, screen, options }: {
  layer: ReferenceScene; cache: RefObject<TextureCache | null>; screen: CanvasRect; options: SceneOptions
}) {
  const { images } = useTextures(cache, layer.base, layer.scene, options.sample)
  return <Shape sceneFunc={(context) => drawReferenceLayer(context._context, layer.scene, images, screen, options)} />
}

export default function CanvasView({ path, language, resolution, onSelect, onHover, toolbarExtra }: CanvasViewProps) {
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
  const [buttonState, setButtonState] = useState<string>()
  const [preferences, setPreferences] = useState<CanvasPreferences>()
  const [preferenceError, setPreferenceError] = useState('')
  const [busy, setBusy] = useState(false)
  const actionPending = useRef(false)
  const revision = useShell((state) => state.revision)
  const [textRevision, setTextRevision] = useState(0)
  const [layerRevision, setLayerRevision] = useState(0)
  const [layers, setLayers] = useState<CanvasLayers>(noLayers)
  const palette = useCanvasPalette()
  const [background, setBackground] = useState<ImageBitmap | null>()
  const [draft, setDraft] = useState<GeometryEdit[]>([])
  const [marquee, setMarquee] = useState<CanvasRect | null>(null)
  const [cursor, setCursor] = useState('default')
  const hoverListener = useRef(onHover)
  hoverListener.current = onHover
  const hovering = useRef<number | null>(null)
  const clearHover = () => {
    hovering.current = null
    hoverListener.current?.(null)
  }
  const { path: openPath, doc, selection, hidden, locked, isolated, error: documentError } = useDoc()
  const [resolutionWidth, resolutionHeight] = resolution ?? []
  const current = loaded?.path === path ? loaded : undefined
  const scene = openPath === path ? doc ?? undefined : undefined
  const preview = !!preferences && preferences.resolution !== 'off'
  const sample = preferences?.character ?? true
  const text = preferences?.text ?? 'off'
  const short = t[2], long = t[3]
  useEffect(() => {
    let active = true
    void call<CanvasPreferences>('canvas_preferences')
      .then((next) => { if (active) setPreferences(next) })
      .catch((error) => { if (active) setPreferenceError(String(error)) })
    return () => { active = false }
  }, [])
  useEffect(() => on('text_edits_changed', (payload) => {
    const { project, files } = payload as TextEditsChanged
    if (files.some((file) => file.toLowerCase() === 't_textindex.ini')) {
      void refreshGameTexts(project).catch(() => undefined)
      setTextRevision((current) => current + 1)
    }
  }), [])
  const draftSource = drag.current?.document ?? committing.current
  const drawn = useMemo(
    () => scene && (draft.length && scene === draftSource ? draftScene(scene, draft, preview) : scene),
    [scene, draft, draftSource, preview],
  )
  const rows = useMemo(
    () => drawn ? visibleRows(sceneRows(drawn, preview), hidden, isolated) : [],
    [drawn, preview, hidden, isolated],
  )
  const textRequests = useMemo(
    () => sceneTextRequests(rows, { sample, text, short, long }, preview ? layers.scenes.map(({ scene }) => scene) : []),
    [rows, sample, text, short, long, preview, layers.scenes],
  )
  const gameText = useGameTextMasks(textRequests)
  const options: SceneOptions = {
    outlines: preferences?.outlines ?? true, labels: preferences?.ids ?? false,
    preview, sample, text, short, long, buttonState, textMasks: gameText.masks,
  }
  const frame = options.preview ? drawn?.preview.frame ?? null : null
  const [, , screenWidth, screenHeight] = scene?.preview.screen ?? []
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
    setButtonState(undefined)
  }, [selected])

  // A dica do mouse usa o retângulo na tela: zoom, pan ou edição o deixam velho.
  useEffect(() => clearHover(), [view, rows])
  useEffect(() => clearHover, [])

  useEffect(() => {
    onSelect?.(selected === null ? null : scene?.elements[selected] ?? null)
  }, [selected, scene, onSelect])

  const backgroundMode = preferences?.background
  const backgroundPath = preferences?.backgroundPath
  const backgroundFile = backgroundMode === 'custom' ? backgroundPath : scene?.preview.background
  const wantsBackground = options.preview && backgroundMode !== 'none' && !!backgroundFile
  useEffect(() => {
    setBackground(undefined)
    if (!wantsBackground || !backgroundFile) return
    let disposed = false
    const source = backgroundMode === 'custom'
      ? call<{ base: string; name: string } | null>('canvas_custom_background')
      : canvasBackgroundBase().then((base) => ({ base, name: backgroundFile }))
    void source
      .then((asset) => asset && cache.current?.load(asset.base, asset.name, false))
      .then((image) => { if (!disposed) setBackground(image ?? null) })
      .catch(() => { if (!disposed) setBackground(null) })
    return () => { disposed = true }
  }, [wantsBackground, backgroundMode, backgroundFile, cache])

  useEffect(() => {
    setLayers(noLayers)
  }, [path, options.preview])

  useEffect(() => {
    const refresh = () => setLayerRevision((current) => current + 1)
    window.addEventListener('gf:layers-changed', refresh)
    return () => window.removeEventListener('gf:layers-changed', refresh)
  }, [])

  const savedPositions = scene?.preview.saved_positions ?? preferences?.savedPositions
  useEffect(() => {
    if (!path || savedPositions === undefined) return
    let active = true
    const resolution = options.preview && screenWidth && screenHeight ? [screenWidth, screenHeight] : null
    void call<CanvasLayers>('canvas_layers', path, resolution, savedPositions)
      .then((value) => { if (active) setLayers(value) })
      .catch((error) => { if (active) setPreferenceError(String(error)) })
    return () => { active = false }
  }, [path, savedPositions, options.preview, screenWidth, screenHeight, revision, textRevision, layerRevision])

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
    if (!previous || previous.path !== path || previous.preview !== options.preview || previous.size !== size ||
        (options.preview && (previous.bounds[2] !== bounds[2] || previous.bounds[3] !== bounds[3]))) {
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
      clearHover()
      if (!drag.current) setView((old) => zoomAt(old, old.scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15), [x, y]))
    }
    node.addEventListener('wheel', wheel, { passive: false })
    return () => node.removeEventListener('wheel', wheel)
  }, [scene])

  useEffect(() => {
    if (!scene) return
    const reset = (event: globalThis.KeyboardEvent) => {
      if (event.key !== '0' || !event.ctrlKey || event.altKey || event.shiftKey ||
          document.querySelector('dialog[open], [role="dialog"]')) return
      event.preventDefault()
      if (!drag.current) setView((old) => zoomAt(old, 1, [size[0] / 2, size[1] / 2]))
    }
    window.addEventListener('keydown', reset)
    return () => window.removeEventListener('keydown', reset)
  }, [scene, size])

  async function toolbarAction(action: () => Promise<void>) {
    if (actionPending.current) return false
    actionPending.current = true
    setBusy(true)
    setPreferenceError('')
    try {
      await action()
      return true
    } catch (error) {
      setPreferenceError(String(error))
      return false
    } finally {
      actionPending.current = false
      setBusy(false)
    }
  }

  function changePreference(key: CanvasPreference, value: string | boolean) {
    if (!path) return Promise.resolve(false)
    cancelGesture()
    return toolbarAction(async () => {
      setPreferences(await applyCanvasPreference(path, key, value, resolution))
    })
  }

  function scenePoint(event: MouseEvent<HTMLDivElement>): CanvasPoint {
    const rect = event.currentTarget.getBoundingClientRect()
    return [(event.clientX - rect.left - view.x) / view.scale, (event.clientY - rect.top - view.y) / view.scale]
  }

  function doubleClick(event: MouseEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    const point = scenePoint(event)
    const hit = rows.findLast(({ box }) => contains(box, point))?.element
    if (hit) window.dispatchEvent(new CustomEvent('gf:element-dblclick', {
      detail: { index: hit.index, windowId: hit.id },
    }))
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
    clearHover()
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
      const hit = space.current ? undefined : rows.findLast(({ box }) => contains(box, point))
      if (!hit) {
        if (hovering.current !== null) clearHover()
      } else if (hoverListener.current) {
        const area = event.currentTarget.getBoundingClientRect()
        const [x, y, width, height] = hit.box
        hovering.current = hit.element.index
        hoverListener.current({
          element: hit.element,
          box: hit.box,
          rect: [area.left + view.x + x * view.scale, area.top + view.y + y * view.scale, width * view.scale, height * view.scale],
          pointer: [event.clientX, event.clientY],
        })
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
    clearHover()
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
  const button = selected === null ? undefined : scene?.elements[selected]?.button_uvs
  const hasSample = !!(options.preview && scene?.preview.drawn) ||
    !!scene?.elements.some((element) => element.sample_text || element.sample_icon)
  const zoom = (factor?: number) => {
    if (!drag.current) setView((old) => zoomAt(old, factor === undefined ? 1 : old.scale * factor, [size[0] / 2, size[1] / 2]))
  }
  return (
    <section className="gf-canvas"
      aria-busy={!!path && error?.path !== path && (!scene || busy || loading || gameText.loading || (wantsBackground && background === undefined))}>
      {scene && preferences && <CanvasToolbar
        preferences={{ ...preferences, savedPositions: savedPositions ?? preferences.savedPositions }}
        screen={scene.preview.screen} busy={busy}
        showCharacter={hasSample} layers={layers.names} inProject={layers.inProject}
        buttonUvs={button} buttonState={buttonState} scale={view.scale}
        onPreference={changePreference}
        onBackground={() => void toolbarAction(async () => {
          setPreferences(await call<CanvasPreferences>('canvas_choose_background'))
        })}
        onLayers={(action) => void toolbarAction(async () => {
          await call('canvas_change_layers', path, action)
          useShell.setState((state) => ({ revision: state.revision + 1 }))
          window.dispatchEvent(new CustomEvent('gf:layers-changed'))
        })}
        onButtonState={setButtonState}
        onZoom={zoom} onResetZoom={() => zoom()} onFit={() => { if (bounds) setView(fit(bounds, size)) }}>
        {toolbarExtra}
        {!!missing.length && <output title={missing.join(', ')}>{t[4]} ({missing.length})</output>}
        {(preferenceError || documentError || gameText.error) && <output role="alert">{preferenceError || documentError || gameText.error}</output>}
      </CanvasToolbar>}
      {scene && !preferences && preferenceError && <output role="alert">{preferenceError}</output>}
      <div ref={viewport} className="gf-canvas-viewport" tabIndex={0} style={{ cursor }}
        onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onDoubleClick={doubleClick}
        onLostPointerCapture={() => { if (drag.current) cancelGesture() }} onPointerCancel={cancelGesture}
        onPointerLeave={clearHover}
        onKeyDown={keyDown}
        onKeyUp={(event) => { if (event.code === 'Space') { space.current = false; setCursor('default') } }}
        onBlur={() => { space.current = false }}
        onContextMenu={(event) => event.preventDefault()}>
        {drawn && size[0] > 0 && size[1] > 0 ?
          <Stage width={size[0]} height={size[1]} listening={false}>
            <Layer listening={false}>
              <Shape sceneFunc={(context) => drawDots(context._context, ...size, palette)} />
            </Layer>
            <Layer listening={false}>
              <Group x={view.x} y={view.y} scaleX={view.scale} scaleY={view.scale}>
                {options.preview && <>
                  <Shape sceneFunc={(context) => drawScreen(context._context, drawn.preview.screen,
                    wantsBackground ? background ?? null : null,
                    context._context.getTransform().a / context.getCanvas().getPixelRatio(), palette)} />
                  {layers.scenes.map((layer) => <ReferenceLayer key={layer.name} layer={layer}
                    cache={cache} screen={drawn.preview.screen} options={options} />)}
                </>}
                <Shape sceneFunc={(context) => drawScene(context._context, drawn, rows, images,
                  options, palette, context.getCanvas().getPixelRatio(), selected, selection, handles, marquee, ghost, editText[2])} />
              </Group>
            </Layer>
          </Stage>
          : <div className="gf-canvas-status" role={error?.path === path ? 'alert' : 'status'}>
            {!path ? t[0] : error?.path === path ? error.message : t[1]}
          </div>}
      </div>
      <AtlasHost language={locale} />
    </section>
  )
}
