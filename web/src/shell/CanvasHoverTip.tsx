// Dica ao parar o mouse sobre um controle no canvas: WindowID, tipo, texto (se houver) e
// X, Y, L × A; o contorno do controle fica destacado. Desenho por cima do canvas (DOM fixo), sem
// mexer no Konva: os dados vêm do CanvasView.onHover. Some ao arrastar, rolar ou passar rápido.
// Liga/desliga no botão (i) da barra flutuante ou em Configurações → Editor (flag canvas_hover_tip).
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { kindLabel } from '../elements/kinds'
import { useT } from '../i18n'
import { Icon } from '../ui/Icon'
import { FAST_MOVE, HOVER_DELAY, HOVER_TIP_FLAG, hoverText, pointerSpeed, setCanvasHover, tipPosition, useCanvasHover, type HoverSample } from './canvasHover'
import { setFlag, useFlag } from './uiState'

export function CanvasHoverToggle() {
  const t = useT()
  const enabled = useFlag(HOVER_TIP_FLAG, true)
  const label = t('Dica ao passar o mouse')
  return (
    <button aria-pressed={enabled} aria-label={label} title={label} data-testid="canvas-hover-toggle" onClick={() => setFlag(HOVER_TIP_FLAG, !enabled)}>
      <Icon name="info" size={14} />
    </button>
  )
}

export default function CanvasHoverTip() {
  const t = useT()
  const enabled = useFlag(HOVER_TIP_FLAG, true)
  const hover = useCanvasHover((state) => state.hover)
  const [tip, setTip] = useState<HoverSample | null>(null)
  const [outline, setOutline] = useState<HoverSample | null>(null)
  const [position, setPosition] = useState<[number, number] | null>(null)
  const previous = useRef<HoverSample | null>(null)
  const shown = useRef<HoverSample | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    window.clearTimeout(timer.current)
    const before = previous.current
    previous.current = hover
    const show = (value: HoverSample | null) => {
      shown.current = value
      setTip(value)
    }
    if (!enabled || !hover) {
      show(null)
      setOutline(null)
      return
    }
    const fast = pointerSpeed(before, hover) > FAST_MOVE
    if (fast) {
      show(null)
      setOutline(null)
    } else {
      setOutline(hover)
      // Já aberta sobre o mesmo controle e o mouse andando devagar: acompanha.
      if (shown.current?.element.index === hover.element.index) {
        show(hover)
        return
      }
      show(null)
    }
    timer.current = window.setTimeout(() => {
      setOutline(hover)
      show(hover)
    }, HOVER_DELAY)
    return () => window.clearTimeout(timer.current)
  }, [hover, enabled])

  // Clique, tecla, roda ou a janela perdendo o foco em qualquer lugar: a dica sai (ex.: um atalho
  // abre um diálogo com o mouse parado no canvas).
  useEffect(() => {
    const hide = () => {
      if (useCanvasHover.getState().hover) setCanvasHover(null)
    }
    const events = ['pointerdown', 'keydown', 'wheel', 'blur'] as const
    for (const name of events) window.addEventListener(name, hide, true)
    return () => {
      for (const name of events) window.removeEventListener(name, hide, true)
    }
  }, [])

  useLayoutEffect(() => {
    if (!tip || !box.current) {
      setPosition(null)
      return
    }
    const { offsetWidth, offsetHeight } = box.current
    setPosition(tipPosition(tip.pointer, [offsetWidth, offsetHeight], [window.innerWidth, window.innerHeight]))
  }, [tip])

  // Com um diálogo aberto, o canvas está por baixo: nada de dica.
  if (!enabled || (!tip && !outline) || document.querySelector('dialog[open], [role=dialog]')) return null
  const viewport = document.querySelector<HTMLElement>('.gf-canvas-viewport')?.getBoundingClientRect()
  const frame = outline && viewport
  const element = tip?.element
  const text = element ? hoverText(element.texts) : ''
  const [x, y, width, height] = element?.geometry ?? [0, 0, 0, 0]
  return (
    <>
      {frame && (
        <div
          className="gf-hover-frame"
          style={{ left: viewport.left, top: viewport.top, width: viewport.width, height: viewport.height }}
          aria-hidden
        >
          <div
            className="gf-hover-outline"
            data-testid="canvas-hover-outline"
            style={{
              left: outline.rect[0] - viewport.left,
              top: outline.rect[1] - viewport.top,
              width: Math.max(1, outline.rect[2]),
              height: Math.max(1, outline.rect[3]),
            }}
          />
        </div>
      )}
      {element && (
        <div
          ref={box}
          className="gf-hover-tip"
          role="tooltip"
          data-testid="canvas-hover-tip"
          style={position ? { left: position[0], top: position[1] } : { left: -9999, top: -9999 }}
        >
          <div className="flex items-center gap-2">
            <span className="font-mono font-semibold text-bright">{element.id || t('(sem WindowID)')}</span>
            <span className="gf-hover-kind">{kindLabel(element.kind, element.ctrl_type)}</span>
          </div>
          {text && <div className="gf-hover-text" title={text}>“{text}”</div>}
          <div className="gf-hover-geometry font-mono">
            <span><b>X</b> {x}</span>
            <span><b>Y</b> {y}</span>
            <span><b>{t('L   ').trim()}×{t('A   ').trim()}</b> {width} × {height}</span>
          </div>
        </div>
      )}
    </>
  )
}
