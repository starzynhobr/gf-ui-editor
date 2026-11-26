import Konva from '../web/node_modules/konva/lib/Core.js'
import { createRoot } from '../web/node_modules/react-dom/client.js'
import { flushSync } from '../web/node_modules/react-dom/index.js'
import { createElement } from '../web/node_modules/react/index.js'
import { openCanvasDocument, type CanvasElement } from '../web/src/bridge'
import { openAtlas, previewTexture } from '../web/src/atlas'
import CanvasView from '../web/src/canvas/CanvasView'
import { previewSave, redo, save, select, setHidden, setIsolated, setLocked, undo, useDoc } from '../web/src/doc/store'
import DdsProbe from './canvas_compare_dds?worker&inline'
import '../web/src/index.css'

Konva.pixelRatio = 1
const root = createRoot(document.getElementById('root')!)
let selected: CanvasElement | null = null
root.render(createElement(CanvasView, { path: null }))

async function setToggle(caption: string, pressed: boolean) {
  const button = [...document.querySelectorAll<HTMLButtonElement>('.gf-canvas-toolbar button')]
    .find((button) => button.textContent === caption)
  if (!button) throw new Error('Missing canvas control: ' + caption)
  const deadline = performance.now() + 5000
  if (button.ariaPressed !== String(pressed)) button.click()
  while (button.disabled || button.ariaPressed !== String(pressed)) {
    if (performance.now() > deadline) throw new Error('Canvas control timed out: ' + caption)
    await new Promise(requestAnimationFrame)
  }
}

