// Documento aberto: estado compartilhado entre canvas, árvore de elementos e painel.
// CONTRATO DO BLOCO 2 (vault/web-bridge.md). Dono da implementação: canvas (Codex).
// A casca (Claude 2) só usa as funções e o hook daqui; não muda as assinaturas.
//
// Fonte da verdade: o documento em memória no Python (web_api/document.py). Toda edição
// passa por applyEdits -> Python (doc_edit) e volta como documento atualizado; desfazer e
// refazer reaplicam o lote inverso pelo mesmo caminho. Salvar grava pelo Python.
import { create } from 'zustand'
import type { CanvasDocument, CanvasRect } from '../bridge'

export type Edit =
  | { index: number; field: 'geometry'; before: CanvasRect; after: CanvasRect }
  | { index: number; field: 'uv'; before: CanvasRect | null; after: CanvasRect | null }
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
  error: null,
}))

const todo = (name: string) => () => {
  throw new Error(`doc/store.${name}: ainda não implementado (bloco 2, canvas)`)
}

/** Abre (ou recarrega) o XML; null fecha. */
export const openDoc: (path: string | null) => Promise<void> = todo('openDoc') as never
/** replace: só estes; add: soma; toggle: liga/desliga cada um. */
export const select: (indexes: number[], mode?: 'replace' | 'add' | 'toggle') => void = todo('select') as never
/** Aplica um lote como UM passo de desfazer (label aparece em Editar > Desfazer). */
export const applyEdits: (edits: Edit[], label: string) => Promise<void> = todo('applyEdits') as never
export const undo: () => Promise<void> = todo('undo') as never
export const redo: () => Promise<void> = todo('redo') as never
/** Diff unificado do que será gravado (a casca mostra antes de salvar). '' se nada mudou. */
export const previewSave: () => Promise<string> = todo('previewSave') as never
/** Grava o XML (com backup no histórico do projeto, como a clássica). */
export const save: () => Promise<void> = todo('save') as never
/** Descarta as edições e relê do disco. */
export const revert: () => Promise<void> = todo('revert') as never
export const setHidden: (indexes: number[], hidden: boolean) => void = todo('setHidden') as never
export const setLocked: (indexes: number[], locked: boolean) => void = todo('setLocked') as never
export const setIsolated: (index: number | null) => void = todo('setIsolated') as never
