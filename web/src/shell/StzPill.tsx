// Pílula STZ Labs no centro da barra superior: abre o cartão com o site, GitHub, Discord e
// quem ajudou a construir o editor (como o StzLabsPopup da clássica).
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { call } from '../bridge'
import { useT } from '../i18n'
import logoUrl from '../assets/stz-labs.svg'
import markUrl from '../assets/stz-mark.svg'

interface Contributor {
  name: string
  color: string
  tags: string[]
  items: { text: string; version: string | null }[]
  since: string | null
}

interface AboutInfo {
  version: string
  author: string
  site: string
  github: string
  discord: string
  contributors: Contributor[]
}

/** Engrenagem → "Sobre o STZ GF UI…": abre o cartão da pílula. */
export function openAbout(): void {
  // Depois do clique que fechou o menu (o cartão fecha com mousedown fora dele).
  window.setTimeout(() => window.dispatchEvent(new CustomEvent('gf:open-about')), 0)
}

const SHOWN = 3 // contribuições à vista por pessoa; o resto abre no "+N"

export default function StzPill() {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState<AboutInfo | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const show = () => setOpen(true)
    window.addEventListener('gf:open-about', show)
    return () => window.removeEventListener('gf:open-about', show)
  }, [])

  useEffect(() => {
    if (!open) return
    if (!info) void call<AboutInfo>('about_info').then(setInfo)
    const close = (event: MouseEvent) => {
      const target = event.target
      if (box.current && !(target instanceof Node && box.current.contains(target))) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', escape)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', escape)
    }
  }, [open, info])

  const go = (url: string) => {
    void api.openUrl(url)
    setOpen(false)
  }
  const tagLabel: Record<string, string> = { ideas: t('Ideias'), qa: t('Testes / QA'), navigation: t('Navegação') }

  return (
    <div ref={box} className="relative">
      <motion.button
        className="gf-stz-pill"
        data-testid="stz-pill"
        aria-expanded={open}
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.96 }}
        transition={{ type: 'spring', stiffness: 500, damping: 28 }}
        onClick={() => setOpen(!open)}
      >
        <img src={markUrl} alt="" className="h-[15px]" draggable={false} />
        <span>Labs</span>
      </motion.button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="gf-stz-card"
            data-testid="stz-card"
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ type: 'spring', stiffness: 420, damping: 32 }}
          >
            <div className="gf-stz-header">
              <img src={logoUrl} alt="STZ Labs" className="h-12" draggable={false} />
              <div className="mt-2 text-[12px] text-muted">
                {t('{name} {version} · feito por {author}', { name: 'STZ GF UI', version: info?.version ?? '', author: info?.author ?? 'StarzynhoBR' })}
              </div>
              <div className="text-[12.5px] leading-snug text-text">{t('Ferramentas e projetos independentes. Este editor é um deles.')}</div>
              <div className="mt-3 flex gap-1.5">
                <button className="btn btn-primary h-7 flex-1" onClick={() => info && go(info.site)}>
                  {t('Visitar stzlabs.com ↗')}
                </button>
                <button className="btn h-7" onClick={() => info && go(info.github)}>
                  GitHub
                </button>
                <button className="btn h-7 gf-discord" onClick={() => info && go(info.discord)}>
                  Discord
                </button>
              </div>
            </div>
            <div className="px-4 pt-3 pb-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="section-label">{t('QUEM AJUDOU A CONSTRUIR')}</span>
                <span className="section-label">{t('{count} pessoas', { count: info?.contributors.length ?? 0 })}</span>
              </div>
              <div className="max-h-[380px] space-y-2 overflow-y-auto pr-1">
                {(info?.contributors ?? []).map((person, index) => (
                  <motion.div
                    key={person.name}
                    className="gf-stz-person"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.04 * index, duration: 0.2 }}
                  >
                    <PersonCard person={person} tagLabel={tagLabel} />
                  </motion.div>
                ))}
              </div>
              <div className="mt-3 text-[12px] leading-snug text-muted">
                {t('💡 Teve uma ideia ou achou um bug? Conte no Discord — quem ajuda entra aqui.')}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function PersonCard({ person, tagLabel }: { person: Contributor; tagLabel: Record<string, string> }) {
  const t = useT()
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? person.items : person.items.slice(0, SHOWN)
  const hidden = person.items.length - shown.length
  return (
    <div className="flex gap-2.5">
      <div className="gf-stz-avatar" style={{ background: person.color }}>
        {person.name.slice(0, 1).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="font-semibold text-bright">{person.name}</span>
          {person.items.length > 1 && (
            <span className="text-[11.5px] text-muted">{t('· {count} contribuições', { count: person.items.length })}</span>
          )}
          <span className="ml-auto text-[11.5px] text-muted">{person.since ? t('desde {version}', { version: person.since }) : ''}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {person.tags.map((tag) => (
            <span key={tag} className="gf-stz-tag">
              {tagLabel[tag] ?? tag}
            </span>
          ))}
        </div>
        <ul className="mt-1.5 space-y-0.5 text-[12.5px] leading-snug text-text">
          {shown.map((item, index) => (
            <li key={index} className="flex gap-1.5">
              <span className="text-accent-text">•</span>
              <span className="min-w-0 flex-1">{item.text}</span>
              {item.version && <span className="shrink-0 font-mono text-[10.5px] text-disabled">{item.version}</span>}
            </li>
          ))}
        </ul>
        {hidden > 0 && (
          <button className="link mt-1 text-[12px]" onClick={() => setExpanded(true)}>
            +{hidden}
          </button>
        )}
      </div>
    </div>
  )
}
