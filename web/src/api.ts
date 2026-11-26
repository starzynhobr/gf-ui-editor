// Chamadas da casca ao Python (web_api/projects.py), tipadas. Usa o `call`/`on` de bridge.ts.
import { call } from './bridge'

export interface ProjectInfo {
  root: string
  name: string
  custom_name: string
  ui_dir: string
  light?: boolean
  game_dir: string | null
  publish_dir: string | null
}

export interface ShellState {
  version: string
  language: string
  ui_mode: 'classic' | 'web'
  project: ProjectInfo | null
  open_path: string | null
  loose_dir: string | null
  pending: number
  publish_confirmed: boolean
  publish_on_save: boolean
}

export type Age = [string, number | string | null]

export interface HomeProject {
  root: string
  title: string
  files: number | null
  edited: number
  age: Age
  current: boolean
  size: string | null
}

export interface ContinueCard {
  root: string
  name: string
  ui_dir: string
  last_file: string
  modified: number
  custom_name: string
  has_game: boolean
  age: Age
}

export interface HomeData {
  projects: HomeProject[]
  continue: ContinueCard | null
  version: string
  news: string[]
  how_to_url: string
  projects_root: string
}

export interface FileListData {
  mode: 'xml' | 'textures'
  files: string[]
  modified: number[]
  layers: number[]
  sections: { kind: SectionKind; items: number[] }[]
  heights: Partial<Record<SectionKind, number>>
  has_textures: boolean
  shared_publish: string[]
  directory: string | null
  in_project: boolean
}

export type SectionKind = 'layers' | 'changed' | 'all'

export interface NewProjectForm {
  game_dir: string | null
  game_dir_warning: boolean
  sources: { label: string; path: string }[]
  default_source: string | null
  loose_dir: string | null
  loose_files: string[]
  projects_root: string
}

export interface PublishTarget {
  value: string
  folder: string
  warning: ['shared', { projects: string; folder: string }] | ['exists', { folder: string }] | null
}

export interface PublishResult {
  copied: number
  texts_changed: number
  texts_blocked: boolean
  text_warnings: string[]
  game_backups: number
  select_in_launcher: boolean
  custom_name: string
  pending: number
}

export interface TreeRow {
  index: number
  label: string
  text: string
  search: string
}

export interface FileHistory {
  backups: { path: string; name: string; stamp: string | null }[]
  original: string | null
  folder: string | null
  in_project: boolean
}

