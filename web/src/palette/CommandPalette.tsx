// Paleta de comandos (Ctrl+K): abrir XML do projeto pelo nome, selecionar elemento do XML
// aberto por WindowID ou tipo, comandos da janela (com o atalho de cada um) e projetos recentes.
// Só chama o que já existe (actions, doc/store, settings, atlas); não muda o layout da casca.
import { Command, defaultFilter } from 'cmdk'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { create } from 'zustand'
import { api, type HomeProject } from '../api'
import { goHome, openProject, openXml, publishToGame, showPage } from '../actions'
import { select, useDoc } from '../doc/store'
import { kindLabel } from '../elements/kinds'
import { LANGUAGES, setLanguage, t, useT } from '../i18n'
import { openSettings } from '../settings/SettingsScreen'
import { atlasAvailable, atlasModule } from '../shell/atlas'
import { redo, undo } from '../shell/doc'
import { saveDocument } from '../shell/saving'
import { THEMES, setTheme, useUi } from '../shell/uiState'
import { openSource } from '../source/SourcePanel'
import { setShell, useShell } from '../store'
import { Icon } from '../ui/Icon'
import './palette.css'

export const usePalette = create<{ open: boolean }>(() => ({ open: false }))

export function openPalette(): void {
  usePalette.setState({ open: true })
}

export function closePalette(): void {
  usePalette.setState({ open: false })
}

function joinPath(directory: string, relative: string): string {
  return `${directory.replace(/[\\/]+$/, '')}\\${relative.replace(/\//g, '\\')}`
}

function Item({ value, keywords, icon, hint, detail, disabled, onSelect, children }: {
  value: string
  keywords?: string[]
  icon: string
  hint?: string
  detail?: string
  disabled?: boolean
  onSelect: () => void
  children: ReactNode
}) {
  return (
    <Command.Item value={value} keywords={keywords} disabled={disabled} onSelect={onSelect} className="gf-palette-item">
      <Icon name={icon} size={15} className="shrink-0 text-icon" />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {detail && <span className="gf-palette-detail">{detail}</span>}
      {hint && <kbd className="gf-palette-kbd">{hint}</kbd>}
    </Command.Item>
  )
}

