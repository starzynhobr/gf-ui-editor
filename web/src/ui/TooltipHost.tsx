// Tooltips no tema do app para qualquer elemento com `title` (o nativo é a caixinha do Windows).
// Ao passar o mouse, o title vira data-gf-title (o navegador não mostra o dele) e este host
// desenha o balão depois de um respiro, acima ou abaixo do elemento.
import { useEffect, useState } from 'react'

const DELAY = 450

interface Tip {
  text: string
  x: number
  y: number
  below: boolean
}

export function TooltipHost() {
  const [tip, setTip] = useState<Tip | null>(null)
  useEffect(() => {
    let timer: number | undefined
    let current: HTMLElement | null = null
    const hide = () => {
      window.clearTimeout(timer)
      current = null
      setTip(null)
    }
    const over = (event: PointerEvent) => {
      const target = (event.target as Element | null)?.closest?.('[title], [data-gf-title]') as HTMLElement | null
      if (target === current) return
      hide()
      if (!target) return
      const native = target.getAttribute('title')
      if (native !== null) {
        target.dataset.gfTitle = native
        target.removeAttribute('title')
      }
      const text = target.dataset.gfTitle
      if (!text) return
      current = target
      timer = window.setTimeout(() => {
        if (current !== target || !target.isConnected) return
        const rect = target.getBoundingClientRect()
        const below = rect.top < 60
        setTip({ text, x: rect.left + rect.width / 2, y: below ? rect.bottom + 8 : rect.top - 8, below })
      }, DELAY)
    }
    window.addEventListener('pointerover', over)
    window.addEventListener('pointerdown', hide, true)
    window.addEventListener('wheel', hide, { passive: true })
    window.addEventListener('blur', hide)
    return () => {
      window.removeEventListener('pointerover', over)
      window.removeEventListener('pointerdown', hide, true)
      window.removeEventListener('wheel', hide)
      window.removeEventListener('blur', hide)
      window.clearTimeout(timer)
    }
  }, [])
  if (!tip) return null
  const left = Math.min(window.innerWidth - 16, Math.max(16, tip.x))
  return (
    <div
      role="tooltip"
      className={`gf-tooltip ${tip.below ? 'is-below' : ''}`}
      style={{ left, top: tip.y }}
    >
      {tip.text}
    </div>
  )
}
