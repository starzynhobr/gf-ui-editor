// Tela inicial: continuar, novo/abrir/XML solto, projetos (filtro, tamanho, data, ⋯,
// Gerenciar) e, à direita, Novidades e Como funciona. Mesma organização da clássica.
import { useEffect, useMemo, useState } from 'react'
import { api, type HomeData, type HomeProject } from '../api'
import { on } from '../bridge'
import { relativeAge, useT } from '../i18n'
import { useShell } from '../store'
import {
  browseProject,
  continueProject,
  deleteProjects,
  duplicateProject,
  newProject,
  openLooseXml,
  openProject,
  renameProject,
} from '../actions'
import { Icon } from '../ui/Icon'
import { openMenuAt } from '../ui/Menu'
import { openWhatsNew } from './WhatsNewDialog'
import { saveProjectVersion, showCleanup, showPull, showVersions } from '../project/flows'
import { useListAnimation } from '../ui/animate'

const ROW = 'grid grid-cols-[minmax(0,1fr)_70px_74px_92px_28px] items-center gap-2.5'

export default function HomeScreen() {
  const t = useT()
  const animateProjects = useListAnimation()
  const revision = useShell((state) => state.revision)
  const [data, setData] = useState<HomeData | null>(null)
  const [sizes, setSizes] = useState<Record<string, string>>({})
  const [filter, setFilter] = useState('')
  const [manage, setManage] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  useEffect(() => on('project_size', (payload) => {
    const { root, size } = payload as { root: string; size: string }
    setSizes((current) => ({ ...current, [root]: size }))
  }), [])

  useEffect(() => {
    let alive = true
    void api.homeData().then((value) => alive && setData(value))
    return () => {
      alive = false
    }
  }, [revision])

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return (data?.projects ?? []).filter((project) => project.title.toLowerCase().includes(needle))
  }, [data, filter])

  const toggle = (root: string) =>
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(root)) next.delete(root)
      else next.add(root)
      return next
    })

  const setManaging = (enabled: boolean) => {
    setManage(enabled)
    if (!enabled) setSelected(new Set())
  }

  const rowMenu = (element: HTMLElement, project: HomeProject) =>
    openMenuAt(
      element,
      [
        { label: t('Abrir'), icon: 'folder-open', onClick: () => void openProject(project.root) },
        { label: t('Abrir pasta'), icon: 'file', onClick: () => void api.openFolder(project.root) },
        { separator: true },
        { label: t('Duplicar…'), icon: 'copy', onClick: () => void duplicateProject(project.root, project.title) },
        { label: t('Renomear…'), icon: 'type', onClick: () => void renameProject(project.root, project.title) },
        { separator: true },
        { label: t('Salvar versão…'), icon: 'save', onClick: () => void saveProjectVersion(project.root) },
        { label: t('Versões do projeto…'), icon: 'layers', onClick: () => void showVersions(project.root, project.title) },
        { label: t('Puxar da pasta do jogo…'), icon: 'file-import', onClick: () => void showPull(project.root, project.title) },
        { label: t('Limpar projeto…'), icon: 'sparkles', onClick: () => void showCleanup(project.root) },
        { separator: true },
        { label: t('Excluir…'), icon: 'trash', danger: true, onClick: () => void deleteProjects([project.root]) },
      ],
      true,
    )

  const actions = [
    { icon: 'folder-plus', heading: t('Novo projeto'), text: t('Da UI em uso, de uma UI do UICustom ou de outra pasta.'), run: () => newProject() },
    { icon: 'folder-open', heading: t('Abrir projeto'), text: t('Um projeto salvo em outra pasta.'), run: browseProject },
    { icon: 'file', heading: t('XML solto'), text: t('Um arquivo só, sem projeto (o launcher pode sobrescrever).'), run: openLooseXml },
  ]

  const card = data?.continue
  return (
    <div className="h-full overflow-y-auto" data-testid="home">
      <div className="mx-auto flex max-w-[1180px] gap-5 px-7 py-6">
        <div className="min-w-0 flex-1 space-y-3.5">
          {card ? (
            <section className="card border-accent-border/40 bg-gradient-to-br from-accent-soft/70 to-card px-4 py-3.5">
              <div className="section-label mb-2.5">{t('CONTINUAR DE ONDE PAROU')}</div>
              <div className="flex items-center gap-3">
                <Icon name="package" size={26} className="self-start text-accent-text" />
                <div className="min-w-0 flex-1">
                  <div className="text-[15px] font-semibold text-bright">{card.name}</div>
                  <div className="mt-0.5 text-muted">
                    {[
                      card.last_file,
                      t('{count} alterados', { count: card.modified }),
                      card.has_game ? t('envia para UICustom/{folder}', { folder: card.custom_name }) : '',
                      t('editado {when}', { when: relativeAge(card.age) }),
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </div>
                <button className="btn btn-primary px-5" onClick={() => void continueProject()}>
                  {t('Continuar')}
                </button>
              </div>
              <div className="mt-3 flex gap-1.5">
                <button className="btn h-7" title={card.ui_dir} onClick={() => void api.openFolder(card.ui_dir)}>
                  <Icon name="folder-open" size={15} />
                  {t('Abrir pasta do projeto')}
                </button>
                <button className="btn h-7" data-testid="home-save-version" onClick={() => void saveProjectVersion(card.root)}>
                  <Icon name="save" size={15} />
                  {t('Salvar versão')}
                </button>
                <button className="btn h-7" data-testid="home-versions" onClick={() => void showVersions(card.root, card.name)}>
                  {t('Versões…')}
                </button>
                <button className="btn h-7" data-testid="home-pull" onClick={() => void showPull(card.root, card.name)}>
                  <Icon name="file-import" size={15} />
                  {t('Puxar do jogo')}
                </button>
              </div>
            </section>
          ) : (
            <section className="space-y-1.5 pb-1">
              <h1 className="text-[22px] font-semibold text-bright">{t('Comece um projeto de UI')}</h1>
              <p className="max-w-[640px] text-[13.5px] leading-relaxed text-muted">
                {t('Você edita uma cópia fora da pasta do jogo. Quando quiser ver o resultado, aperte F5 para enviar ao jogo e inicie-o pelo launcher.')}
              </p>
            </section>
          )}

          <div className="grid grid-cols-3 gap-2.5">
            {actions.map((action) => (
              <button
                key={action.icon}
                className="card group flex min-h-[112px] flex-col items-start gap-1 px-3.5 py-3 text-left transition-colors hover:border-accent-border/50 hover:bg-hover"
                onClick={() => void action.run()}
              >
                <Icon name={action.icon} size={20} className="mb-1 text-icon group-hover:text-accent-text" />
                <span className="text-[14px] font-semibold text-bright">{action.heading}</span>
                <span className="text-[12px] leading-snug text-muted">{action.text}</span>
              </button>
            ))}
          </div>

          <section className="card px-3.5 py-3" data-testid="home-projects">
            <div className="mb-2 flex items-center gap-2">
              <div className="section-label flex-1">{t('PROJETOS · {count}', { count: data?.projects.length ?? 0 })}</div>
              <div className="relative">
                <Icon name="search" size={14} className="pointer-events-none absolute top-2 left-2.5 text-disabled" />
                <input
                  className="field h-7 w-[220px] pl-7"
                  placeholder={t('Filtrar projetos…')}
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                />
              </div>
              <button
                className={`btn h-7 ${manage ? 'border-accent-border/60 bg-accent-soft text-accent-text' : ''}`}
                title={t('Selecionar vários projetos para excluir de uma vez')}
                onClick={() => setManaging(!manage)}
              >
                <Icon name="trash" size={14} />
                {t('Gerenciar')}
              </button>
            </div>
            <div className={`${ROW} section-label px-2.5 pb-1`}>
              <span>{t('Nome')}</span>
              <span>{t('Arquivos')}</span>
              <span>{t('Tamanho')}</span>
              <span>{t('Editado')}</span>
              <span />
            </div>
            <div ref={animateProjects}>
              {visible.map((project) => (
                <div
                  key={project.root}
                  role="button"
                  title={project.root}
                  data-testid="home-project-row"
                  className={`${ROW} group h-[38px] rounded-md px-2.5 hover:bg-hover ${selected.has(project.root) ? 'bg-selected' : ''}`}
                  onClick={() => (manage ? toggle(project.root) : void openProject(project.root))}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    {manage && (
                      <input
                        type="checkbox"
                        checked={selected.has(project.root)}
                        onClick={(event) => event.stopPropagation()}
                        onChange={() => toggle(project.root)}
                      />
                    )}
                    <span className="truncate font-medium text-bright">{project.title}</span>
                    {project.current && (
                      <span className="rounded-full bg-accent-soft px-2 py-px text-[11px] text-accent-text">{t('aberto')}</span>
                    )}
                  </span>
                  <span className="font-mono text-[12px] text-muted">{project.files ?? '—'}</span>
                  <span className="font-mono text-[12px] text-muted">{sizes[project.root] ?? project.size ?? '…'}</span>
                  <span className="text-[12px] text-muted">{relativeAge(project.age)}</span>
                  <button
                    className="icon-button opacity-60 group-hover:opacity-100"
                    title={t('Mais ações')}
                    aria-label={t('Mais ações')}
                    onClick={(event) => {
                      event.stopPropagation()
                      rowMenu(event.currentTarget, project)
                    }}
                  >
                    <Icon name="dots" size={18} />
                  </button>
                </div>
              ))}
              {data && visible.length === 0 && (
                <div className="px-2.5 py-3 text-muted">
                  {data.projects.length ? t('Nenhum projeto com esse nome.') : t('Nenhum projeto ainda. Crie o primeiro em Novo projeto.')}
                </div>
              )}
            </div>
            {manage && (
              <div className="mt-1.5 flex items-center gap-2 border-t border-border px-2.5 pt-2.5">
                <span className="flex-1 text-muted">
                  {selected.size ? t('{count} selecionado(s)', { count: selected.size }) : t('Marque os projetos que quer excluir.')}
                </span>
                {selected.size > 0 && (
                  <button
                    className="btn btn-danger h-7"
                    data-testid="delete-selected"
                    onClick={async () => {
                      if (await deleteProjects([...selected])) setManaging(false)
                    }}
                  >
                    <Icon name="trash" size={14} />
                    {t('Excluir selecionados…')}
                  </button>
                )}
              </div>
            )}
          </section>
        </div>

        <aside className="w-[280px] shrink-0 space-y-3">
          <section className="card px-3.5 py-3">
            <div className="section-label mb-2">{t('NOVIDADES · {version}', { version: data?.version ?? '' })}</div>
            {data && data.news.length ? (
              <ul className="space-y-1.5 text-[12.5px] leading-snug text-text">
                {data.news.map((title) => (
                  <li key={title} className="flex gap-2">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-accent-text" />
                    {title}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-muted">{t('Sem novidades registradas.')}</div>
            )}
            <button className="link mt-2.5 text-[12.5px]" onClick={() => void openWhatsNew()}>
              {t('Ver todas')}
            </button>
          </section>
          <section className="card px-3.5 py-3">
            <div className="section-label mb-2">{t('COMO FUNCIONA')}</div>
            <ol className="space-y-1.5 text-[12.5px] leading-snug text-text">
              <li>{t('1. O projeto é a sua cópia segura da UI.')}</li>
              <li>{t('2. Edite aqui, clicando e arrastando, ou no Notepad++ e aperte Ctrl+R.')}</li>
              <li>{t('3. F5 envia para o jogo; é só abrir pelo launcher.')}</li>
            </ol>
            <button className="link mt-2.5 inline-flex items-center gap-1 text-[12.5px]" onClick={() => data && void api.openUrl(data.how_to_url)}>
              {t('Ver o vídeo')}
              <Icon name="external-link" size={13} />
            </button>
          </section>
        </aside>
      </div>
    </div>
  )
}