function Palette() {
  useT()
  const shell = useShell((state) => state.shell)
  const view = useShell((state) => state.view)
  const doc = useDoc((state) => state.doc)
  const selection = useDoc((state) => state.selection)
  const dirty = useDoc((state) => state.dirty)
  const canUndo = useDoc((state) => state.canUndo)
  const canRedo = useDoc((state) => state.canRedo)
  const theme = useUi((state) => state.theme)
  const [query, setQuery] = useState('')
  const [files, setFiles] = useState<{ name: string; path: string }[]>([])
  const [recent, setRecent] = useState<HomeProject[]>([])
  const input = useRef<HTMLInputElement>(null)
  const project = shell?.project ?? null
  const openPath = shell?.open_path ?? null
  const selected = selection[0] != null ? doc?.elements[selection[0]] : undefined

  useEffect(() => {
    input.current?.focus()
    let active = true
    api.homeData().then((data) => active && setRecent(data.projects.slice(0, 8)), () => undefined)
    if (shell?.project || shell?.loose_dir) {
      api.fileList('xml').then(
        (data) => {
          if (!active || !data.directory) return
          setFiles(data.files.map((name) => ({ name, path: joinPath(data.directory!, name) })))
        },
        () => undefined,
      )
    }
    return () => {
      active = false
    }
  }, [shell?.project, shell?.loose_dir])

  const run = (action: () => unknown) => {
    closePalette()
    // Depois de fechar: diálogos abertos pelo comando não disputam o foco com a paleta.
    window.setTimeout(() => void action(), 0)
  }

  const elements = useMemo(() => doc?.elements ?? [], [doc])
  const searching = query.trim().length > 0
  const themeNames = { dark: t('Escuro'), midnight: t('Meia-noite'), light: t('Claro') }

  return (
    <motion.div
      className="gf-palette-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closePalette()
      }}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label={t('Paleta de comandos')}
        className="gf-palette"
        data-testid="command-palette"
        initial={{ opacity: 0, y: -10, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -6, scale: 0.98 }}
        transition={{ duration: 0.14, ease: 'easeOut' }}
      >
        <Command
          label={t('Paleta de comandos')}
          loop
          // Procura pelo texto visível (keywords), não pelo valor interno ("xml:", "element:"…).
          filter={(value, search, keywords) => defaultFilter(keywords?.length ? keywords.join(' ') : value, search)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              event.stopPropagation()
              closePalette()
            }
          }}
        >
          <div className="gf-palette-search">
            <Icon name="search" size={16} className="text-muted" />
            <Command.Input
              ref={input}
              value={query}
              onValueChange={setQuery}
              placeholder={t('Digite um comando, o nome de um XML ou um WindowID…')}
              data-testid="command-input"
            />
            <kbd className="gf-palette-kbd">Esc</kbd>
          </div>
          <Command.List className="gf-palette-list">
            <Command.Empty className="gf-palette-empty">{t('Nenhum resultado.')}</Command.Empty>

            <Command.Group heading={t('Comandos')}>
              <Item value="cmd:publish" keywords={[t('Enviar para o jogo'), 'F5']} icon="send" hint="F5"
                disabled={!project?.game_dir} onSelect={() => run(() => publishToGame())}>
                {t('Enviar para o jogo')}
              </Item>
              <Item value="cmd:save" keywords={[t('Salvar')]} icon="save" hint="Ctrl+S" disabled={!dirty}
                onSelect={() => run(() => saveDocument())}>
                {t('Salvar')}
              </Item>
              <Item value="cmd:undo" keywords={[t('Desfazer')]} icon="undo" hint="Ctrl+Z" disabled={!canUndo}
                onSelect={() => run(() => undo())}>
                {t('Desfazer')}
              </Item>
              <Item value="cmd:redo" keywords={[t('Refazer')]} icon="redo" hint="Ctrl+Y" disabled={!canRedo}
                onSelect={() => run(() => redo())}>
                {t('Refazer')}
              </Item>
              <Item value="cmd:source" keywords={[t('Ver código XML'), 'xml', 'source']} icon="code" hint="Ctrl+U"
                disabled={!openPath || view !== 'workspace'} onSelect={() => run(() => openSource())}>
                {t('Ver código XML')}
              </Item>
              <Item value="cmd:atlas" keywords={[t('Abrir atlas do elemento'), 'atlas', 'dds']} icon="image"
                detail={selected?.id}
                disabled={!selected?.texture || !atlasAvailable()}
                onSelect={() => run(() => selected && atlasModule().then((atlas) => atlas?.openAtlas(selected.index)))}>
                {t('Abrir atlas do elemento')}
              </Item>
              <Item value="cmd:home" keywords={[t('Tela inicial')]} icon="home" onSelect={() => run(() => goHome())}>
                {t('Tela inicial')}
              </Item>
              <Item value="cmd:settings" keywords={[t('Configurações…')]} icon="settings" onSelect={() => run(() => openSettings())}>
                {t('Configurações…')}
              </Item>
              {THEMES.map((name) => (
                <Item key={name} value={`cmd:theme:${name}`} keywords={[t('Tema'), themeNames[name]]} icon="sparkles"
                  detail={theme === name ? '✓' : undefined} onSelect={() => run(() => setTheme(name))}>
                  {t('Tema')}: {themeNames[name]}
                </Item>
              ))}
              {LANGUAGES.map(([code, label]) => (
                <Item key={code} value={`cmd:language:${code}`} keywords={[t('Idioma'), label]} icon="language"
                  detail={shell?.language === code ? '✓' : undefined}
                  onSelect={() => run(async () => {
                    const state = await api.setLanguage(code)
                    setLanguage(code)
                    setShell(state)
                  })}>
                  {t('Idioma')}: {label}
                </Item>
              ))}
            </Command.Group>

            {searching && files.length > 0 && (
              <Command.Group heading={t('Arquivos XML')}>
                {files.map((file) => (
                  <Item key={file.path} value={`xml:${file.name}`} keywords={[file.name]} icon="file"
                    detail={file.path.toLowerCase() === openPath?.toLowerCase() ? t('aberto') : undefined}
                    onSelect={() => run(() => openXml(file.path))}>
                    {file.name}
                  </Item>
                ))}
              </Command.Group>
            )}

            {searching && elements.length > 0 && (
              <Command.Group heading={t('Elementos')}>
                {elements.map((element) => {
                  const kind = kindLabel(element.kind, element.ctrl_type)
                  return (
                    <Item key={element.index} value={`element:${element.index}`}
                      keywords={[element.id, kind, element.ctrl_type ?? '', element.kind]} icon="layers" detail={kind}
                      onSelect={() => run(() => {
                        showPage('elements')
                        select([element.index])
                      })}>
                      {element.id}
                    </Item>
                  )
                })}
              </Command.Group>
            )}

            {recent.length > 0 && (
              <Command.Group heading={t('Projetos recentes')}>
                {recent.map((item) => (
                  <Item key={item.root} value={`project:${item.root}`} keywords={[item.title]} icon="folder-open"
                    detail={item.current ? t('atual') : undefined}
                    onSelect={() => run(() => openProject(item.root))}>
                    {item.title}
                  </Item>
                ))}
              </Command.Group>
            )}
          </Command.List>
          <div className="gf-palette-footer">
            <span><kbd className="gf-palette-kbd">↑↓</kbd> {t('navegar')}</span>
            <span><kbd className="gf-palette-kbd">Enter</kbd> {t('executar')}</span>
            <span className="flex-1" />
            <span><kbd className="gf-palette-kbd">Ctrl+K</kbd></span>
          </div>
        </Command>
      </motion.div>
    </motion.div>
  )
}

export default function CommandPalette() {
  const open = usePalette((state) => state.open)
  return <AnimatePresence>{open && <Palette key="palette" />}</AnimatePresence>
}
