import { useLayoutEffect, useState } from 'react'

const tokens = {
  surface: '--color-canvas-surface',
  grid: '--color-canvas-grid',
  frame: '--color-canvas-frame',
  outline: '--color-canvas-outline',
  selection: '--color-gold',
  label: '--color-warning',
  character: '--color-success',
  ghost: '--color-warning',
} as const

function readPalette() {
  const style = getComputedStyle(document.documentElement)
  return Object.fromEntries(Object.entries(tokens).map(([key, token]) => [
    key, style.getPropertyValue(token).trim(),
  ])) as Record<keyof typeof tokens, string>
}

export type CanvasPalette = ReturnType<typeof readPalette>

export function useCanvasPalette() {
  const [palette, setPalette] = useState(readPalette)
  useLayoutEffect(() => {
    const observer = new MutationObserver(() => setPalette(readPalette()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])
  return palette
}
