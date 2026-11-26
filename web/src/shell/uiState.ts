// Estado visual da interface nova, guardado nas preferências (ponte ui_state): larguras dos
// painéis laterais, tema e fonte. Lido uma vez ao abrir; gravado com atraso para não martelar o disco.
import { create } from 'zustand'
import { call } from '../bridge'

export type ThemeName = 'dark' | 'midnight' | 'light' | 'cappuccino' | 'rosa'
export const THEMES: ThemeName[] = ['dark', 'midnight', 'light', 'cappuccino', 'rosa']
/** Temas claros: toasts (sonner) e outros componentes que só conhecem claro/escuro. */
export const isLightTheme = (theme: ThemeName) => theme === 'light' || theme === 'rosa'

/** Fontes da interface (fonts.css: data-font no <html> troca --font-sans e --font-mono). */
export type FontName = 'system' | 'plex' | 'inter' | 'geist'
export const FONTS: FontName[] = ['system', 'plex', 'inter', 'geist']
/** Nome de cada fonte como aparece no seletor (nomes próprios, sem tradução). */
export const FONT_LABELS: Record<FontName, string> = { system: 'Segoe UI', plex: 'IBM Plex Sans', inter: 'Inter', geist: 'Geist' }

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
  font: FontName
  /** Liga/desliga e "já vi" (ponte ui_set_flag → web_flags). */
  flags: Record<string, boolean>
  loaded: boolean
}

export const useUi = create<UiState>(() => ({ layout: {}, theme: 'dark', font: 'system', flags: {}, loaded: false }))

export function applyTheme(theme: ThemeName): void {
  document.documentElement.dataset.theme = theme
}

export function applyFont(font: FontName): void {
  const root = document.documentElement
  if (font === 'system') delete root.dataset.font
  else root.dataset.font = font
}

export async function loadUiState(): Promise<void> {
  try {
    const state = await call<{ layout: Record<string, number>; theme: ThemeName; font?: FontName; flags?: Record<string, boolean> }>('ui_state')
    const font = state.font && FONTS.includes(state.font) ? state.font : 'system'
    useUi.setState({ layout: state.layout ?? {}, theme: state.theme ?? 'dark', font, flags: state.flags ?? {}, loaded: true })
    applyTheme(state.theme ?? 'dark')
    applyFont(font)
  } catch {
    useUi.setState({ loaded: true })
    applyTheme('dark')
    applyFont('system')
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

/** Troca a fonte na hora (só as variáveis --font-sans/--font-mono mudam) e grava em web_font. */
export function setFont(font: FontName): void {
  applyFont(font)
  useUi.setState({ font })
  void call('ui_set_font', font).catch(() => undefined)
}

/** Flag da interface nova; `fallback` vale enquanto a pessoa não mudou. */
export function useFlag(name: string, fallback: boolean): boolean {
  return useUi((state) => state.flags[name] ?? fallback)
}

export function setFlag(name: string, value: boolean): void {
  useUi.setState((state) => ({ flags: { ...state.flags, [name]: value } }))
  void call('ui_set_flag', name, value).catch(() => undefined)
}
