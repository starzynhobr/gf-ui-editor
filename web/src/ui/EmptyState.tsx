// Estado vazio dos painéis (lista sem projeto, Textos sem jogo, árvore sem XML): ícone e
// um texto curto, centralizados e nas cores do tema.
import type { ReactNode } from 'react'
import { Icon } from './Icon'

export function EmptyState({ icon, title, text, testId, children }: {
  icon: string
  title: string
  text?: string
  testId?: string
  children?: ReactNode
}) {
  return (
    <div className="gf-empty" data-testid={testId ?? 'empty-state'}>
      <span className="gf-empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <div className="text-[13px] font-semibold text-bright">{title}</div>
      {text && <div className="max-w-[240px] text-[12px] leading-snug text-muted">{text}</div>}
      {children}
    </div>
  )
}
