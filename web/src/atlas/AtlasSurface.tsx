import { useEffect, useRef, useState, type PointerEvent } from 'react'
import type { CanvasPoint, CanvasRect } from '../bridge'
import { clamp, cropBetween, handles, moveCrop, resizeCrop, type Handle } from './geometry'

type View = { x: number; y: number; scale: number }
type Gesture = { id: number; start: CanvasPoint; origin: CanvasPoint; crop?: CanvasRect; handle?: Handle; pan: boolean }
export type Frame = { mode: 'fit' | 'crop' | 'zoom'; crop?: CanvasRect; factor?: number }

function framed([x, y, w, h]: CanvasRect, width: number, height: number, max: number): View {
  const scale = Math.min((width - 32) / Math.max(1, w), (height - 32) / Math.max(1, h), max)
  const safeScale = Math.max(0.015625, scale)
  return { x: (width - w * safeScale) / 2 - x * safeScale, y: (height - h * safeScale) / 2 - y * safeScale, scale: safeScale }
}

function zoom(view: View, [x, y]: CanvasPoint, factor: number): View {
  const scale = clamp(view.scale * factor, 0.015625, 32)
  const ratio = scale / view.scale
  return { x: x - (x - view.x) * ratio, y: y - (y - view.y) * ratio, scale }
}

export function AtlasSurface({ bitmap, label, cut, editing, frame, onCrop }: {
  bitmap: ImageBitmap | null | undefined
  label: string
  cut?: CanvasRect
  editing: boolean
  frame: Frame
  onCrop: (crop: CanvasRect) => void
}) {
  const viewport = useRef<HTMLDivElement>(null)
  const image = useRef<HTMLCanvasElement>(null)
  const gesture = useRef<Gesture | null>(null)
  const draftRef = useRef<CanvasRect | undefined>(undefined)
  const [draft, setDraft] = useState<CanvasRect>()
  const [size, setSize] = useState<CanvasPoint>([0, 0])
  const [view, setView] = useState<View>({ x: 0, y: 0, scale: 1 })
  const width = bitmap?.width ?? 0
  const height = bitmap?.height ?? 0

  useEffect(() => {
    const context = image.current?.getContext('2d')
    if (bitmap && context) {
      context.clearRect(0, 0, bitmap.width, bitmap.height)
      context.drawImage(bitmap, 0, 0)
    }
  }, [bitmap])

  useEffect(() => {
    const node = viewport.current!
    const observer = new ResizeObserver(() => setSize([node.clientWidth, node.clientHeight]))
    observer.observe(node)
    const wheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = node.getBoundingClientRect()
      setView((old) => zoom(old, [event.clientX - rect.left, event.clientY - rect.top], event.deltaY < 0 ? 1.2 : 1 / 1.2))
    }
    node.addEventListener('wheel', wheel, { passive: false })
    return () => {
      observer.disconnect()
      node.removeEventListener('wheel', wheel)
    }
  }, [])

  useEffect(() => {
    if (!width || !height || !size[0] || !size[1]) return
    switch (frame.mode) {
      case 'zoom':
        setView((old) => zoom(old, [size[0] / 2, size[1] / 2], frame.factor ?? 1))
        break
      case 'crop':
        setView(frame.crop && frame.crop[2] && frame.crop[3]
          ? framed(frame.crop, ...size, 12)
          : framed([0, 0, width, height], ...size, 8))
        break
      case 'fit':
        setView(framed([0, 0, width, height], ...size, 8))
    }
  }, [frame, width, height, size])

  function point(event: PointerEvent<HTMLDivElement>): CanvasPoint {
    const rect = event.currentTarget.getBoundingClientRect()
    return [(event.clientX - rect.left - view.x) / view.scale, (event.clientY - rect.top - view.y) / view.scale]
  }

  function start(event: PointerEvent<HTMLDivElement>) {
    if (!bitmap || gesture.current || ![0, 1, 2].includes(event.button)) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    const target = event.target as HTMLElement
    const handle = target.dataset.edge as Handle | undefined
    const pan = !editing || event.button !== 0 || event.altKey
    gesture.current = {
      id: event.pointerId, start: [event.clientX, event.clientY],
      origin: pan ? [view.x, view.y] : point(event),
      crop: target.closest('.gf-atlas-cut') ? cut : undefined,
      handle, pan,
    }
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    const active = gesture.current
    if (!active || active.id !== event.pointerId) return
    const [dx, dy] = [event.clientX - active.start[0], event.clientY - active.start[1]]
    if (active.pan) {
      setView((old) => ({ ...old, x: active.origin[0] + dx, y: active.origin[1] + dy }))
      return
    }
    if (!draftRef.current && Math.hypot(dx, dy) < 2) return
    const textureSize: CanvasPoint = [width, height]
    const end = point(event)
    const crop = active.crop
      ? active.handle
        ? resizeCrop(active.crop, active.handle, end, textureSize)
        : moveCrop(active.crop, [dx / view.scale, dy / view.scale], textureSize)
      : cropBetween(active.origin, end, textureSize)
    draftRef.current = crop
    setDraft(crop)
  }

  function finish(event: PointerEvent<HTMLDivElement>, commit: boolean) {
    if (gesture.current?.id !== event.pointerId) return
    if (commit && draftRef.current) onCrop(draftRef.current)
    gesture.current = null
    draftRef.current = undefined
    setDraft(undefined)
  }

  const activeCut = draft ?? cut
  return (
    <div ref={viewport} className="gf-atlas-surface gf-atlas-checker" data-testid="atlas-surface"
      data-editing={editing} onPointerDown={start} onPointerMove={move}
      onPointerUp={(event) => finish(event, true)}
      onPointerCancel={(event) => finish(event, false)} onLostPointerCapture={(event) => finish(event, false)}
      onContextMenu={(event) => event.preventDefault()}>
      {bitmap ? <>
        <canvas ref={image} width={width} height={height}
          style={{ left: view.x, top: view.y, width: width * view.scale, height: height * view.scale }} />
        {activeCut && activeCut[2] > 0 && activeCut[3] > 0 &&
          <div className="gf-atlas-cut" style={{
            left: view.x + activeCut[0] * view.scale, top: view.y + activeCut[1] * view.scale,
            width: activeCut[2] * view.scale, height: activeCut[3] * view.scale,
          }}>
            {editing && handles.map((handle) => <span key={handle} data-edge={handle} />)}
          </div>}
        <output className="gf-atlas-magnification">{Math.round(view.scale * 100)}%</output>
      </> : <p className="gf-atlas-placeholder" role={bitmap === null ? 'alert' : 'status'}>{label}</p>}
    </div>
  )
}
