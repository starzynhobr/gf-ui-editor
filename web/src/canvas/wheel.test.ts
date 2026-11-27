import { describe, expect, it } from 'vitest'
import { wheelAction } from './wheel'

const wheel = (deltaY: number, keys: Partial<{ ctrlKey: boolean; shiftKey: boolean; altKey: boolean; deltaX: number; deltaMode: number }> = {}) => ({
  deltaX: 0, deltaMode: 0, ctrlKey: false, shiftKey: false, altKey: false, deltaY, ...keys,
})

describe('wheelAction', () => {
  it('corel always zooms', () => {
    expect(wheelAction('corel', wheel(-100))).toEqual({ kind: 'zoom', zoomIn: true })
    expect(wheelAction('corel', wheel(100, { shiftKey: true }))).toEqual({ kind: 'zoom', zoomIn: false })
  })

  it('paintnet scrolls, Shift goes sideways, Ctrl zooms', () => {
    expect(wheelAction('paintnet', wheel(100))).toEqual({ kind: 'pan', dx: -0, dy: -100 })
    expect(wheelAction('paintnet', wheel(100, { shiftKey: true }))).toEqual({ kind: 'pan', dx: -100, dy: 0 })
    expect(wheelAction('paintnet', wheel(0, { shiftKey: true, deltaX: 100 }))).toEqual({ kind: 'pan', dx: -100, dy: 0 })
    expect(wheelAction('paintnet', wheel(-100, { ctrlKey: true }))).toEqual({ kind: 'zoom', zoomIn: true })
    expect(wheelAction('paintnet', wheel(-100, { altKey: true }))).toEqual({ kind: 'pan', dx: -0, dy: 100 })
  })

  it('photoshop scrolls, Ctrl or Shift goes sideways, Alt zooms', () => {
    expect(wheelAction('photoshop', wheel(100))).toEqual({ kind: 'pan', dx: -0, dy: -100 })
    expect(wheelAction('photoshop', wheel(100, { ctrlKey: true }))).toEqual({ kind: 'pan', dx: -100, dy: 0 })
    expect(wheelAction('photoshop', wheel(-100, { altKey: true }))).toEqual({ kind: 'zoom', zoomIn: true })
  })

  it('turns line deltas into pixels and ignores empty events', () => {
    expect(wheelAction('paintnet', wheel(3, { deltaMode: 1 }))).toEqual({ kind: 'pan', dx: -0, dy: -48 })
    expect(wheelAction('paintnet', wheel(0))).toBeNull()
  })
})
