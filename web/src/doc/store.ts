// Documento aberto: estado compartilhado entre canvas, árvore de elementos e painel.
// CONTRATO DO BLOCO 2 (vault/web-bridge.md). Dono da implementação: canvas (Codex).
// A casca (Claude 2) só usa as funções e o hook daqui; não muda as assinaturas.
//
// Fonte da verdade: o documento em memória no Python (web_api/document.py). Toda edição
// passa por applyEdits -> Python (doc_edit) e volta como documento atualizado; desfazer e
// refazer reaplicam o lote inverso pelo mesmo caminho. Salvar grava pelo Python.
import { create } from 'zustand'
import type { ShellState } from '../api'
import { call, type CanvasDocument, type CanvasPoint, type CanvasPreference, type CanvasPreferences, type CanvasRect } from '../bridge'

export type Edit =
  | { index: number; field: 'geometry'; before: CanvasRect; after: CanvasRect }
  | { index: number; field: 'uv'; name?: string; before: CanvasRect | null; after: CanvasRect | null }
  | { index: number; field: 'texture'; before: string | null; after: string | null }
  | { index: number; field: 'font'; name: string; before: string; after: string }

export interface DocState {
  path: string | null
  doc: CanvasDocument | null
  /** Índices selecionados; o primeiro é o "principal" (o do painel). */
  selection: number[]
  /** Só do editor (não vão para o XML). */
  hidden: number[]
  locked: number[]
  isolated: number | null
  dirty: boolean
  canUndo: boolean
  canRedo: boolean
  undoLabel?: string | null
  redoLabel?: string | null
  /** Texto do último erro de edição/salvar, para a casca mostrar. */
  error: string | null
}

export const useDoc = create<DocState>(() => ({
  path: null,
  doc: null,
  selection: [],
  hidden: [],
  locked: [],
  isolated: null,
  dirty: false,
  canUndo: false,
  canRedo: false,
  undoLabel: null,
  redoLabel: null,
  error: null,
}))

type Batch = { edits: Edit[]; label: string } | { source: true; label: string }

export interface SourceIssue {
  message: string
  line: number
  column: number
}

type SourceResult = { issue: SourceIssue } | { changed: false } | { changed: true; doc: CanvasDocument }

const past: Batch[] = []
const future: Batch[] = []
const state = useDoc.getState
const update = useDoc.setState
let queue: Promise<unknown> = Promise.resolve()
let opening: { path: string | null; done: Promise<void> } | null = null
let ignoredChange: string | null = null

function run<T>(work: () => Promise<T>): Promise<T> {
  const task = queue.then(async () => {
    try {
      const value = await work()
      update({ error: null })
      return value
    } catch (error) {
      update({ error: error instanceof Error ? error.message : String(error) })
      throw error
    }
  })
  queue = task.catch(() => undefined)
  return task
}

function received(doc: CanvasDocument | null, flags?: Pick<DocState, 'selection' | 'hidden' | 'locked' | 'isolated'>) {
  update({
    ...flags,
    doc, dirty: doc?.dirty === true,
    canUndo: past.length > 0, canRedo: future.length > 0,
    undoLabel: past.at(-1)?.label ?? null, redoLabel: future.at(-1)?.label ?? null,
  })
}

function resetHistory() {
  past.length = 0
  future.length = 0
  ignoredChange = null
}

function resetDocument(path: string | null, doc: CanvasDocument | null) {
  resetHistory()
  update({
    path, doc, dirty: false, canUndo: false, canRedo: false,
    undoLabel: null, redoLabel: null,
    selection: [], hidden: [], locked: [], isolated: null,
  })
}

function load(path: string | null, resolution?: CanvasPoint) {
  const done = run(async () => {
    const doc = await call<CanvasDocument | null>('doc_open', path, resolution ?? null)
    resetDocument(path, doc)
  })
  const request = { path, done }
  opening = request
  const settled = () => { if (opening === request) opening = null }
  void done.then(settled, settled)
  return done
}

function validIndexes(indexes: number[]) {
  const length = state().doc?.elements.length ?? 0
  return [...new Set(indexes.filter((index) => Number.isInteger(index) && index >= 0 && index < length))]
}

