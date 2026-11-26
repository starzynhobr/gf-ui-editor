// Pílula STZ Labs no centro da barra superior: abre o cartão com o site, GitHub, Discord e
// quem ajudou a construir o editor (como o StzLabsPopup da clássica). "Quem ajudou" tem duas
// vistas: Pessoas (cartões que expandem com todas as contribuições) e Por versão (linha do tempo).
import NumberFlow from '@number-flow/react'
import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { api } from '../api'
import { call } from '../bridge'
import { t, useT } from '../i18n'
import logoUrl from '../assets/stz-labs.svg'
import markUrl from '../assets/stz-mark.svg'
import { Icon } from '../ui/Icon'

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

export default function StzPill() {
  useT()
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
            <Helpers info={info} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** Tags por tipo de ajuda; cada tipo com a sua cor do tema (index.css, .gf-stz-tag[data-tag]). */
function tagLabel(tag: string): string {
  return ({ ideas: t('Ideias'), qa: t('Testes / QA'), navigation: t('Navegação') } as Record<string, string>)[tag] ?? tag
}

function Avatar({ person, size = 32 }: { person: Contributor; size?: number }) {
  return (
    <span
      className="gf-stz-avatar"
      style={{ '--person': person.color, width: size, height: size, fontSize: Math.round(size * 0.42) } as CSSProperties}
      title={person.name}
    >
      {person.name.slice(0, 1).toUpperCase()}
    </span>
  )
}

/** Número que conta a partir de zero quando o cartão abre (NumberFlow). */
function Count({ value, testId }: { value: number; testId?: string }) {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(value))
    return () => cancelAnimationFrame(frame)
  }, [value])
  return <NumberFlow value={shown} className="gf-stz-count" data-testid={testId} data-value={value} />
}

type View = 'people' | 'versions'

function Helpers({ info }: { info: AboutInfo | null }) {
  useT()
  const [view, setView] = useState<View>('people')
  const people = info?.contributors ?? []
  const total = people.reduce((sum, person) => sum + person.items.length, 0)
  const views: [View, string][] = [
    ['people', t('Pessoas')],
    ['versions', t('Por versão')],
  ]
  return (
    <div className="px-4 pt-3 pb-4" data-testid="stz-helpers">
      <div className="section-label mb-2">{t('QUEM AJUDOU A CONSTRUIR')}</div>
      <div className="mb-3 flex items-center gap-3">
        <div className="gf-stz-stack" aria-hidden="true">
          {people.map((person) => (
            <Avatar key={person.name} person={person} size={28} />
          ))}
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="text-[13px] font-semibold text-bright">
            {t('{count} pessoas ajudaram', { count: '\u0000' })
              .split('\u0000')
              .flatMap((part, index) => (index ? [<Count key="n" value={people.length} testId="stz-people-count" />, part] : [part]))}
          </div>
          <div className="text-[11.5px] text-muted">
            {t('{count} contribuições', { count: '\u0000' })
              .split('\u0000')
              .flatMap((part, index) => (index ? [<Count key="n" value={total} testId="stz-items-count" />, part] : [part]))}
          </div>
        </div>
      </div>
      <div className="gf-stz-views" role="tablist" aria-label={t('QUEM AJUDOU A CONSTRUIR')}>
        {views.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={view === key} data-view={key} className="gf-stz-view" onClick={() => setView(key)}>
            {view === key && (
              <motion.span layoutId="stz-view-active" className="gf-stz-view-active" transition={{ type: 'spring', stiffness: 520, damping: 38 }} />
            )}
            <span className="relative">{label}</span>
          </button>
        ))}
      </div>
      <div className="gf-stz-list" data-testid={`stz-view-${view}`}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={view}
            initial={{ opacity: 0, x: view === 'people' ? -8 : 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, transition: { duration: 0.08 } }}
            transition={{ duration: 0.16, ease: 'easeOut' }}
          >
            {view === 'people' ? <PeopleView people={people} /> : <VersionsView people={people} />}
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="mt-3 text-[12px] leading-snug text-muted">
        {t('💡 Teve uma ideia ou achou um bug? Conte no Discord — quem ajuda entra aqui.')}
      </div>
    </div>
  )
}

function PeopleView({ people }: { people: Contributor[] }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <LayoutGroup>
      <div className="space-y-2">
        {people.map((person, index) => (
          <PersonCard
            key={person.name}
            person={person}
            index={index}
            expanded={open === person.name}
            onToggle={() => setOpen(open === person.name ? null : person.name)}
          />
        ))}
      </div>
    </LayoutGroup>
  )
}

