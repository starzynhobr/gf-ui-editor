// Store de documento falso para os testes da casca: implementa o contrato de doc/store.ts
// em memória (edições aplicadas direto no documento, desfazer por lotes, diff fixo).
import { vi } from 'vitest'
import { create } from 'zustand'
import type { CanvasDocument, CanvasElement } from '../bridge'
import type { DocState, Edit } from '../doc/store'

export type { DocState, Edit }

const initial: DocState = {
  path: null,
  doc: null,
  selection: [],
  hidden: [],
  locked: [],
  isolated: null,
  dirty: false,
  canUndo: false,
  canRedo: false,
  error: null,
  externalChange: null,
}

export const useDoc = create<DocState>(() => ({ ...initial }))

let undoStack: Edit[][] = []
let redoStack: Edit[][] = []

function apply(edits: Edit[], reverse = false) {
  const doc = useDoc.getState().doc
  if (!doc) return
  const elements = doc.elements.map((element) => ({ ...element, text_props: { ...element.text_props } }))
  for (const edit of edits) {
    const element = elements[edit.index] as CanvasElement & { font_attrs?: Record<string, string> }
    const value = reverse ? edit.before : edit.after
    if (edit.field === 'geometry') element.geometry = value as CanvasElement['geometry']
    else if (edit.field === 'texture') element.texture = value as string | null
    else if (edit.field === 'uv') element.uv = value as CanvasElement['uv']
    else if (edit.field === 'font') element.text_props[edit.name] = value as string
  }
  useDoc.setState({ doc: { ...doc, elements } })
}

function sync() {
  useDoc.setState({ canUndo: undoStack.length > 0, canRedo: redoStack.length > 0, dirty: undoStack.length > 0 })
}

export const calls = {
  applyEdits: vi.fn(),
  save: vi.fn(),
  revert: vi.fn(),
  openDoc: vi.fn(),
}

export function loadMockDocument(path: string, doc: CanvasDocument): void {
  undoStack = []
  redoStack = []
  useDoc.setState({ ...initial, path, doc })
}

export function resetMock(): void {
  undoStack = []
  redoStack = []
  useDoc.setState({ ...initial })
  Object.values(calls).forEach((fn) => fn.mockReset())
}

export const openDoc = async (path: string | null) => {
  calls.openDoc(path)
  if (path == null) useDoc.setState({ ...initial })
}

export const select = (indexes: number[], mode: 'replace' | 'add' | 'toggle' = 'replace') => {
  const current = useDoc.getState().selection
  let next: number[]
  if (mode === 'replace') next = indexes
  else if (mode === 'add') next = [...current, ...indexes.filter((index) => !current.includes(index))]
  else {
    next = [...current]
    for (const index of indexes) next = next.includes(index) ? next.filter((item) => item !== index) : [...next, index]
  }
  useDoc.setState({ selection: next })
}

export const applyEdits = async (edits: Edit[], label: string) => {
  calls.applyEdits(edits, label)
  apply(edits)
  undoStack.push(edits)
  redoStack = []
  sync()
}

export const undo = async () => {
  const edits = undoStack.pop()
  if (edits) {
    apply([...edits].reverse(), true)
    redoStack.push(edits)
  }
  sync()
}

export const redo = async () => {
  const edits = redoStack.pop()
  if (edits) {
    apply(edits)
    undoStack.push(edits)
  }
  sync()
}

export const previewSave = async () => (useDoc.getState().dirty ? '--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new' : '')

export const save = async () => {
  calls.save()
  undoStack = []
  redoStack = []
  sync()
}

export const revert = async () => {
  calls.revert()
  while (undoStack.length) await undo()
  redoStack = []
  sync()
}

export const setHidden = (indexes: number[], hidden: boolean) =>
  useDoc.setState((state) => ({ hidden: hidden ? [...new Set([...state.hidden, ...indexes])] : state.hidden.filter((i) => !indexes.includes(i)) }))
export const setLocked = (indexes: number[], locked: boolean) =>
  useDoc.setState((state) => ({ locked: locked ? [...new Set([...state.locked, ...indexes])] : state.locked.filter((i) => !indexes.includes(i)) }))
export const setIsolated = (index: number | null) => useDoc.setState({ isolated: index })

// ---- documento de exemplo -----------------------------------------------------------------
function element(index: number, id: string, parent: string | null, kind: string, extra: Partial<CanvasElement> = {}): CanvasElement {
  return {
    index,
    id,
    parent,
    kind,
    ctrl_type: kind === 'button' ? '5' : null,
    geometry: [index * 10, index * 5, 100, 20],
    texture: 'Panel.dds',
    uv: [0, 0, 100, 20],
    button_uvs: {},
    progress_offset: null,
    visible: true,
    text_props: {},
    button: kind === 'button',
    texts: { off: { value: '' }, game: { value: '' }, xml: { value: '' }, short: { sample: 'short' }, long: { sample: 'long' } },
    sample_text: '',
    sample_icon: null,
    ...extra,
  }
}

export function sampleDocument(): CanvasDocument {
  return {
    elements: [
      element(0, '1', null, 'window'),
      element(1, '10', '1', 'panel'),
      element(2, '11', '10', 'button', { text_props: { FontColor: '65535', FontStyle: '1', TextAlign: '1', MultiLine: '0' } }),
      element(3, '12', '1', 'image', { texture: 'Other.dds' }),
    ],
    bounds: [0, 0, 400, 300],
    preview: { screen: [0, 0, 1024, 768], root_on_screen: [0, 0], offsets: [], frame: null, content: null, drawn: null, background: null },
  }
}