async function open(path: string, preview: boolean, background: boolean) {
  const doc = await openCanvasDocument(path, [1024, 768])
  flushSync(() => root.render(createElement(CanvasView, {
    key: `${path}:${preview}:${background}`, path, resolution: [1024, 768],
    onSelect: (element) => { selected = element },
  })))
  const timeout = performance.now() + 10000
  while ((!Konva.stages[0]?.width() || !document.querySelector('.gf-canvas-toolbar')) && performance.now() < timeout) {
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  const change = async (caption: string, value: string) => {
    const select = document.querySelector<HTMLSelectElement>(`select[aria-label="${caption}"]`)!
    if (select.value === value) return
    select.value = value
    select.dispatchEvent(new Event('change', { bubbles: true }))
    const deadline = performance.now() + 5000
    while (select.value !== value || select.disabled) {
      if (performance.now() > deadline) throw new Error('Canvas control timed out: ' + caption)
      await new Promise(requestAnimationFrame)
    }
  }
  await setToggle('Contornos', false)
  await setToggle('IDs', false)
  await change('Tela', preview ? 'game' : 'off')
  await change('Fundo', background ? 'builtin' : 'none')
  await change('Texto', preview ? 'game' : 'off')
  if ((preview && doc.preview.drawn) || doc.elements.some((element) => element.sample_text || element.sample_icon)) {
    await setToggle('Personagem', false)
  }
  await new Promise(requestAnimationFrame)
  const maxWait = performance.now() + 5000
  while (document.querySelector('.gf-canvas[aria-busy="true"]')) {
    if (performance.now() >= maxWait) throw new Error('Canvas textures timed out')
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  await new Promise(requestAnimationFrame)
  const missing = document.querySelector<HTMLOutputElement>('.gf-canvas-toolbar output')?.title.split(', ') ?? []
  return {
    missing,
    elements: doc.elements.length,
    textures: new Set(doc.elements.flatMap((element) => element.texture?.toLowerCase() ?? [])).size,
  }
}

function positionStage(x: number, y: number) {
  const stage = Konva.stages[0]
  const group = stage.findOne('Group')!
  group.position({ x, y })
  group.scale({ x: 1, y: 1 })
  stage.draw()
  return stage
}

async function checkControls() {
  const viewport = document.querySelector<HTMLDivElement>('.gf-canvas-viewport')!
  const group = Konva.stages[0].findOne('Group')!
  const rect = viewport.getBoundingClientRect()
  const x = Math.round(group.x() + 8 * group.scaleX())
  const y = Math.round(group.y() + 8 * group.scaleY())
  // Synthetic PointerEvents have no native pointer to capture.
  viewport.setPointerCapture = () => {}
  const pointer = (type: string, dx = 0, dy = 0, button = 0) => viewport.dispatchEvent(new PointerEvent(type, {
    clientX: rect.left + x + dx, clientY: rect.top + y + dy, pointerId: 1, bubbles: true, button,
  }))
  const commit = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  pointer('pointerdown')
  pointer('pointerup')
  await commit()
  if (selected?.id !== '1') throw new Error('Canvas selection did not report the element')
  const initial = group.position()
  const scale = group.scaleX()
  pointer('pointerdown', 0, 0, 1)
  pointer('pointermove', 20, 12, 1)
  pointer('pointerup', 20, 12, 1)
  await commit()
  if (group.x() !== initial.x + 20 || group.y() !== initial.y + 12) throw new Error('Canvas pan did not follow the pointer')
  const beforeX = (x - group.x()) / scale
  const beforeY = (y - group.y()) / scale
  viewport.dispatchEvent(new WheelEvent('wheel', {
    clientX: rect.left + x, clientY: rect.top + y, deltaY: -120, cancelable: true,
  }))
  await commit()
  const zoom = group.scaleX()
  if (zoom <= scale || Math.abs((x - group.x()) / zoom - beforeX) > 0.01 ||
      Math.abs((y - group.y()) / zoom - beforeY) > 0.01) throw new Error('Canvas zoom moved the anchor')
  viewport.closest('section')!.querySelector<HTMLButtonElement>('[data-testid="canvas-fit"]')!.click()
  await commit()
  if (group.x() !== initial.x || group.y() !== initial.y || group.scaleX() !== scale) throw new Error('Canvas fit did not restore framing')

  await setToggle('IDs', true)
  await commit()
  const context = CanvasRenderingContext2D.prototype
  const { fillText, strokeRect } = context
  const fonts: string[] = []
  const strokes: number[] = []
  context.fillText = function (text, ...args) {
    if (text.startsWith('1 · ')) fonts.push(`${this.font} × ${this.getTransform().a}`)
    fillText.call(this, text, ...args)
  }
  context.strokeRect = function (...args) {
    strokes.push(this.lineWidth * this.getTransform().a)
    strokeRect.call(this, ...args)
  }
  const stage = Konva.stages[0]
  try {
    group.position({ x: 20, y: 20 })
    group.scale({ x: 1, y: 1 })
    stage.draw()
    group.scale({ x: .2, y: .2 })
    stage.draw()
  } finally {
    context.fillText = fillText
    context.strokeRect = strokeRect
  }
  if (fonts.length !== 2 || fonts.some((font) => font !== '12px Arial × 1')) {
    throw new Error('IDs did not retain their screen font: ' + fonts.join(', '))
  }
  if (strokes.length !== 2 || strokes.some((width) => Math.abs(width - 2) > .001)) {
    throw new Error('Selection outlines did not retain their screen thickness: ' + strokes.join(', '))
  }
  await setToggle('IDs', false)

  const html = document.documentElement
  const theme = document.createElement('style')
  theme.textContent = 'html[data-theme="comparison"] { --color-canvas-surface: rgb(21, 43, 65); }'
  document.head.append(theme)
  try {
    html.dataset.theme = 'comparison'
    await commit()
    const dots = stage.getLayers()[0].getCanvas()._canvas.getContext('2d')!
    if (dots.getImageData(0, 0, 1, 1).data.join(',') !== '21,43,65,255') {
      throw new Error('Canvas did not redraw after the theme changed')
    }
  } finally {
    delete html.dataset.theme
    theme.remove()
    await commit()
  }
  return true
}

async function editOpen(path: string, preview: boolean) {
  await open(path, preview, false)
  const doc = useDoc.getState().doc!
  const [, , width, height] = preview ? doc.preview.screen : doc.bounds
  const viewport = document.querySelector<HTMLDivElement>('.gf-canvas-viewport')!
  Object.assign(viewport.style, { flex: 'none', width: `${width + 40}px`, height: `${height + 44}px` })
  for (let attempt = 0; attempt < 30; attempt++) {
    await new Promise(requestAnimationFrame)
    if (Konva.stages[0].findOne('Group')!.scaleX() === 1) return true
  }
  throw new Error('Editing fixture did not reach 1:1 zoom')
}

Object.assign(window, {
  canvasEdit: {
    open: editOpen,
    state: useDoc.getState,
    select, setHidden, setLocked, setIsolated, undo, redo, save, previewSave,
    openAtlas, previewTexture,
    atlasPoint(x: number, y: number) {
      const image = document.querySelector<HTMLCanvasElement>('.gf-atlas-surface > canvas')!
      const rect = image.getBoundingClientRect()
      return [rect.left + x * rect.width / image.width, rect.top + y * rect.height / image.height]
    },
    point(x: number, y: number) {
      const group = Konva.stages[0].findOne('Group')!
      const rect = document.querySelector('.gf-canvas-viewport')!.getBoundingClientRect()
      return [rect.left + group.x() + x, rect.top + group.y() + y]
    },
  },
  canvasCompare: {
    open,
    checkControls,
    ddsHashes: (files: [base: string, file: string][]) => new Promise((resolve, reject) => {
      const worker = new DdsProbe()
      worker.onmessage = ({ data }) => {
        worker.terminate()
        if (data.error) reject(new Error(data.error))
        else resolve(data.hashes)
      }
      worker.onerror = (error) => { worker.terminate(); reject(error.message) }
      worker.postMessage(files)
    }),
    capture(x: number, y: number, width: number, height: number) {
      return positionStage(-x, -y).toDataURL({ width, height, pixelRatio: 1 })
    },
    pixel(x: number, y: number) {
      const ctx = positionStage(0, 0).toCanvas({ width: 16, height: 16, pixelRatio: 1 }).getContext('2d')!
      return [...ctx.getImageData(x, y, 1, 1).data]
    },
    panDrawTime() {
      const times = Array.from({ length: 60 }, (_, i) => {
        const start = performance.now()
        positionStage(-i, -i)
        return performance.now() - start
      }).sort((a, b) => a - b)
      return times[56]
    },
  },
})