function PersonCard({ person, index, expanded, onToggle }: {
  person: Contributor
  index: number
  expanded: boolean
  onToggle: () => void
}) {
  useT()
  const count = person.items.length
  return (
    <motion.div
      layout
      className="gf-stz-person"
      style={{ '--person': person.color } as CSSProperties}
      data-person={person.name}
      data-count={count}
      data-expanded={expanded || undefined}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ layout: { type: 'spring', stiffness: 420, damping: 36 }, delay: 0.04 * index, duration: 0.2 }}
    >
      <motion.button layout="position" className="gf-stz-person-head" aria-expanded={expanded} onClick={onToggle}>
        <Avatar person={person} />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5">
            <span className="font-semibold text-bright">{person.name}</span>
            <span className="text-[11.5px] text-muted">
              {count === 1 ? t('1 contribuição') : t('{count} contribuições', { count })}
            </span>
            {person.since && <span className="ml-auto font-mono text-[10.5px] text-muted">{t('desde {version}', { version: person.since })}</span>}
          </span>
          <span className="mt-1 flex flex-wrap gap-1">
            {person.tags.map((tag) => (
              <span key={tag} className="gf-stz-tag" data-tag={tag}>
                {tagLabel(tag)}
              </span>
            ))}
          </span>
          {!expanded && person.items[0] && <span className="gf-stz-preview">{person.items[0].text}</span>}
        </span>
        <motion.span animate={{ rotate: expanded ? 90 : 0 }} transition={{ duration: 0.16 }} className="flex self-center text-muted">
          <Icon name="chevron-right" size={14} />
        </motion.span>
      </motion.button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.ul
            key="items"
            className="gf-stz-items"
            data-testid="stz-person-items"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
          >
            {person.items.map((item, position) => (
              <li key={position} className="flex gap-1.5">
                <span className="gf-stz-bullet">•</span>
                <span className="min-w-0 flex-1">{item.text}</span>
                {item.version && <span className="shrink-0 font-mono text-[10.5px] text-muted">{item.version}</span>}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

/** Linha do tempo: cada versão com o que cada pessoa trouxe ("0.7.0: Harlem — …"). */
function VersionsView({ people }: { people: Contributor[] }) {
  useT()
  const groups = useMemo(() => {
    const map = new Map<string, { person: Contributor; text: string }[]>()
    for (const person of people)
      for (const item of person.items) {
        const key = item.version ?? ''
        if (!map.has(key)) map.set(key, [])
        map.get(key)!.push({ person, text: item.text })
      }
    // Da versão mais nova para a mais antiga; o que não tem versão fica no fim.
    return [...map.entries()].sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : compareVersions(b, a)))
  }, [people])
  return (
    <ol className="gf-stz-timeline">
      {groups.map(([version, entries], index) => (
        <motion.li
          key={version || 'earlier'}
          className="gf-stz-timeline-version"
          data-version={version || 'earlier'}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 * index, duration: 0.2 }}
        >
          <div className="gf-stz-timeline-head">
            <span className="gf-stz-timeline-dot" />
            <span className="font-mono text-[12px] font-semibold text-accent-text">{version || t('Versões anteriores')}</span>
          </div>
          <ul className="gf-stz-timeline-items">
            {entries.map(({ person, text }, position) => (
              <li key={position} className="flex gap-2">
                <Avatar person={person} size={18} />
                <span className="min-w-0 flex-1">
                  <span className="font-semibold text-bright">{person.name}</span>
                  <span className="text-muted"> — </span>
                  {text}
                </span>
              </li>
            ))}
          </ul>
        </motion.li>
      ))}
    </ol>
  )
}

/** Ordem de versões como a do atualizador: 0.7.0-beta.1 < 0.7.0-beta.2 < 0.7.0. */
export function compareVersions(a: string, b: string): number {
  const parse = (text: string) => {
    const [main, pre] = text.split('-')
    return { parts: main.split('.').map((part) => Number(part) || 0), pre: pre ? Number(pre.replace(/\D+/g, '')) || 0 : Infinity }
  }
  const left = parse(a)
  const right = parse(b)
  for (let index = 0; index < Math.max(left.parts.length, right.parts.length); index += 1) {
    const diff = (left.parts[index] ?? 0) - (right.parts[index] ?? 0)
    if (diff) return diff
  }
  return left.pre === right.pre ? 0 : left.pre > right.pre ? 1 : -1
}