function record(doc: CanvasDocument, edits: Edit[], label: string) {
  if (edits.length) {
    past.push({ edits, label })
    future.length = 0
  }
  received(doc)
}

function receiveSource(doc: CanvasDocument) {
  const previous = state()
  const byId = new Map<string, CanvasDocument['elements']>()
  for (const element of doc.elements) {
    const siblings = byId.get(element.id) ?? []
    siblings.push(element)
    byId.set(element.id, siblings)
  }
  const remap = (index: number | null) => {
    const element = index === null ? undefined : previous.doc?.elements[index]
    if (!element?.id) return null
    const options = byId.get(element.id) ?? []
    if (options.length === 1) return options[0].index
    const siblings = options.filter((option) => option.parent === element.parent)
    return siblings.length === 1 ? siblings[0].index : siblings.find((option) => option.index === index)?.index ?? null
  }
  const indexes = (values: number[]) => [...new Set(values.map(remap).filter((index) => index !== null))]
  received(doc, {
    selection: indexes(previous.selection), hidden: indexes(previous.hidden), locked: indexes(previous.locked),
    isolated: remap(previous.isolated),
  })
}

export function applySource(path: string, text: string, expected: string, label: string): Promise<SourceIssue | null> {
  return run(async () => {
    if (state().path?.toLowerCase() !== path.toLowerCase()) throw new Error('O XML aberto mudou.')
    const result = await call<SourceResult>('doc_apply_source', path, text, expected)
    if ('issue' in result) return result.issue
    if (result.changed) {
      past.push({ source: true, label })
      future.length = 0
      receiveSource(result.doc)
    }
    return null
  })
}

function changeHistory(source: Batch[], target: Batch[], inverse: boolean) {
  return run(async () => {
    const batch = source.at(-1)
    if (!batch || !state().doc) return
    const doc = 'source' in batch
      ? await call<CanvasDocument>('doc_source_history', !inverse)
      : await call<CanvasDocument>('doc_edit', inverse ? batch.edits.toReversed().map((edit) => ({
        ...edit, before: edit.after, after: edit.before,
      })) : batch.edits)
    source.pop()
    target.push(batch)
    if ('source' in batch) receiveSource(doc)
    else received(doc)
  })
}

function setFlag(field: 'hidden' | 'locked', indexes: number[], enabled: boolean) {
  const next = new Set(state()[field])
  for (const index of validIndexes(indexes)) {
    if (enabled) next.add(index)
    else next.delete(index)
  }
  update({ [field]: [...next] })
}

/** Abre (ou recarrega) o XML; null fecha. */
export const openDoc: (path: string | null) => Promise<void> = (path) => load(path)

type ImportResult = { conflict: true; name: string; path: string } | {
  conflict: false; name: string; path: string; state: ShellState; doc: CanvasDocument; textures: string[]; backup: string | null
}

export function importStandalone(path: string, name: string | null, replace: boolean, textures: boolean, root: string | null) {
  return run(async () => {
    if (state().path !== path) throw new Error('O arquivo avulso ativo mudou.')
    const result = await call<ImportResult>('standalone_import', path, name, replace, textures, root)
    if (!result.conflict) {
      resetHistory()
      update({ path: result.path })
      received(result.doc)
    }
    return result
  })
}
/** replace: só estes; add: soma; toggle: liga/desliga cada um. */
export const select: (indexes: number[], mode?: 'replace' | 'add' | 'toggle') => void = (indexes, mode = 'replace') => {
  const valid = validIndexes(indexes)
  const next = new Set(mode === 'replace' ? [] : state().selection)
  for (const index of valid) {
    if (mode === 'toggle' && next.has(index)) next.delete(index)
    else next.add(index)
  }
  update({ selection: [...next] })
}
/** Aplica um lote como UM passo de desfazer (label aparece em Editar > Desfazer). */
export const applyEdits: (edits: Edit[], label: string) => Promise<void> = (edits, label) => {
  const path = state().path
  return run(async () => {
    const batch = edits.filter((edit) => JSON.stringify(edit.before) !== JSON.stringify(edit.after))
    if (!batch.length || !path || state().path !== path) return
    const doc = await call<CanvasDocument>('doc_edit', batch)
    record(doc, batch, label)
  })
}
export const undo: () => Promise<void> = () => changeHistory(past, future, true)
export const redo: () => Promise<void> = () => changeHistory(future, past, false)
/** Diff unificado do que será gravado (a casca mostra antes de salvar). '' se nada mudou. */
export const previewSave: () => Promise<string> = () =>
  run(() => state().dirty ? call<string>('doc_diff') : Promise.resolve(''))
