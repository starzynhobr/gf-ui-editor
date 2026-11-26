// Chamadas das ferramentas do projeto ao Python (web_api/maintenance.py).
import { call } from '../bridge'

export interface VersionInfo {
  path: string
  title: string
  label: string
  created: string
  files: number
  size: string
}

export interface PullCandidate {
  relative: string
  source: string
  new: boolean
  origin: 'edited' | 'official' | 'ui' | 'sent' | 'unknown'
  origin_ui: string
}

interface Part {
  count: number
  size: number
}

export interface CleanupScan {
  name: string
  days: number
  total: string
  ui: string
  history: string
  versions: string
  history_old: Part
  history_all: Part
  icons: Part & { left: number }
  maps: Part & { left: number }
  custom: Part & { folder: string }
}

export interface OfficialStatus {
  game_dir: string | null
  has_list: boolean
  ready: boolean
  cached: number
  total: number
  launcher_ui: string
}

export interface FileDiff {
  relative: string
  new_ids: string[]
  other_ids: string[]
}

export interface OfficialControls {
  file: string
  unavailable?: true
  complete?: true
  new_ids?: string[]
  other_ids?: string[]
  infos?: Record<string, { kind: string; texture: string; position: [number, number] }>
}

export interface GameErrorLocation {
  error?: 'invalid'
  cpp: string
  id: string
  candidates: string[]
  folder: string | null
  paths: Record<string, string>
  exists: Record<string, boolean>
}

export const toolsApi = {
  versions: (root: string) => call<VersionInfo[]>('versions_list', root),
  saveVersion: (root: string, label: string) => call<{ path: string; size: string }>('version_save', root, label),
  restoreVersion: (root: string, version: string) =>
    call<{ written: number; reverted: number; removed: number; unresolved: string[] }>('version_restore', root, version),
  branchVersion: (root: string, version: string, name: string) =>
    call<{ name: string; error?: 'taken' }>('version_branch', root, version, name),
  deleteVersion: (version: string) => call<void>('version_delete', version),
  versionsFolder: (root: string) => call<string>('versions_folder', root),
  pullSources: (root: string) => call<{ label: string; path: string }[]>('pull_sources', root),
  pullCompare: (root: string, source: string) => call<PullCandidate[]>('pull_compare', root, source),
  pullApply: (root: string, items: [string, string][]) => call<{ count: number; open_affected: boolean }>('pull_apply', root, items),
  gameBackups: () => call<PullCandidate[]>('game_backups'),
  cleanupScan: (root: string) => call<CleanupScan>('cleanup_scan', root),
  cleanupApply: (root: string, history: 'old' | 'all' | null, icons: boolean, maps: boolean, custom: boolean) =>
    call<{ removed: number; freed: string }>('cleanup_apply', root, history, icons, maps, custom),
  humanSize: (size: number) => call<string>('human_size', size),
  officialStatus: () => call<OfficialStatus>('official_status'),
  officialSnapshot: () => call<OfficialStatus>('official_snapshot'),
  officialScan: () => call<void>('official_scan'),
  officialControls: (path: string) => call<OfficialControls>('official_controls', path),
  locateGameError: (text: string) => call<GameErrorLocation>('locate_game_error', text),
  gameTextId: (path: string, windowId: string) => call<number | null>('game_text_id', path, windowId),
  textsExportInfo: () => call<{ available: boolean; has_edits: boolean; disabled: boolean }>('texts_export_info'),
  textsPickExport: () => call<string | null>('texts_pick_export'),
  textsExport: (target: string) => call<{ path: string; names: string[]; warnings: string[] }>('texts_export', target),
}

/** Tamanho legível, igual ao home.human_size do Python (para somas feitas no front). */
export function humanSize(size: number): string {
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(1)} GB`
  if (size >= 1024 ** 2) return `${Math.round(size / 1024 ** 2)} MB`
  return `${Math.max(1, Math.floor(size / 1024))} KB`
}
