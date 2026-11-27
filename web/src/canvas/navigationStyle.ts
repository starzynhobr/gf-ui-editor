import { useEffect, useState } from 'react'
import { call, type CanvasPreferences } from '../bridge'
import type { NavigationStyle } from './wheel'

let saved: NavigationStyle | undefined
let loading: Promise<NavigationStyle> | undefined

function load(): Promise<NavigationStyle> {
  loading ??= call<CanvasPreferences>('canvas_preferences')
    .then((preferences) => (saved ??= preferences.navigation ?? 'corel'))
    .catch(() => { loading = undefined; return saved ?? 'corel' })
  return loading
}

/** Estilo de navegação da roda (Configurações → Editor), o mesmo no canvas e no atlas. */
export function useNavigationStyle(): NavigationStyle {
  const [style, setStyle] = useState<NavigationStyle>(saved ?? 'corel')
  useEffect(() => {
    let active = true
    void load().then((value) => { if (active) setStyle(saved ?? value) })
    // A tela de Configurações troca o estilo com o canvas e o atlas montados.
    const changed = (event: Event) => {
      const { name, value } = (event as CustomEvent<{ name: string; value: unknown }>).detail ?? {}
      if (name !== 'navigation_style') return
      saved = value as NavigationStyle
      setStyle(saved)
    }
    window.addEventListener('gf:settings-changed', changed)
    return () => { active = false; window.removeEventListener('gf:settings-changed', changed) }
  }, [])
  return style
}

export function resetNavigationStyleForTests(): void {
  saved = undefined
  loading = undefined
}
