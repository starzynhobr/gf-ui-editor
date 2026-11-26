// Casca da interface nova: barra superior, lateral, centro (tela inicial ou canvas) e status.
// O canvas é do bloco do canvas: a casca só monta <CanvasView path=... />.
import { TooltipHost } from './ui/TooltipHost'
import { Toaster } from 'sonner'
import { ResizeHandle } from './ui/ResizeHandle'
import { isLightTheme, loadUiState, panelWidth, useUi } from './shell/uiState'
import { useEffect, useState } from 'react'
import { api, errorText } from './api'
import { setLanguage, useT } from './i18n'
import { setShell, useShell } from './store'
import CanvasView from './canvas/CanvasView'
import FilesPanel from './files/FilesPanel'
import ElementTree from './elements/ElementTree'
import PropertiesPanel from './elements/PropertiesPanel'
import DocSync from './shell/DocSync'
import { selectElements, useEditingAvailable } from './shell/doc'
import HomeScreen from './home/HomeScreen'
import TextsPage from './texts/TextsPage'
import Banners from './project/Banners'
import { installOfficialEvents, startOfficialScan } from './project/official'
import { installGameTextEditing } from './shell/gameText'
import { checkTextUpdates } from './project/textUpdates'
import ProgressOverlay from './shell/ProgressOverlay'
import SideRail from './shell/SideRail'
import StatusBar from './shell/StatusBar'
import TopBar from './shell/TopBar'
import { installShortcuts } from './shell/shortcuts'
import { DialogHost } from './ui/dialogs'
import SettingsHost, { useSettings } from './settings/SettingsScreen'
import { startupChecks } from './settings/updates'
import { startWhatsNew } from './home/WhatsNewDialog'
import { useWhatsNew } from './home/whatsNew'
import { openExternalXml, openProject } from './actions'
import { call, on } from './bridge'
import { MenuHost } from './ui/Menu'
import SourcePanel from './source/SourcePanel'
import './doc/standalone.css'
import StandaloneBar from './doc/StandaloneBar'
import DropOverlay from './doc/DropOverlay'
import ExternalChangeBand, { installExternalChangeStub } from './doc/ExternalChangeBand'
import CanvasHoverTip, { CanvasHoverToggle } from './shell/CanvasHoverTip'
import { setCanvasHover } from './shell/canvasHover'
import CommandPalette from './palette/CommandPalette'

export default function App() {
  const layout = useUi((state) => state.layout)
  const theme = useUi((state) => state.theme)
  const leftWidth = panelWidth('left', layout)
  const rightWidth = panelWidth('right', layout)
  useT()
  const view = useShell((state) => state.view)
  const page = useShell((state) => state.page)
  const shell = useShell((state) => state.shell)
  const storeReady = useEditingAvailable()
  const canvasEpoch = useSettings((state) => state.canvasEpoch)
  const [error, setError] = useState<string | null>(null)
  const shellMounted = shell !== null && !error
  // Abertura automática das Novidades: os banners (UI oficial não guardada etc.) esperam.
  const notesHold = useWhatsNew((state) => state.hold)

  useEffect(() => {
    if (shellMounted) void call('shell_ready').catch(() => {})
  }, [shellMounted])

  useEffect(() => {
    void loadUiState()
    api.startup().then(
      ({ view: first, ...state }) => {
        setLanguage(state.language)
        setShell(state, { view: first })
        // Novidades primeiro (abrem sozinhas uma vez depois de atualizar); os outros avisos esperam
        // elas fecharem. Depois, como a clássica: a verificação de atualização e o manifesto.
        void startWhatsNew().then((shown) => window.setTimeout(() => void startupChecks(), shown ? 900 : 2500))
      },
      (reason) => setError(errorText(reason)),
    )
    const uninstall = installOfficialEvents()
    const unshortcut = installShortcuts()
    const ungameText = installGameTextEditing()
    const unexternalChange = installExternalChangeStub()
    // Outro .exe ("Abrir com") mandou um XML para esta janela.
    const unexternal = on('open_external', (payload) => {
      const { path, project } = payload as { path: string; project?: boolean }
      void (project ? openProject(path) : openExternalXml(path))
    })
    return () => {
      unexternal()
      unexternalChange()
      uninstall()
      unshortcut()
      ungameText()
    }
  }, [])

  const projectRoot = shell?.project?.root ?? null
  useEffect(() => {
    startOfficialScan(projectRoot)
    if (projectRoot) void checkTextUpdates()
  }, [projectRoot])

  // O contador do F5 e a lista mudam quando o XML é salvo fora (Notepad++): relê ao voltar
  // para a janela e, com um projeto aberto, a cada poucos segundos.
  useEffect(() => {
    const refresh = () => {
      const current = useShell.getState().shell
      if (!current?.project) return
      void api.shellState().then((state) => {
        const before = useShell.getState().shell
        if (state.pending !== before?.pending) setShell(state)
        else useShell.setState({ shell: state })
      })
    }
    window.addEventListener('focus', refresh)
    const timer = window.setInterval(refresh, 4000)
    return () => {
      window.removeEventListener('focus', refresh)
      window.clearInterval(timer)
    }
  }, [])

  if (error) {
    return <div className="flex h-full items-center justify-center p-8 text-danger">{error}</div>
  }
  if (!shell) {
    return <div className="h-full bg-window" />
  }

  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <SideRail />
        {view === 'workspace' && (
          <>
            <aside className="shrink-0 bg-panel" style={{ width: leftWidth }} data-testid="left-panel">
              {page === 'texts' ? <TextsPage /> : page === 'elements' ? <ElementTree /> : <FilesPanel />}
            </aside>
            <ResizeHandle side="left" />
          </>
        )}
        <main className="flex min-w-0 flex-1 flex-col bg-window" data-testid="center">
          {view === 'workspace' && !notesHold && <Banners />}
          {view === 'workspace' && <ExternalChangeBand />}
          {view === 'workspace' && <StandaloneBar />}
          <div className="relative min-h-0 flex-1">
          {view === 'home' ? (
            <HomeScreen />
          ) : (
            <CanvasView
              // Mudou o preview nas Configurações: remonta para reler as preferências do canvas.
              key={canvasEpoch}
              path={shell.open_path}
              language={shell.language}
              // Antes do store do canvas, o clique no canvas seleciona pelo modo só leitura.
              onSelect={storeReady ? undefined : (element) => selectElements(element ? [element.index] : [])}
              onHover={setCanvasHover}
              toolbarExtra={<CanvasHoverToggle />}
            />
          )}
          {view === 'workspace' && <SourcePanel />}
          </div>
        </main>
        {view === 'workspace' && shell.open_path && (
          <>
            <ResizeHandle side="right" />
            <aside className="shrink-0 overflow-y-auto bg-panel" style={{ width: rightWidth }} data-testid="right-panel">
              <PropertiesPanel />
            </aside>
          </>
        )}
      </div>
      <StatusBar />
      <DocSync />
      <MenuHost />
      <CommandPalette />
      <SettingsHost />
      <DialogHost />
      {view === 'workspace' && <CanvasHoverTip />}
      <DropOverlay />
      <ProgressOverlay />
      <TooltipHost />
      <Toaster theme={isLightTheme(theme) ? 'light' : 'dark'} position="bottom-right" offset={40} toastOptions={{ className: "gf-toast" }} />
    </div>
  )
}