export const api = {
  startup: () => call<ShellState & { view: 'home' | 'workspace' }>('startup'),
  shellState: () => call<ShellState>('shell_state'),
  setLanguage: (language: string) => call<ShellState>('set_language', language),
  openFolder: (path: string) => call<void>('open_folder', path),
  openUrl: (url: string) => call<void>('open_url', url),
  homeData: () => call<HomeData>('home_data'),
  whatsNew: () =>
    call<{ version: string; date: string; sections: Record<'new' | 'improved' | 'fixed', [string, string][]> }>('whats_new'),
  goHome: () => call<ShellState>('go_home'),
  openProject: (root: string) => call<ShellState>('open_project', root),
  browseProject: () => call<ShellState | { error: 'not_a_project' } | null>('browse_project'),
  duplicateProject: (root: string, name: string) => call<{ name: string; error?: 'taken' }>('duplicate_project', root, name),
  renameProject: (root: string, name: string) =>
    call<{ name: string; error?: 'taken' | 'busy'; detail?: string; state?: ShellState }>('rename_project', root, name),
  deleteInfo: (roots: string[]) =>
    call<{ projects: { root: string; name: string }[]; owned: string[] }>('delete_info', roots),
  deleteProjects: (roots: string[], removeCustom: boolean) =>
    call<{ failed: string[]; state: ShellState }>('delete_projects', roots, removeCustom),
  newProjectForm: (gameDir?: string | null, looseDir?: string | null) =>
    call<NewProjectForm>('new_project_form', gameDir ?? null, looseDir ?? null),
  newProjectTargets: (name: string, sourceLabel: string, gameDir: string | null) =>
    call<PublishTarget[]>('new_project_targets', name, sourceLabel, gameDir),
  pickGameDir: (current: string | null) => call<string | null>('pick_game_dir', current),
  pickSource: (kind: 'folder' | 'zip') => call<{ path: string; suggested_name: string } | null>('pick_source', kind),
  createProject: (form: Record<string, unknown>) =>
    call<{ count: number; state: ShellState } | { error: 'exists'; path: string }>('create_project', form),
  pickXml: () => call<{ path: string; offer_project: boolean } | null>('pick_xml'),
  setOfferProject: (enabled: boolean) => call<void>('set_offer_project', enabled),
  openLoose: (path: string) => call<ShellState>('open_loose', path),
  fileList: (mode: 'xml' | 'textures') => call<FileListData>('file_list', mode),
  moveSection: (kind: SectionKind, step: number, visible: SectionKind[]) =>
    call<SectionKind[]>('move_section', kind, step, visible),
  setSectionOrder: (order: SectionKind[]) => call<SectionKind[]>('set_section_order', order),
  setSectionHeights: (heights: Partial<Record<SectionKind, number>>) => call<void>('set_section_heights', heights),
  openXml: (path: string) => call<ShellState>('open_xml', path),
  openInTextEditor: (path: string) => call<string>('open_in_text_editor', path),
  textEditorName: () => call<string>('text_editor_name'),
  setUnsaved: (unsaved: boolean) => call<void>('set_unsaved', unsaved),
  closeWindow: (restart = false) => call<void>('close_window', restart),
  elementTree: (path: string, kinds: string[]) => call<TreeRow[]>('element_tree', path, kinds),
  treeColumns: () => call<string[]>('tree_columns'),
  setTreeColumns: (hidden: string[]) => call<string[]>('set_tree_columns', hidden),
  textureNames: (xmlPath: string) => call<string[]>('texture_names', xmlPath),
  textureCopyInfo: (xmlPath: string, current: string) =>
    call<{ exists: boolean; suggestion: string }>('texture_copy_info', xmlPath, current),
  copyTexture: (xmlPath: string, current: string, name: string) =>
    call<{ name: string; error?: 'exists' }>('copy_texture', xmlPath, current, name),
  pickTexture: (xmlPath: string) => call<{ path: string; name: string; replacing: boolean } | null>('pick_texture', xmlPath),
  bringTexture: (xmlPath: string, source: string) => call<{ name: string }>('bring_texture', xmlPath, source),
  fileHistory: (path: string) => call<FileHistory>('file_history', path),
  renameCheck: (path: string, name: string) =>
    call<{ invalid?: true; target: string; name: string; replacing: boolean; texture_users: number }>('rename_check', path, name),
  renameFile: (path: string, name: string) => call<{ path: string; name: string }>('rename_file', path, name),
  retargetTexture: (oldName: string, newName: string) => call<number>('retarget_texture', oldName, newName),
  deleteFileInfo: (path: string) => call<{ official: boolean; texture_users: number }>('delete_file_info', path),
  deleteFile: (path: string) => call<void>('delete_file', path),
  restorePreview: (path: string, source: string, currentLabel: string, restoredLabel: string) =>
    call<string>('restore_preview', path, source, currentLabel, restoredLabel),
  restoreFile: (path: string, source: string) => call<void>('restore_file', path, source),
  publishInfo: () => call<{ confirmed: boolean; custom_dir: string; custom_name: string; new_controls: string[] }>('publish_info'),
  confirmPublish: () => call<void>('confirm_publish'),
  publish: () => call<PublishResult>('publish'),
  pickExportTarget: () => call<string | null>('pick_export_target'),
  exportZip: (target: string) => call<{ path: string; count: number; skipped: number } | { empty: true }>('export_zip', target),
  convertProjectToLight: () => call<{ backup: string | null; state: ShellState }>('convert_project_to_light'),
}

/** Mensagem legível de um erro vindo do Python (o pywebview rejeita com {name, message}). */
export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message
  if (error && typeof error === 'object' && 'message' in error) return String((error as { message: unknown }).message)
  return String(error)
}
