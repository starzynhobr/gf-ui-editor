// Notas de versão longas, usadas no "Novidades" (home/WhatsNewDialog) e no atualizador
// (UpdateDialog): destaques no topo, chips de categoria que filtram, lista recolhível
// (acordeão) e, com mais de uma versão, uma linha do tempo à esquerda que pula até cada uma.
// As seções seguem a ordem da clássica (Novo, Melhorado, Corrigido).
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { t, useT } from '../i18n'
import { useListAnimation } from '../ui/animate'
import { Icon } from '../ui/Icon'
import type { ReleaseSections } from './settingsApi'
import './settings.css'

export interface Release {
  version: string
  date: string
  sections: ReleaseSections
}

type Section = keyof ReleaseSections
type Filter = 'all' | Section

const SECTIONS: Section[] = ['new', 'improved', 'fixed']
const HIGHLIGHTS = 4 // primeiros itens de "Novo" de cada versão que viram cartões

const SECTION_CLASS: Record<Section, string> = { new: 'is-new', improved: 'is-improved', fixed: 'is-fixed' }

function sectionLabel(section: Section): string {
  return { new: t('Novo'), improved: t('Melhorado'), fixed: t('Corrigido') }[section]
}

function sectionHeading(section: Section): string {
  return { new: t('NOVO'), improved: t('MELHORADO'), fixed: t('CORRIGIDO') }[section]
}

// Ícone do cartão de destaque pelo título (nos 4 idiomas); sem palavra conhecida, uma estrela.
const ICON_RULES: [RegExp, string][] = [
  [/inicial|home|inicio|inicio|accueil/i, 'home'],
  [/envi|send|envoy|publi/i, 'send'],
  [/limp|clean|nettoy/i, 'trash'],
  [/puxa|pull|traer|récup|recup/i, 'arrow-down'],
  [/vers/i, 'layers'],
  [/projet|project|proyect/i, 'folder-open'],
  [/xml|código|code/i, 'code'],
  [/fonte|font|fuente|police|texto|text/i, 'type'],
  [/atalho|shortcut|atajo|raccourci/i, 'command'],
  [/zoom/i, 'focus'],
  [/seç|section|secci/i, 'layout'],
  [/tema|theme|thème/i, 'sparkles'],
  [/abrir|open|ouvrir/i, 'external-link'],
  [/textur|dds|atlas/i, 'image'],
]

export function highlightIcon(title: string): string {
  return ICON_RULES.find(([rule]) => rule.test(title))?.[1] ?? 'sparkles'
}

interface Entry {
  key: string
  section: Section
  title: string
  text: string
}

interface Prepared {
  release: Release
  highlights: Entry[]
  rest: Entry[]
}

function prepare(releases: Release[]): Prepared[] {
  return releases.map((release) => {
    const entries = SECTIONS.flatMap((section) =>
      (release.sections[section] ?? []).map(([title, text], index) => ({ key: `${release.version}:${section}:${index}`, section, title, text })),
    )
    const highlights = entries.filter((entry) => entry.section === 'new').slice(0, HIGHLIGHTS)
    // Com só um ou dois itens não há o que destacar: tudo fica na lista.
    const useHighlights = entries.length > HIGHLIGHTS && highlights.length >= 3
    return {
      release,
      highlights: useHighlights ? highlights : [],
      rest: useHighlights ? entries.filter((entry) => !highlights.includes(entry)) : entries,
    }
  })
}

