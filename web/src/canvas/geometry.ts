import type { CanvasDocument, CanvasPoint, CanvasRect } from '../bridge'
import type { Edit } from '../doc/store'
import type { sceneRows } from './drawScene'

type Rows = ReturnType<typeof sceneRows>
export type GeometryEdit = Extract<Edit, { field: 'geometry' }>
export type Axis = 'horizontal' | 'vertical'
export type Handle = { index: number; point: CanvasPoint; axes: CanvasPoint }

// Python's round, used by the classic scene when snapping to a pixel.
function pixel(value: number) {
  const lower = Math.floor(value)
  return value - lower === 0.5 && lower % 2 === 0 ? lower : Math.round(value)
}

export function contains([x, y, w, h]: CanvasRect, [px, py]: CanvasPoint) {
  return px >= x && py >= y && px <= x + w && py <= y + h
}

export function intersects([x, y, w, h]: CanvasRect, [bx, by, bw, bh]: CanvasRect) {
  return x <= bx + bw && x + w >= bx && y <= by + bh && y + h >= by
}

export function between([x, y]: CanvasPoint, [ax, ay]: CanvasPoint): CanvasRect {
  return [Math.min(x, ax), Math.min(y, ay), Math.abs(ax - x), Math.abs(ay - y)]
}

export function visibleRows(rows: Rows, hidden: number[], isolated: number | null) {
  const family = new Set<number>()
  if (isolated !== null) {
    const children = new Map<string, Rows>()
    for (const row of rows) {
      const parent = row.element.parent
      if (parent === null) continue
      if (!children.has(parent)) children.set(parent, [])
      children.get(parent)!.push(row)
    }
    const pending = [rows[isolated]]
    while (pending.length) {
      const row = pending.pop()
      if (!row || family.has(row.element.index)) continue
      family.add(row.element.index)
      for (const child of children.get(row.element.id) ?? []) pending.push(child)
    }
  }
  const hiddenSet = new Set(hidden)
  return rows.filter(({ element: { index } }) => !hiddenSet.has(index) && (isolated === null || family.has(index)))
}

export function resizeHandles(rows: Rows, selection: number[], locked: number[], frame: CanvasRect | null): Handle[] {
  const selected = new Set(selection)
  const blocked = new Set(locked)
  return rows.flatMap(({ element: { index }, box }) => {
    if (!selected.has(index) || blocked.has(index)) return []
    const [x, y, w, h] = (index === 0 && frame) || box
    const axes: CanvasPoint[] = index === 0 && frame
      ? [[-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1]]
      : [[1, 1]]
    return axes.map(([ax, ay]) => ({ index, axes: [ax, ay], point: [x + (ax + 1) * w / 2, y + (ay + 1) * h / 2] }))
  })
}

export function moves(doc: CanvasDocument, indexes: number[], [dx, dy]: CanvasPoint): GeometryEdit[] {
  return indexes.map((index) => {
    const before = doc.elements[index].geometry
    return {
      index, field: 'geometry', before,
      after: [pixel(before[0] + dx), pixel(before[1] + dy), before[2], before[3]],
    }
  })
}

export function resizes(
  doc: CanvasDocument, indexes: number[], handle: Handle, [dx, dy]: CanvasPoint,
  proportional: boolean, preview: boolean,
): GeometryEdit[] {
  const anchor = preview ? doc.frame_anchor_delta : null
  if (anchor && handle.index === 0) {
    const scale = (axis: number, offset: number) => axis ? 1 / (offset + Number(axis > 0) || axis) : 0
    dx *= scale(handle.axes[0], anchor[0])
    dy *= scale(handle.axes[1], anchor[1])
  }
  const group = indexes.length > 1
  const elements = indexes.map((index) => {
    const [x, y, w, h] = doc.elements[index].geometry
    return { index, x, y, w, h }
  })
  const left = Math.min(...elements.map(({ x }) => x))
  const top = Math.min(...elements.map(({ y }) => y))
  const width = Math.max(...elements.map(({ x, w }) => x + Math.max(1, w))) - left
  const height = Math.max(...elements.map(({ y, h }) => y + Math.max(1, h))) - top
  const minX = Math.max(1 / width, ...elements.flatMap(({ w }) => w > 0 ? [1 / w] : []))
  const minY = Math.max(1 / height, ...elements.flatMap(({ h }) => h > 0 ? [1 / h] : []))
  let sx = (width + dx) / width
  let sy = (height + dy) / height
  if (proportional) {
    const dominant = Math.abs(sx - 1) >= Math.abs(sy - 1) ? sx : sy
    sx = sy = Math.max(dominant, minX, minY)
  } else {
    sx = Math.max(sx, minX)
    sy = Math.max(sy, minY)
  }
  return elements.map(({ index, x, y, w, h }) => ({
    index, field: 'geometry', before: doc.elements[index].geometry,
    after: [
      pixel(left + (x - left) * sx), pixel(top + (y - top) * sy),
      group && !w ? 0 : Math.max(1, pixel(Math.max(1, w) * sx)),
      group && !h ? 0 : Math.max(1, pixel(Math.max(1, h) * sy)),
    ],
  }))
}

export function draftScene(doc: CanvasDocument, edits: GeometryEdit[], preview: boolean): CanvasDocument {
  const changed = new Map(edits.map((edit) => [edit.index, edit]))
  const root = changed.get(0)
  const anchored = preview && !!doc.preview.frame
  const rootOnly = root && edits.length === 1
  const moving = rootOnly && root.before[2] === root.after[2] && root.before[3] === root.after[3]
  const dx = moving ? root.after[0] - root.before[0] : 0
  const dy = moving ? root.after[1] - root.before[1] : 0
  const shift = ([x, y, w, h]: CanvasRect): CanvasRect => [x + dx, y + dy, w, h]
  let frame = doc.preview.frame
  if (anchored && frame && root && !moving) {
    const [ax, ay] = doc.frame_anchor_delta ?? [0, 0]
    const [x, y, w, h] = root.after
    frame = [x + pixel(ax * (w - frame[2])), y + pixel(ay * (h - frame[3])), w, h]
  }
  const elements = doc.elements.map((element) => ({
    ...element, geometry: changed.get(element.index)?.after ?? (moving ? shift(element.geometry) : element.geometry),
  }))
  const content = doc.preview.content
  if (!anchored || !content) return { ...doc, elements }
  const children = elements.slice(1).map((element) => {
    const [x, y, w, h] = element.geometry
    const [ox, oy] = doc.preview.offsets[element.index]
    return [x + ox, y + oy, Math.max(1, w), Math.max(1, h)]
  })
  const left = Math.min(...children.map(([x]) => x))
  const top = Math.min(...children.map(([, y]) => y))
  const right = Math.max(...children.map(([x, , w]) => x + w))
  const bottom = Math.max(...children.map(([, y, , h]) => y + h))
  return { ...doc, elements, preview: { ...doc.preview, frame, content: [left, top, right - left, bottom - top] } }
}
