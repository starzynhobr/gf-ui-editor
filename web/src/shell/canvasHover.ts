// Controle sob o mouse no canvas (CanvasView.onHover → aqui → CanvasHoverTip). Store próprio para
// que só a dica redesenhe a cada movimento do mouse, não a casca inteira.
import { create } from 'zustand'
import type { CanvasHover } from '../canvas/CanvasView'

export const HOVER_TIP_FLAG = 'canvas_hover_tip'
/** Mouse parado este tempo sobre um controle: aparece a dica. */
export const HOVER_DELAY = 450
/** Acima desta velocidade (px/ms) o mouse está passando, não parando: a dica some. */
export const FAST_MOVE = 0.9

export interface HoverSample extends CanvasHover {
  time: number
}

export const useCanvasHover = create<{ hover: HoverSample | null }>(() => ({ hover: null }))

export function setCanvasHover(hover: CanvasHover | null): void {
  useCanvasHover.setState({ hover: hover && { ...hover, time: performance.now() } })
}

/** Velocidade do mouse entre duas amostras (px/ms). */
export function pointerSpeed(previous: HoverSample | null, next: HoverSample): number {
  if (!previous) return 0
  const elapsed = Math.max(1, next.time - previous.time)
  return Math.hypot(next.pointer[0] - previous.pointer[0], next.pointer[1] - previous.pointer[1]) / elapsed
}

/** Texto do controle para a dica: o do jogo, senão o literal do XML (amostras ficam de fora). */
export function hoverText(texts: HoverSample['element']['texts']): string {
  for (const mode of ['game', 'xml'] as const) {
    const entry = texts?.[mode]
    if (entry && 'value' in entry && entry.value.trim()) return entry.value.trim()
  }
  return ''
}

/** Posição da dica: abaixo e à direita do mouse, virando quando não cabe. */
export function tipPosition(pointer: [number, number], size: [number, number], viewport: [number, number]): [number, number] {
  const gap = 16
  let x = pointer[0] + gap
  let y = pointer[1] + gap + 4
  if (x + size[0] > viewport[0] - 8) x = pointer[0] - gap - size[0]
  if (y + size[1] > viewport[1] - 8) y = pointer[1] - gap - size[1]
  return [Math.max(8, x), Math.max(8, y)]
}
