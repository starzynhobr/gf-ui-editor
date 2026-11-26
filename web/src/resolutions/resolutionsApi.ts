// Chamadas de "Exportar para várias resoluções…" (web_api/resolutions.py), tipadas.
import { call, type CanvasDocument, type CanvasPoint, type CanvasRect } from '../bridge'

export type Size = [width: number, height: number]
/** Regra por eixo: perto do começo, no meio, perto do fim, ou o jogo leva junto. */
export type Rule = 'start' | 'middle' | 'end' | 'game'

export interface PieceInfo {
  key: string
  indexes: number[]
  rule: [Rule, Rule]
  base: CanvasRect
  rect: CanvasRect
  adjusted: boolean
  /** O XML muda nesta resolução para o pedaço ficar no lugar. */
  moved: boolean
}

export interface WindowInfo {
  file: string
  kind: 'game' | 'fixed' | 'unknown'
  changed: boolean
  hud: boolean
  moves: boolean
  pieces: PieceInfo[]
}

export interface TargetPlan {
  size: Size
  key: string
  windows: WindowInfo[]
  files: string[]
  variants: string[]
}

export interface Plan {
  base: Size
  targets: TargetPlan[]
  windows: number
}

export interface Info {
  project: string
  base: Size
  previewBase: Size
  common: Size[]
  presets: Size[]
  targets: Size[]
  hud: string[]
}

export interface SceneLayer {
  name: string
  base: string
  scene: CanvasDocument
}

export interface ExportResult {
  folder: string
  zips: { key: string; path: string; count: number }[]
}

export const resolutionsApi = {
  info: () => call<Info>('resolutions_info'),
  setChoice: (base: Size, targets: Size[]) => call<void>('resolutions_set_choice', base, targets),
  plan: (base: Size, targets: Size[]) => call<Plan>('resolutions_plan', base, targets),
  scenes: (base: Size, target: Size, files: string[]) => call<SceneLayer[]>('resolutions_scenes', base, target, files),
  adjust: (file: string, piece: string, target: Size, point: CanvasPoint | null) =>
    call<void>('resolutions_adjust', file, piece, target, point),
  reset: (target: Size | null) => call<void>('resolutions_reset', target),
  addVariant: (target: Size) => call<string[] | null>('resolutions_add_variant', target),
  removeVariant: (target: Size, name: string) => call<string[]>('resolutions_remove_variant', target, name),
  pickFolder: () => call<string | null>('resolutions_pick_folder'),
  export: (folder: string, base: Size, targets: Size[], whole: boolean, allResolution: boolean) =>
    call<ExportResult>('resolutions_export', folder, base, targets, whole, allResolution),
}

export const sizeKey = ([width, height]: Size) => `${width}x${height}`
export const sizeLabel = ([width, height]: Size) => `${width} × ${height}`
export const sameSize = (a: Size, b: Size) => a[0] === b[0] && a[1] === b[1]

/** "1680x1050", "1680 × 1050" ou "1680 1050" → [1680, 1050] (entre 320 e 7680). */
export function parseSize(text: string): Size | null {
  const match = /^\s*(\d{3,5})\s*[x×\s]\s*(\d{3,5})\s*$/i.exec(text)
  if (!match) return null
  const size: Size = [Number(match[1]), Number(match[2])]
  return size.every((value) => value >= 320 && value <= 7680) ? size : null
}
