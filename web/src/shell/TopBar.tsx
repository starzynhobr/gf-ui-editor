// Barra superior: casinha, projeto ˅ / arquivo, salvar e, à direita, Exportar e Enviar · N.
import StzPill from './StzPill'
import WhatsNewPill from './WhatsNewPill'
import { useEffect, useState } from 'react'
import { api, type HomeProject } from '../api'
import { useT } from '../i18n'
import { useShell } from '../store'
import { browseProject, exportZip, goHome, newProject, openProject, publishToGame } from '../actions'
import { Icon } from '../ui/Icon'
import { redo, undo, useDocState, useEditingAvailable } from './doc'
import { saveDocument } from './saving'
import { isStandalone } from '../doc/standalone'
import { toggleSource, useSource } from '../source/SourcePanel'
import { openMenuAt, type MenuItem } from '../ui/Menu'
import { openResolutionsDialog } from '../resolutions/ResolutionsDialog'
import {
  convertProjectToLight, exportTexts, openOfficialCompare, openOfficialReference, resolveGameError, saveProjectVersion, showCleanup, showPull, showVersions,
} from '../project/flows'

export default function TopBar() {
  const t = useT()
  const shell = useShell((state) => state.shell)
  const [recent, setRecent] = useState<HomeProject[]>([])
  const project = shell?.project ?? null
  const fileName = shell?.open_path?.split(/[\\/]/).pop() ?? null
  const pending = shell?.pending ?? 0
  const standalone = isStandalone(shell)
  const canPublish = Boolean(project?.game_dir)
  const dirty = useDocState((state) => state.dirty)
  const canUndo = useDocState((state) => state.canUndo)
  const canRedo = useDocState((state) => state.canRedo)
  const editable = useEditingAvailable()
  const sourceOpen = useSource((state) => state.open)

  useEffect(() => {
    const marker = dirty ? ' *' : ''
    document.title = project ? `STZ GF UI [${project.name}]${fileName ? ` — ${fileName}${marker}` : ''}` : `STZ GF UI${fileName ? ` — ${fileName}${marker}` : ''}`
  }, [project, fileName, dirty])

  const loadRecent = async () => {
    const data = await api.homeData()
    setRecent(data.projects.slice(0, 8))
    return data.projects.slice(0, 8)
  }

  const projectMenu = async (element: HTMLElement) => {
    const list = await loadRecent().catch(() => recent)
    const items: MenuItem[] = [
      { label: t('Novo projeto…'), icon: 'folder-plus', hint: 'Ctrl+Shift+N', onClick: () => void newProject() },
      { label: t('Abrir projeto…'), icon: 'folder-open', hint: 'Ctrl+Shift+O', onClick: () => void browseProject() },
      {
        label: t('Projetos recentes'),
        submenu: list.length
          ? list.map((item) => ({ label: item.title, checked: item.current, onClick: () => void openProject(item.root) }))
          : [{ label: t('Nenhum projeto ainda. Crie o primeiro em Novo projeto.'), disabled: true }],
      },
      { separator: true },
      { label: t('Tela inicial'), icon: 'home', onClick: () => void goHome() },
      { label: t('Abrir pasta do projeto'), icon: 'file', disabled: !project, onClick: () => project && void api.openFolder(project.root) },
      { separator: true },
      { label: t('Salvar versão…'), icon: 'save', disabled: !project, onClick: () => project && void saveProjectVersion(project.root) },
      { label: t('Versões do projeto…'), icon: 'layers', disabled: !project, onClick: () => project && void showVersions(project.root, project.name) },
      { label: t('Converter em projeto leve…'), disabled: !project?.game_dir, onClick: () => void convertProjectToLight() },
      { label: t('Puxar da pasta do jogo…'), icon: 'file-import', disabled: !project?.game_dir, onClick: () => project && void showPull(project.root, project.name) },
      { label: t('Limpar projeto…'), icon: 'sparkles', disabled: !project, onClick: () => project && void showCleanup(project.root) },
      { separator: true },
      { label: t('UI oficial de referência…'), icon: 'package', disabled: !project?.game_dir, onClick: () => void openOfficialReference() },
      { label: t('Comparar com a UI oficial…'), icon: 'search', disabled: !project?.game_dir, onClick: () => void openOfficialCompare() },
      { label: t('Resolver erro do jogo…'), icon: 'alert', onClick: () => void resolveGameError() },
      { label: t('Exportar textos (.zip)…'), icon: 'type', disabled: !project?.game_dir, onClick: () => void exportTexts() },
    ]
    openMenuAt(element, items)
  }

  const projectTip = project
    ? [t('Editando em: {path}', { path: project.ui_dir }), project.publish_dir ? t('Publica em: {path}', { path: project.publish_dir }) : '']
        .filter(Boolean)
        .join('\n')
    : shell?.loose_dir
      ? t('Editando em: {path}', { path: shell.loose_dir })
      : ''

  return (
    <header className="relative flex h-11 shrink-0 items-center gap-1 border-b border-border bg-chrome px-2" data-testid="topbar">
      <button className="icon-button h-8 w-8" title={t('Tela inicial: fecha o XML aberto e mostra os projetos recentes')} onClick={() => void goHome()}>
        <Icon name="home" size={18} />
      </button>
      <button
        className="flex h-8 max-w-[280px] items-center gap-1.5 rounded-md px-2.5 font-semibold text-bright hover:bg-hover"
        title={projectTip}
        data-testid="project-button"
        onClick={(event) => void projectMenu(event.currentTarget)}
      >
        <span className="truncate">{project ? project.name : t('Sem projeto')}</span>
        <Icon name="chevron-down" size={14} className="text-muted" />
      </button>
      {fileName && (
        <div className="flex min-w-0 items-center gap-2 text-[12px]" data-testid="breadcrumb">
          <span className="text-muted">/</span>
          <span className="truncate font-mono text-text" title={shell?.open_path ?? ''}>
            {fileName}
          </span>
          {standalone && (
            <span
              className="gf-standalone-badge"
              title={t('Arquivo avulso, de fora do projeto: {path}', { path: shell?.open_path ?? '' })}
              data-testid="standalone-badge"
            >
              {t('Avulso')}
            </span>
          )}
          {dirty && (
            <span className="text-gold" title={t('alterado')} data-testid="dirty-marker">
              ●
            </span>
          )}
        </div>
      )}
      <div className="mx-1.5 h-5 w-px bg-border" />
      <button
        className="btn btn-ghost h-8 px-2"
        disabled={!dirty || !editable}
        title={`${t('Salvar com backup')} (Ctrl+S)`}
        data-testid="save"
        onClick={() => void saveDocument()}
      >
        <Icon name="save" size={16} />
        {t('Salvar')}
      </button>
      <button className="icon-button h-8 w-8" disabled={!canUndo} title={`${t('Desfazer')} (Ctrl+Z)`} aria-label={t('Desfazer')} onClick={() => void undo()}>
        <Icon name="undo" size={17} />
      </button>
      <button className="icon-button h-8 w-8" disabled={!canRedo} title={`${t('Refazer')} (Ctrl+Y)`} aria-label={t('Refazer')} onClick={() => void redo()}>
        <Icon name="redo" size={17} />
      </button>
      {fileName && (
        <button
          className={`icon-button h-8 w-8 ${sourceOpen ? 'bg-accent-soft text-accent-text' : ''}`}
          title={`${t('Ver código XML')} (Ctrl+U)`}
          aria-label={t('Ver código XML')}
          aria-pressed={sourceOpen}
          data-testid="view-source"
          onClick={toggleSource}
        >
          <Icon name="code" size={17} />
        </button>
      )}
      <div className="flex-1" data-topbar-spacer />
      <div className="pointer-events-none absolute inset-y-0 left-1/2 z-40 flex -translate-x-1/2 items-center">
        <div className="pointer-events-auto">
          <StzPill />
        </div>
      </div>
      <WhatsNewPill />
      <div className="flex">
        <button
          className="btn h-8 rounded-r-none"
          disabled={!project}
          title={project ? undefined : t('Exportar a UI precisa de um projeto aberto.')}
          onClick={() => void exportZip()}
          data-testid="export-zip"
        >
          <Icon name="package" size={16} />
          {t('Exportar UI (.zip)…')}
        </button>
        <button
          className="btn h-8 w-7 rounded-l-none border-l-0 px-0"
          disabled={!project}
          aria-label={t('Mais opções de exportar')}
          title={t('Mais opções de exportar')}
          data-testid="export-menu"
          onClick={(event) =>
            openMenuAt(event.currentTarget, [
              { label: t('Exportar UI (.zip)…'), icon: 'package', onClick: () => void exportZip() },
              { label: t('Exportar para várias resoluções…'), icon: 'layout', onClick: () => void openResolutionsDialog() },
            ], true)
          }
        >
          <Icon name="chevron-down" size={14} />
        </button>
      </div>
      <button
        className="btn btn-primary ml-1 h-8"
        disabled={!canPublish}
        data-testid="publish"
        title={
          pending
            ? t('{count} arquivo(s) salvos no projeto ainda não estão no jogo. F5 envia.', { count: pending })
            : t('Publica o projeto em UICustom e na pasta UI do jogo e o seleciona no launcher (F5)')
        }
        onClick={() => void publishToGame()}
      >
        <Icon name="send" size={16} />
        {t('Enviar para o jogo')}
        {pending > 0 && (
          <span className="rounded-full bg-white/20 px-1.5 font-mono text-[11px]" data-testid="publish-count">
            {pending}
          </span>
        )}
      </button>
    </header>
  )
}
