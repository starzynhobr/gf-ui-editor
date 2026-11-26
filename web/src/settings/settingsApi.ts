// Ponte do bloco 4: Configurações (web_api/settings.py) e atualizador/manifesto (web_api/updates.py).
import { call } from '../bridge'

export type ThemeValue = 'dark' | 'midnight' | 'light' | 'cappuccino' | 'rosa'
export type NavigationStyle = 'corel' | 'paintnet' | 'photoshop'
export type BackgroundMode = 'builtin' | 'custom' | 'none'

export interface SettingsValues {
  language: string
  ui_mode: 'classic' | 'web'
  web_theme: ThemeValue
  navigation_style: NavigationStyle
  auto_update_check: boolean
  beta_updates: boolean
  publish_on_save: boolean
  publish_confirmed: boolean
  offer_project_on_open: boolean
  canvas_saved_positions: boolean
  canvas_character: boolean
  game_dir: string
  game_resolution: string
  background_mode: BackgroundMode
}

export type SettingName = keyof SettingsValues

export interface SettingsState {
  version: string
  beta_build: boolean
  can_install: boolean
  values: SettingsValues
  game_dir_valid: boolean
  game_dir_default: string | null
  game_background: string
  has_custom_background: boolean
  resolutions: string[]
  review: { skipped_update: string; manifest_seen: number; layout: boolean }
}

export type ReleaseSections = Record<'new' | 'improved' | 'fixed', [string, string][]>

export interface UpdateOffer {
  version: string
  current: string
  page_url: string
  fallback_text: string
  verified: boolean
  can_install: boolean
  grouped: boolean
  releases: { version: string; date: string; sections: ReleaseSections }[]
}

export interface UpdateCheck {
  status: 'offer' | 'latest' | 'skipped' | 'error' | 'not_due'
  current: string
  include_betas: boolean
  error: string
  offer?: UpdateOffer
}

export interface ManifestNotices {
  needs_update: boolean
  version: string
  min_version: string | null
  messages: { id: string; level: 'info' | 'warning'; text: string; url: string | null }[]
  disabled: string[]
}

export const settingsApi = {
  state: () => call<SettingsState>('settings_state'),
  set: <K extends SettingName>(name: K, value: SettingsValues[K]) => call<SettingsState>('settings_set', name, value),
  reset: (what: 'skipped_update' | 'manifest_seen' | 'layout') => call<SettingsState>('settings_reset', what),
  pickGameDir: (current: string | null) => call<string | null>('pick_game_dir', current),
  chooseBackground: () => call<unknown>('canvas_choose_background'),
  updateCheck: (manual: boolean) => call<UpdateCheck>('update_check', manual),
  updateAutoCheck: () => call<UpdateCheck>('update_auto_check'),
  updateSkip: (version: string) => call<void>('update_skip', version),
  updateInstall: (version: string) => call<{ opened_page?: boolean; installing?: boolean }>('update_install', version),
  manifestNotices: () => call<ManifestNotices | null>('manifest_notices'),
  manifestMarkSeen: (id: string) => call<void>('manifest_mark_seen', id),
}
