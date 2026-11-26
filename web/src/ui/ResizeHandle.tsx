// Divisor arrastável entre um painel lateral e o centro. Duplo clique volta à largura padrão.
import { useRef, useState } from 'react'
import { PANEL_LIMITS, panelWidth, setPanelWidth, useUi, type PanelSide } from '../shell/uiState'

export function ResizeHandle({ side }: { side: PanelSide }) {
  const layout = useUi((state) => state.layout)
  const [dragging, setDragging] = useState(false)
  const start = useRef<{ x: number; width: number } | null>(null)

  const onPointerDown = (event: React.PointerEvent) => {
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    start.current = { x: event.clientX, width: panelWidth(side, layout) }
    setDragging(true)
  }
  const onPointerMove = (event: React.PointerEvent) => {
    if (!start.current) return
    const delta = event.clientX - start.current.x
    setPanelWidth(side, start.current.width + (side === 'left' ? delta : -delta))
  }
  const onPointerUp = (event: React.PointerEvent) => {
    event.currentTarget.releasePointerCapture(event.pointerId)
    start.current = null
    setDragging(false)
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={side === 'left' ? 'Largura do painel esquerdo' : 'Largura do painel direito'}
      data-testid={`resize-${side}`}
      className={`gf-resize ${dragging ? 'is-dragging' : ''}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={() => setPanelWidth(side, PANEL_LIMITS[side].initial)}
    />
  )
}
