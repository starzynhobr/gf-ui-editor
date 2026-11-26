// Pílula "Novidades ×" da barra superior, no espaço livre à esquerda do Exportar: aparece quando
// as notas abertas sozinhas depois de atualizar são fechadas. "Novidades" reabre (o diálogo
// cresce a partir dela); o × a tira até a próxima versão.
//
// Ela não ocupa lugar no fluxo da barra (fica presa à direita de uma âncora de largura zero) e
// some quando não cabe entre o conteúdo da esquerda / a pílula STZ e o Exportar: nunca empurra
// nem quebra a barra. Sem ela, as Novidades continuam na engrenagem e no Ctrl+K.
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useLayoutEffect, useRef, useState } from 'react'
import { openWhatsNew } from '../home/WhatsNewDialog'
import { dismissPill, useWhatsNew } from '../home/whatsNew'
import { useT } from '../i18n'
import { Icon } from '../ui/Icon'

const GAP = 10 // folga mínima até o conteúdo da esquerda e a pílula STZ

function PillFace({ label }: { label: string }) {
  return (
    <>
      <span className="gf-whats-new-dot" aria-hidden="true" />
      <Icon name="sparkles" size={15} className="text-accent-text" />
      {label}
    </>
  )
}

export default function WhatsNewPill() {
  const t = useT()
  const pill = useWhatsNew((state) => state.pill)
  const covering = useWhatsNew((state) => state.covering)
  const reduced = useReducedMotion()
  const anchor = useRef<HTMLDivElement>(null)
  const ghost = useRef<HTMLDivElement>(null)
  const face = useRef<HTMLDivElement>(null)
  const [fits, setFits] = useState(true)

  useLayoutEffect(() => {
    const here = anchor.current
    const header = here?.closest('header')
    if (!pill || !here || !header) return
    const measure = () => {
      const bar = header.getBoundingClientRect()
      if (bar.width === 0) return setFits(true) // sem layout (testes)
      const width = ghost.current?.getBoundingClientRect().width ?? 0
      const left = here.getBoundingClientRect().right - width
      const spacer = header.querySelector<HTMLElement>('[data-topbar-spacer]')?.getBoundingClientRect().left ?? bar.left
      const stz = header.querySelector<HTMLElement>('[data-testid=stz-pill]')?.getBoundingClientRect().right ?? bar.left
      setFits(width > 0 && left >= Math.max(spacer, stz) + GAP)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(header)
    const spacer = header.querySelector<HTMLElement>('[data-topbar-spacer]')
    if (spacer) observer.observe(spacer)
    if (ghost.current) observer.observe(ghost.current)
    window.addEventListener('resize', measure)
    document.fonts?.addEventListener?.('loadingdone', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
      document.fonts?.removeEventListener?.('loadingdone', measure)
    }
  }, [pill])

  const label = t('Novidades')
  const reopen = () => {
    const rect = face.current?.getBoundingClientRect() ?? null
    openWhatsNew('pill', rect)
  }

  return (
    <div ref={anchor} className="relative mr-1.5 h-8 w-0 shrink-0" data-testid="whats-new-anchor">
      {pill && (
        // Medida da pílula (mesmas classes, sem botões): decide se cabe sem depender dela estar na tela.
        <div ref={ghost} aria-hidden="true" className="pointer-events-none invisible absolute top-0 right-0 flex whitespace-nowrap">
          <span className="btn h-8 rounded-r-none">
            <PillFace label={label} />
          </span>
          <span className="btn h-8 w-7 rounded-l-none border-l-0 px-0" />
        </div>
      )}
      <AnimatePresence>
        {pill && fits && (
          <motion.div
            key="pill"
            ref={face}
            className="absolute top-0 right-0 flex whitespace-nowrap"
            data-testid="whats-new-pill"
            data-fits="true"
            data-covered={covering || undefined}
            initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.86 }}
            animate={covering ? { opacity: 0, scale: reduced ? 1 : 0.92 } : { opacity: 1, scale: 1 }}
            exit={reduced ? { opacity: 0, transition: { duration: 0.12 } } : { opacity: 0, scale: 0.7, transition: { duration: 0.18, ease: 'easeIn' } }}
            transition={reduced ? { duration: 0.14 } : { type: 'spring', stiffness: 520, damping: 30 }}
            style={{ pointerEvents: covering ? 'none' : undefined, transformOrigin: '100% 50%' }}
          >
            <button
              className="btn gf-whats-new-pill h-8 rounded-r-none"
              data-testid="whats-new-pill-open"
              title={t('Ver o que mudou nesta versão')}
              tabIndex={covering ? -1 : undefined}
              onClick={reopen}
            >
              <PillFace label={label} />
            </button>
            <button
              className="btn h-8 w-7 rounded-l-none border-l-0 px-0"
              data-testid="whats-new-pill-dismiss"
              aria-label={t('Tirar Novidades da barra')}
              title={t('Tira da barra até a próxima versão. As Novidades continuam na engrenagem.')}
              tabIndex={covering ? -1 : undefined}
              onClick={dismissPill}
            >
              <Icon name="x" size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
