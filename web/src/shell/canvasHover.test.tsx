// Dica do canvas: aparece com o mouse parado (atraso), some ao passar rápido ou sair, acompanha
// devagar no mesmo controle, respeita o liga/desliga e vira quando não cabe.
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CanvasElement } from '../bridge'

const bridge = vi.hoisted(() => ({ call: vi.fn(async () => undefined) }))
vi.mock('../bridge', async (original) => ({ ...(await original<typeof import('../bridge')>()), call: bridge.call }))

const { default: CanvasHoverTip, CanvasHoverToggle } = await import('./CanvasHoverTip')
const { HOVER_DELAY, HOVER_TIP_FLAG, hoverText, pointerSpeed, tipPosition, useCanvasHover } = await import('./canvasHover')
const { useUi } = await import('./uiState')
const { setLanguage } = await import('../i18n')

const element = (index: number, id: string): CanvasElement => ({
  index, id, parent: null, kind: 'button', ctrl_type: null, geometry: [10, 20, 80, 30], texture: null, uv: null,
  button_uvs: {}, progress_offset: null, visible: true, text_props: {}, button: true,
  texts: { off: { value: '' }, game: { value: 'Confirmar' }, xml: { value: 'OK' }, short: { sample: 'short' }, long: { sample: 'long' } },
  sample_text: '', sample_icon: null,
})

let now = 1000
function hover(index: number, pointer: [number, number], dt = 50) {
  now += dt
  act(() => useCanvasHover.setState({
    hover: { element: element(index, `Btn${index}`), box: [10, 20, 80, 30], rect: [100, 100, 80, 30], pointer, time: now },
  }))
}

beforeEach(() => {
  setLanguage('pt_BR')
  vi.useFakeTimers()
  useUi.setState({ flags: {}, loaded: true })
  useCanvasHover.setState({ hover: null })
  const viewport = document.createElement('div')
  viewport.className = 'gf-canvas-viewport'
  viewport.getBoundingClientRect = () => new DOMRect(0, 40, 800, 600)
  document.body.appendChild(viewport)
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  document.querySelector('.gf-canvas-viewport')?.remove()
})

describe('funções', () => {
  it('velocidade, texto e posição', () => {
    expect(pointerSpeed(null, { pointer: [0, 0], time: 0 } as never)).toBe(0)
    expect(pointerSpeed({ pointer: [0, 0], time: 0 } as never, { pointer: [30, 40], time: 10 } as never)).toBe(5)
    expect(hoverText(element(1, 'a').texts)).toBe('Confirmar')
    expect(hoverText({ ...element(1, 'a').texts, game: { value: ' ' } })).toBe('OK')
    expect(tipPosition([100, 100], [200, 80], [1000, 800])).toEqual([116, 120])
    expect(tipPosition([950, 760], [200, 80], [1000, 800])).toEqual([734, 664])
  })
})

describe('CanvasHoverTip', () => {
  it('contorno na hora, dica depois do atraso com WindowID, tipo, texto e X/Y/L×A', () => {
    render(<CanvasHoverTip />)
    hover(1, [120, 110])
    expect(screen.getByTestId('canvas-hover-outline')).toBeTruthy()
    expect(screen.queryByTestId('canvas-hover-tip')).toBeNull()
    act(() => void vi.advanceTimersByTime(HOVER_DELAY + 10))
    const tip = screen.getByTestId('canvas-hover-tip')
    expect(tip.textContent).toContain('Btn1')
    expect(tip.textContent).toContain('Botão')
    expect(tip.textContent).toContain('“Confirmar”')
    expect(tip.textContent).toContain('X 10')
    expect(tip.textContent).toContain('80 × 30')
    // devagar no mesmo controle: continua
    hover(1, [125, 112], 40)
    expect(screen.getByTestId('canvas-hover-tip')).toBeTruthy()
    // rápido: some tudo
    hover(2, [600, 400], 20)
    expect(screen.queryByTestId('canvas-hover-tip')).toBeNull()
    expect(screen.queryByTestId('canvas-hover-outline')).toBeNull()
    // saiu / arrastou (null): some
    act(() => void vi.advanceTimersByTime(HOVER_DELAY + 10))
    expect(screen.getByTestId('canvas-hover-tip').textContent).toContain('Btn2')
    act(() => useCanvasHover.setState({ hover: null }))
    expect(screen.queryByTestId('canvas-hover-tip')).toBeNull()
  })

  it('clique ou tecla em qualquer lugar e diálogo aberto tiram a dica', () => {
    render(<CanvasHoverTip />)
    hover(1, [120, 110])
    act(() => void vi.advanceTimersByTime(HOVER_DELAY + 10))
    expect(screen.getByTestId('canvas-hover-tip')).toBeTruthy()
    act(() => void window.dispatchEvent(new KeyboardEvent('keydown', { key: 'u', ctrlKey: true })))
    expect(screen.queryByTestId('canvas-hover-tip')).toBeNull()
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    document.body.appendChild(dialog)
    hover(2, [130, 115], 40)
    act(() => void vi.advanceTimersByTime(HOVER_DELAY + 10))
    expect(screen.queryByTestId('canvas-hover-tip')).toBeNull()
    dialog.remove()
  })

  it('outro controle devagar: espera de novo', () => {
    render(<CanvasHoverTip />)
    hover(1, [120, 110])
    act(() => void vi.advanceTimersByTime(HOVER_DELAY + 10))
    hover(2, [130, 115], 40)
    expect(screen.queryByTestId('canvas-hover-tip')).toBeNull()
    act(() => void vi.advanceTimersByTime(HOVER_DELAY + 10))
    expect(screen.getByTestId('canvas-hover-tip').textContent).toContain('Btn2')
  })

  it('desligada pelo botão da barra flutuante: nada aparece e grava a flag', () => {
    render(<><CanvasHoverToggle /><CanvasHoverTip /></>)
    const toggle = screen.getByTestId('canvas-hover-toggle')
    expect(toggle.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(toggle)
    expect(bridge.call).toHaveBeenCalledWith('ui_set_flag', HOVER_TIP_FLAG, false)
    hover(1, [120, 110])
    act(() => void vi.advanceTimersByTime(HOVER_DELAY + 10))
    expect(screen.queryByTestId('canvas-hover-tip')).toBeNull()
    expect(screen.queryByTestId('canvas-hover-outline')).toBeNull()
  })
})
