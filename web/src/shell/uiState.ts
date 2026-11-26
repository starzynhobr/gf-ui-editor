// Estado visual da interface nova, guardado nas preferências (ponte ui_state): larguras dos
// painéis laterais e tema. Lido uma vez ao abrir; gravado com atraso para não martelar o disco.
import { create } from 'zustand'
import { call } from '../bridge'

export type ThemeName = 'dark' | 'midnight' | 'light' | 'cappuccino' | 'rosa'
export const THEMES: ThemeName[] = ['dark', 'midnight', 'light', 'cappuccino', 'rosa']
/** Temas claros: toasts (sonner) e outros componentes que só conhecem claro/escuro. */
export const isLightTheme = (theme: ThemeName) => theme === 'light' || theme === 'rosa'

export const PANEL_LIMITS = {
  left: { min: 240, max: 560, initial: 310 },
  right: { min: 260, max: 520, initial: 320 },
  /** Painel "Ver código XML" (cresce para a esquerda). */
  code: { min: 320, max: 1600, initial: 560 },
} as const
export type PanelSide = keyof typeof PANEL_LIMITS

interface UiState {
  layout: Partial<Record<PanelSide, number>>
  theme: ThemeName
  loaded: boolean
}

export const useUi = create<UiState>(() => ({ layout: {}, theme: 'dark', loaded: false }))

export function applyTheme(theme: ThemeName): void {
  document.documentElement.dataset.theme = theme
}

export async function loadUiState(): Promise<void> {
  try {
    const state = await call<{ layout: Record<string, number>; theme: ThemeName }>('ui_state')
    useUi.setState({ layout: state.layout ?? {}, theme: state.theme ?? 'dark', loaded: true })
    applyTheme(state.theme ?? 'dark')
  } catch {
    useUi.setState({ loaded: true })
    applyTheme('dark')
  }
}

export function panelWidth(side: PanelSide, layout: UiState['layout']): number {
  const limits = PANEL_LIMITS[side]
  const value = layout[side]
  return typeof value === 'number' ? Math.min(limits.max, Math.max(limits.min, value)) : limits.initial
}

let saveTimer: number | undefined
export function setPanelWidth(side: PanelSide, width: number): void {
  const limits = PANEL_LIMITS[side]
  const layout = { ...useUi.getState().layout, [side]: Math.round(Math.min(limits.max, Math.max(limits.min, width))) }
  useUi.setState({ layout })
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => void call('ui_set_layout', layout).catch(() => undefined), 400)
}

export function setTheme(theme: ThemeName): void {
  // Troca suave: as cores fazem transição só durante a troca (não em todo hover).
  const root = document.documentElement
  root.classList.add('theme-switching')
  applyTheme(theme)
  useUi.setState({ theme })
  window.setTimeout(() => root.classList.remove('theme-switching'), 350)
  void call('ui_set_theme', theme).catch(() => undefined)
}
