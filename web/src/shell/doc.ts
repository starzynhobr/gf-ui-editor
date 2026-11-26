// Ponte da casca com o documento aberto (doc/store.ts, implementado pelo canvas).
//
// A casca usa só as funções do contrato. Enquanto o store ainda lança "não implementado"
// (antes de o bloco 2 do canvas chegar), este módulo cai num modo só leitura: lê o XML pela
// mesma ponte do canvas e guarda seleção/oculto/travado/isolado aqui. Assim a árvore e o
// painel funcionam e podem ser testados; editar e salvar avisam que ainda não dá.
import { create } from 'zustand'
import { openCanvasDocument, type CanvasDocument } from '../bridge'
import * as store from '../doc/store'
import type { DocState, Edit } from '../doc/store'

export class StoreUnavailable extends Error {}

const notImplemented = (error: unknown) => error instanceof Error && error.message.includes('ainda não implementado')

/** Estado só leitura enquanto o store do canvas não existe. */
const useFallback = create<DocState & { active: boolean }>(() => ({
  active: false,
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
}))

/** O estado do documento, venha do store do canvas ou do modo só leitura. */
export function useDocState<T>(pick: (state: DocState) => T): T {
  const active = useFallback((state) => state.active)
  const fromStore = store.useDoc(pick)
  const fromFallback = useFallback(pick)
  return active ? fromFallback : fromStore
}

export function docState(): DocState {
  return useFallback.getState().active ? useFallback.getState() : store.useDoc.getState()
}

/** O store do canvas está implementado (edição e salvar disponíveis). */
export function editingAvailable(): boolean {
  return !useFallback.getState().active
}

export function useEditingAvailable(): boolean {
  return !useFallback((state) => state.active)
}

async function guard<T>(run: () => T | Promise<T>, fallback: () => T | Promise<T>): Promise<T> {
  if (useFallback.getState().active) return fallback()
  try {
    return await run()
  } catch (error) {
    if (!notImplemented(error)) throw error
    useFallback.setState({ active: true })
    return fallback()
  }
}

let loading = 0

export async function openDocument(path: string | null): Promise<void> {
  await guard(
    () => store.openDoc(path),
    async () => {
      const ticket = ++loading
      if (!path) {
        useFallback.setState({ path: null, doc: null, selection: [], hidden: [], locked: [], isolated: null })
        return
      }
      let doc: CanvasDocument | null = null
      let error: string | null = null
      try {
        doc = await openCanvasDocument(path)
      } catch (reason) {
        error = reason instanceof Error ? reason.message : String(reason)
      }
      if (ticket !== loading) return
      useFallback.setState({ path, doc, error, selection: [], hidden: [], locked: [], isolated: null, dirty: false })
    },
  )
}

function combine(current: number[], indexes: number[], mode: 'replace' | 'add' | 'toggle'): number[] {
  if (mode === 'replace') return [...new Set(indexes)]
  if (mode === 'add') return [...current, ...indexes.filter((index) => !current.includes(index))]
  const next = [...current]
  for (const index of indexes) {
    const at = next.indexOf(index)
    if (at >= 0) next.splice(at, 1)
    else next.push(index)
  }
  return next
}

export function selectElements(indexes: number[], mode: 'replace' | 'add' | 'toggle' = 'replace'): void {
  void guard(
    () => store.select(indexes, mode),
    () => useFallback.setState((state) => ({ selection: combine(state.selection, indexes, mode) })),
  )
}

const toggleList = (list: number[], indexes: number[], on: boolean) =>
  on ? [...new Set([...list, ...indexes])] : list.filter((index) => !indexes.includes(index))

export function setHidden(indexes: number[], hidden: boolean): void {
  void guard(
    () => store.setHidden(indexes, hidden),
    () => useFallback.setState((state) => ({ hidden: toggleList(state.hidden, indexes, hidden) })),
  )
}

export function setLocked(indexes: number[], locked: boolean): void {
  void guard(
    () => store.setLocked(indexes, locked),
    () => useFallback.setState((state) => ({ locked: toggleList(state.locked, indexes, locked) })),
  )
}

export function setIsolated(index: number | null): void {
  void guard(
    () => store.setIsolated(index),
    () => useFallback.setState({ isolated: index }),
  )
}

const unavailable = () => {
  throw new StoreUnavailable('edição indisponível')
}

export const applyEdits = (edits: Edit[], label: string) => guard(() => store.applyEdits(edits, label), unavailable)
export const undo = () => guard(() => store.undo(), () => undefined)
export const redo = () => guard(() => store.redo(), () => undefined)
export const previewSave = () => guard(() => store.previewSave(), () => '')
export const save = () => guard(() => store.save(), unavailable)
export const revert = () => guard(() => store.revert(), () => undefined)
