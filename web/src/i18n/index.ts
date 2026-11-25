// Traduções da interface. pt_BR é o texto-fonte (a chave); os outros idiomas vêm dos
// catálogos do Qt convertidos por scripts/ts-to-json.mjs e, para textos só da interface
// nova, de web-strings.json. `npm run i18n:check` exige os 4 idiomas em toda chamada de t().
import { create } from 'zustand'
import en_US from './catalogs/en_US.json'
import es_ES from './catalogs/es_ES.json'
import fr_FR from './catalogs/fr_FR.json'
import webStrings from './web-strings.json'

export const LANGUAGES = [
  ['pt_BR', 'Português (Brasil)'],
  ['en_US', 'English'],
  ['es_ES', 'Español'],
  ['fr_FR', 'Français'],
] as const

export type Language = (typeof LANGUAGES)[number][0]

const catalogs: Record<string, Record<string, string>> = { en_US, es_ES, fr_FR }
const extra = webStrings as Record<string, Partial<Record<Language, string>>>

export const useLanguage = create<{ language: Language }>(() => ({ language: 'pt_BR' }))

export function setLanguage(language: string): void {
  const known = LANGUAGES.some(([code]) => code === language)
  useLanguage.setState({ language: (known ? language : 'pt_BR') as Language })
  document.documentElement.lang = (known ? language : 'pt_BR').replace('_', '-')
}

type Params = Record<string, string | number>

/** Texto traduzido; `{nome}` é trocado pelos parâmetros (como o str.format da clássica). */
export function t(text: string, params?: Params): string {
  const language = useLanguage.getState().language
  const translated = language === 'pt_BR' ? text : (catalogs[language]?.[text] ?? extra[text]?.[language] ?? text)
  if (!params) return translated
  return translated.replace(/\{(\w+)\}/g, (match, name: string) => (name in params ? String(params[name]) : match))
}

/** Assina o idioma: o componente redesenha quando ele muda. */
export function useT(): typeof t {
  useLanguage((state) => state.language)
  return t
}

/** "agora", "há 5 min"… a partir da chave de home.relative_age. */
export function relativeAge(age: [string, number | string | null]): string {
  const [key, value] = age
  if (key === 'now') return t('agora')
  if (key === 'minutes') return t('há {count} min', { count: value ?? 0 })
  if (key === 'hours') return t('há {count} h', { count: value ?? 0 })
  if (key === 'yesterday') return t('ontem')
  if (key === 'days') return t('há {count} dias', { count: value ?? 0 })
  return value != null ? String(value) : '—'
}