/** Grava o XML (com backup no histórico do projeto, como a clássica). */
export const save: () => Promise<void> = () => run(async () => {
  if (!state().dirty) return
  const doc = await call<CanvasDocument>('doc_save')
  resetHistory()
  received(doc)
})
/** Descarta as edições e relê do disco. */
export const revert: () => Promise<void> = () => run(async () => {
  const { path } = state()
  if (path) resetDocument(path, await call<CanvasDocument>('doc_revert'))
})
export const setHidden: (indexes: number[], hidden: boolean) => void = (indexes, hidden) => setFlag('hidden', indexes, hidden)
export const setLocked: (indexes: number[], locked: boolean) => void = (indexes, locked) => setFlag('locked', indexes, locked)
export const setIsolated: (index: number | null) => void = (index) =>
  update({ isolated: index === null ? null : validIndexes([index])[0] ?? null })

/** The canvas can mount before the shell calls openDoc. Both use the same session. */
export function ensureDoc(path: string | null, resolution?: CanvasPoint): Promise<void> {
  if (opening?.path === path) return opening.done
  if (!opening && state().path === path && !resolution) return Promise.resolve()
  return load(path, resolution)
}

export function applyCanvasPreference(path: string, key: CanvasPreference, value: string | boolean, gameSize?: CanvasPoint) {
  return run(async () => {
    const result = await call<{ preferences: CanvasPreferences; doc: CanvasDocument | null }>(
      'canvas_set_preference', path, key, value, gameSize ?? null,
    )
    if (result.doc && state().path === path) received(result.doc)
    return result.preferences
  })
}

type GeometryEdit = Extract<Edit, { field: 'geometry' }>

export function applyCanvasEdits(
  makeEdits: (doc: CanvasDocument) => GeometryEdit[], label: string, preview: boolean, rootBackground: boolean,
) {
  const path = state().path
  return run(async () => {
    const { doc, locked } = state()
    if (!doc || !path || state().path !== path) return
    const edits = makeEdits(doc)
    if (!edits.length) return
    const result = await call<{ doc: CanvasDocument; edits: GeometryEdit[] }>(
      'doc_canvas_edit', edits, locked, preview, rootBackground,
    )
    record(result.doc, result.edits, label)
  })
}

export function checkExternalChange(path: string, confirm: (missing: boolean, dirty: boolean) => boolean) {
  // Watch checks should preserve an editing or save error already shown by the shell.
  const task = queue.then(async () => {
    if (state().path !== path || !state().doc) return
    const token = await call<string | null>('doc_external_change')
    if (token === null) {
      ignoredChange = null
      return
    }
    if (token === ignoredChange) return
    if ((token === 'missing' || state().dirty) && !confirm(token === 'missing', state().dirty)) {
      ignoredChange = token
      return
    }
    try {
      resetDocument(path, await call<CanvasDocument>('doc_revert'))
      update({ error: null })
    } catch (error) {
      // A malformed external revision may stay on disk until the other editor saves again.
      ignoredChange = token
      throw error
    }
  })
  queue = task.catch((error) => {
    update({ error: error instanceof Error ? error.message : String(error) })
  })
  return task
}

export function refreshGameTexts(project: string) {
  const task = queue.then(async () => {
    if (!state().doc) return
    const doc = await call<CanvasDocument | null>('doc_refresh_texts', project)
    if (doc) received(doc)
  })
  queue = task.catch(() => undefined)
  return task
}
