import type { CanvasPoint, CanvasRect } from '../bridge'

export const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value))
export const handles = ['nw', 'n', 'ne', 'w', 'e', 'sw', 's', 'se'] as const
export type Handle = typeof handles[number]

export function cropBetween(start: CanvasPoint, end: CanvasPoint, [width, height]: CanvasPoint): CanvasRect {
  const left = clamp(Math.floor(Math.min(start[0], end[0])), 0, width - 1)
  const top = clamp(Math.floor(Math.min(start[1], end[1])), 0, height - 1)
  const right = clamp(Math.ceil(Math.max(start[0], end[0])), left + 1, width)
  const bottom = clamp(Math.ceil(Math.max(start[1], end[1])), top + 1, height)
  return [left, top, right - left, bottom - top]
}

export function resizeCrop(
  [x, y, width, height]: CanvasRect, handle: Handle, [px, py]: CanvasPoint, size: CanvasPoint,
): CanvasRect {
  return cropBetween(
    [handle.includes('w') ? px : x, handle.includes('n') ? py : y],
    [handle.includes('e') ? px : x + width, handle.includes('s') ? py : y + height],
    size,
  )
}

export function moveCrop([x, y, width, height]: CanvasRect, [dx, dy]: CanvasPoint, size: CanvasPoint): CanvasRect {
  return [
    clamp(x + Math.round(dx), 0, size[0] - width),
    clamp(y + Math.round(dy), 0, size[1] - height),
    width, height,
  ]
}
