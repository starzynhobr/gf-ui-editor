import Konva from '../web/node_modules/konva/lib/Core.js'
import { createRoot } from '../web/node_modules/react-dom/client.js'
import { flushSync } from '../web/node_modules/react-dom/index.js'
import { createElement } from '../web/node_modules/react/index.js'
import { openCanvasDocument, type CanvasElement } from '../web/src/bridge'
import CanvasView from '../web/src/canvas/CanvasView'
import DdsProbe from './canvas_compare_dds?worker&inline'

Konva.pixelRatio = 1
const root = createRoot(document.getElementById('root')!)
let selected: CanvasElement | null = null

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
  const click = (caption: string) => {
    const button = [...document.querySelectorAll('button')].find((button) => button.textContent === caption)
    if (!button) throw new Error('Missing canvas control: ' + caption)
    button.click()
  }
  click('Contornos')
  if (doc.elements.some((element) => element.sample_text || element.sample_icon)) click('Personagem')
  if (preview) {
    click('Tela')
    await new Promise(requestAnimationFrame)
    if (!background) click('Fundo')
    const select = document.querySelector<HTMLSelectElement>('select[aria-label="Texto"]')!
    select.value = 'game'
    select.dispatchEvent(new Event('change', { bubbles: true }))
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
  const pointer = (type: string, dx = 0, dy = 0) => viewport.dispatchEvent(new PointerEvent(type, {
    clientX: rect.left + x + dx, clientY: rect.top + y + dy, pointerId: 1, bubbles: true,
  }))
  const commit = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  pointer('pointerdown')
  pointer('pointerup')
  await commit()
  if (selected?.id !== '1') throw new Error('Canvas selection did not report the element')
  const initial = group.position()
  const scale = group.scaleX()
  pointer('pointerdown')
  pointer('pointermove', 20, 12)
  pointer('pointerup', 20, 12)
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
  viewport.closest('section')!.querySelector<HTMLButtonElement>('button:last-child')!.click()
  await commit()
  if (group.x() !== initial.x || group.y() !== initial.y || group.scaleX() !== scale) throw new Error('Canvas fit did not restore framing')
  return true
}

Object.assign(window, {
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