export function ReleaseNotes({ releases, showVersion = true }: { releases: Release[]; showVersion?: boolean }) {
  useT()
  const prepared = useMemo(() => prepare(releases), [releases])
  const [filter, setFilter] = useState<Filter>('all')
  const [open, setOpen] = useState<Set<string>>(() => new Set())
  const [active, setActive] = useState(releases[0]?.version ?? '')
  const scroller = useRef<HTMLDivElement>(null)
  const timeline = releases.length > 1

  const counts = useMemo(() => {
    const result: Record<Section, number> = { new: 0, improved: 0, fixed: 0 }
    for (const release of releases) for (const section of SECTIONS) result[section] += release.sections[section]?.length ?? 0
    return result
  }, [releases])
  const total = counts.new + counts.improved + counts.fixed

  const visible = prepared
    .map((item) => ({
      ...item,
      highlights: filter === 'all' || filter === 'new' ? item.highlights : [],
      rest: item.rest.filter((entry) => filter === 'all' || entry.section === filter),
    }))
    .filter((item) => item.highlights.length + item.rest.length > 0)
  const listed = visible.flatMap((item) => item.rest)
  const allOpen = listed.length > 0 && listed.every((entry) => open.has(entry.key))

  // Linha do tempo: a versão ativa é a que está no topo da área rolada.
  useEffect(() => {
    const box = scroller.current
    if (!box || !timeline) return
    const onScroll = () => {
      const top = box.getBoundingClientRect().top
      let current = visible[0]?.release.version ?? ''
      for (const node of box.querySelectorAll<HTMLElement>('[data-release]')) {
        if (node.getBoundingClientRect().top - top <= 24) current = node.dataset.release ?? current
      }
      setActive(current)
    }
    onScroll()
    box.addEventListener('scroll', onScroll, { passive: true })
    return () => box.removeEventListener('scroll', onScroll)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `visible` deriva de filter e prepared
  }, [timeline, filter, prepared])

  const jump = (version: string) => {
    const box = scroller.current
    const node = box?.querySelector<HTMLElement>(`[data-release="${CSS.escape(version)}"]`)
    if (!box || !node) return
    setActive(version)
    box.scrollTo({ top: node.offsetTop, behavior: 'smooth' })
  }

  const toggle = (key: string) =>
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const chips: [Filter, string, number][] = [
    ['all', t('Tudo'), total],
    ...SECTIONS.filter((section) => counts[section] > 0).map((section): [Filter, string, number] => [section, sectionLabel(section), counts[section]]),
  ]

  return (
    <div className="gf-notes" data-testid="release-notes">
      <div className="gf-notes-toolbar">
        <div className="gf-notes-chips" role="radiogroup" aria-label={t('Filtrar por categoria')}>
          {chips.map(([value, label, count]) => (
            <button
              key={value}
              role="radio"
              aria-checked={filter === value}
              className={`gf-notes-chip ${value === 'all' ? '' : SECTION_CLASS[value]}`}
              data-filter={value}
              onClick={() => setFilter(filter === value && value !== 'all' ? 'all' : value)}
            >
              {filter === value && (
                <motion.span layoutId="notes-chip-active" className="gf-notes-chip-active" transition={{ type: 'spring', stiffness: 520, damping: 38 }} />
              )}
              <span className="relative">{label}</span>
              <span className="gf-notes-chip-count relative">{count}</span>
            </button>
          ))}
        </div>
        <div className="flex-1" />
        {listed.length > 0 && (
          <button
            className="link text-[12px]"
            data-testid="notes-toggle-all"
            onClick={() => setOpen(allOpen ? new Set() : new Set(listed.map((entry) => entry.key)))}
          >
            {allOpen ? t('Recolher tudo') : t('Expandir tudo')}
          </button>
        )}
      </div>
      <div className={timeline ? 'gf-notes-body has-timeline' : 'gf-notes-body'}>
        {timeline && (
          <nav className="gf-notes-timeline" aria-label={t('Versões')} data-testid="notes-timeline">
            {visible.map(({ release }) => (
              <button
                key={release.version}
                className="gf-notes-timeline-item"
                aria-current={active === release.version ? 'true' : undefined}
                data-version={release.version}
                onClick={() => jump(release.version)}
              >
                {active === release.version && (
                  <motion.span layoutId="notes-timeline-active" className="gf-notes-timeline-active" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />
                )}
                <span className="gf-notes-timeline-dot" />
                <span className="relative min-w-0">
                  <span className="block truncate font-mono text-[12px]">{release.version}</span>
                  {release.date && <span className="block truncate text-[11px] text-muted">{release.date}</span>}
                </span>
              </button>
            ))}
          </nav>
        )}
        <div ref={scroller} className={timeline ? 'gf-notes-scroll' : undefined} data-testid="notes-scroll">
          {visible.length === 0 && <div className="py-6 text-center text-muted">{t('Nada nesta categoria.')}</div>}
          {visible.map((item, index) => (
            <ReleaseBlock
              key={item.release.version}
              item={item}
              index={index}
              showVersion={showVersion || timeline}
              open={open}
              toggle={toggle}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function ReleaseBlock({ item, index, showVersion, open, toggle }: {
  item: Prepared
  index: number
  showVersion: boolean
  open: Set<string>
  toggle: (key: string) => void
}) {
  const list = useListAnimation<HTMLDivElement>()
  const { release, highlights, rest } = item
  return (
    <section className="gf-notes-release" data-release={release.version}>
      {showVersion && (
        <div className="gf-notes-release-head">
          <span className="gf-version-chip font-mono text-[12px]">{release.version}</span>
          {release.date && <span className="text-[12px] text-muted">{release.date}</span>}
        </div>
      )}
      {highlights.length > 0 && (
        <div className="gf-notes-highlights" data-testid="notes-highlights">
          {highlights.map((entry, position) => (
            <motion.div
              key={entry.key}
              className="gf-notes-highlight"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.03 * (index * HIGHLIGHTS + position), duration: 0.22, ease: 'easeOut' }}
            >
              <span className="gf-notes-highlight-icon">
                <Icon name={highlightIcon(entry.title)} size={16} />
              </span>
              <div className="min-w-0">
                <div className="font-semibold text-bright">{entry.title}</div>
                <div className="mt-0.5 text-[12px] leading-snug text-muted">{entry.text}</div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
      <div ref={list} className="gf-notes-list">
        {rest.map((entry, position) => {
          const first = position === 0 || rest[position - 1].section !== entry.section
          const expanded = open.has(entry.key)
          return (
            <div key={entry.key}>
              {first && <div className={`section-label gf-notes-section ${SECTION_CLASS[entry.section]}`}>{sectionHeading(entry.section)}</div>}
              <div className={`gf-notes-item ${SECTION_CLASS[entry.section]}`} data-expanded={expanded || undefined}>
                <button className="gf-notes-item-head" aria-expanded={expanded} onClick={() => toggle(entry.key)}>
                  <span className="gf-notes-item-dot" />
                  <span className="min-w-0 flex-1 font-semibold text-bright">{entry.title}</span>
                  <motion.span animate={{ rotate: expanded ? 90 : 0 }} transition={{ duration: 0.16 }} className="flex text-muted">
                    <Icon name="chevron-right" size={14} />
                  </motion.span>
                </button>
                <AnimatePresence initial={false}>
                  {expanded && (
                    <motion.div
                      key="text"
                      className="overflow-hidden"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.18, ease: 'easeOut' }}
                    >
                      <div className="gf-notes-item-text">{entry.text}</div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
