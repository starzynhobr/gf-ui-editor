// Chamadas da tela de Textos ao Python (web_api/texts.py).
import { call } from '../bridge'

export type TextState = '' | 'edited' | 'updated' | 'changed'

export interface TextRow {
  name: string
  id: string
  fields: string[]
  state: TextState
  game_fields: string[]
  original: string[]
}

export interface TextResults {
  rows: TextRow[]
  total: number
  summary: 'no_game' | 'type_to_search' | 'nothing_edited' | 'changed' | 'limited' | 'count'
  values: { total?: number; shown?: number }
  updates: number
  limit: number
}

export interface OpenText {
  name: string
  id: string
  fields: string[]
  original: string[] | null
  can_restore: boolean
  encoding: string
  newline: string
}

export interface ImportPlan {
  count: number
  missing_ids: number
  unsupported: number
  unknown_files: string[]
  replaced: number
  per_file: [string, number][]
  folder: string
}

export const textsApi = {
  state: () => call<{ available: boolean; can_import: boolean; index_ready: boolean }>('texts_state'),
  search: (query: string, editedOnly: boolean) => call<TextResults>('texts_search', query, editedOnly),
  open: (name: string, id: string) => call<OpenText | null>('texts_open', name, id),
  save: (name: string, id: string, values: string[]) =>
    call<{ saved?: true; error?: 'pipe' | 'encoding'; encoding?: string }>('texts_save', name, id, values),
  restore: (name: string, id: string) => call<{ saved: true }>('texts_restore', name, id),
  reload: () => call<void>('texts_reload'),
  pickImport: () => call<string | null>('texts_pick_import'),
  planImport: (folder: string) => call<ImportPlan>('texts_plan_import', folder),
  applyImport: () => call<number>('texts_apply_import'),
}

/** Uma linha só, como a lista da clássica (quebras viram ⏎). */
export function oneLine(value: string): string {
  return value.replace(/\r\n/g, ' ⏎ ').replace(/\n/g, ' ⏎ ').replace(/\t/g, ' ')
}
