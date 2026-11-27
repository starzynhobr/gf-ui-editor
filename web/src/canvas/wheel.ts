export type NavigationStyle = 'corel' | 'paintnet' | 'photoshop'

export type WheelAction = { kind: 'zoom'; zoomIn: boolean } | { kind: 'pan'; dx: number; dy: number }

type WheelInput = Pick<WheelEvent, 'deltaX' | 'deltaY' | 'deltaMode' | 'ctrlKey' | 'shiftKey' | 'altKey'>

const LINE = 16
const PAGE = 400

/** Same rules as the classic canvas (EditorView.wheelEvent): corel always zooms;
 * paintnet scrolls, Shift goes sideways, Ctrl zooms; photoshop scrolls, Ctrl or Shift
 * goes sideways, Alt zooms. */
export function wheelAction(style: NavigationStyle, event: WheelInput): WheelAction | null {
  const unit = event.deltaMode === 1 ? LINE : event.deltaMode === 2 ? PAGE : 1
  const x = event.deltaX * unit
  const y = event.deltaY * unit
  const delta = y || x
  if (!delta) return null
  const zoom = style === 'paintnet' ? event.ctrlKey : style === 'photoshop' ? event.altKey : true
  if (zoom) return { kind: 'zoom', zoomIn: delta < 0 }
  const sideways = style === 'paintnet' ? event.shiftKey : event.ctrlKey || event.shiftKey
  // Shift+wheel already arrives as deltaX in Chromium; a trackpad sends both axes.
  if (sideways) return { kind: 'pan', dx: -delta, dy: 0 }
  return { kind: 'pan', dx: -x, dy: -y }
}
