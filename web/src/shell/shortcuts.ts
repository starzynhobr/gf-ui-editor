// Atalhos da janela (os mesmos da clássica): F5, Ctrl+S, Ctrl+Z, Ctrl+Y/Ctrl+Shift+Z,
// Ctrl+Shift+N, Ctrl+Shift+O, Ctrl+1..4, F1 (Como usar). Da interface nova: Ctrl+K (paleta) e Ctrl+U (código XML).
import { browseProject, newProject, publishToGame, showPage } from '../actions'
import { docState, redo, undo } from './doc'
import { saveDocument } from './saving'
import { useShell, type SidePage } from '../store'
import { openPalette } from '../palette/CommandPalette'
import { toggleSource } from '../source/SourcePanel'
import { openHowTo } from '../home/HowToDialog'

const PAGES: SidePage[] = ['xml', 'textures', 'elements', 'texts']

function modalOpen(): boolean {
  return document.querySelector('[role="dialog"]') !== null
}

export function installShortcuts(): () => void {
  const onKey = (event: KeyboardEvent) => {
    // F1 é da janela (QKeySequence.HelpContents na clássica): nunca vai para a ajuda do navegador.
    if (event.key === 'F1' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault()
      if (!modalOpen() && !event.repeat) openHowTo()
      return
    }
    if (modalOpen() || event.repeat) return
    const key = event.key.toLowerCase()
    const ctrl = event.ctrlKey || event.metaKey
    // Em campos de texto, Ctrl+Z/Y desfazem a digitação (o padrão do campo).
    const typing = (event.target as HTMLElement | null)?.closest?.('input, textarea, select') != null
    if (ctrl && !event.shiftKey && !event.altKey && key === 'k') {
      event.preventDefault()
      openPalette()
      return
    }
    if (ctrl && !event.shiftKey && !event.altKey && key === 'u') {
      event.preventDefault()
      if (useShell.getState().view === 'workspace') toggleSource()
      return
    }
    if (ctrl && !event.shiftKey && !event.altKey && key === 's') {
      event.preventDefault()
      void saveDocument()
      return
    }
    if (ctrl && !event.altKey && !typing && (key === 'z' || key === 'y')) {
      event.preventDefault()
      const redoing = key === 'y' || event.shiftKey
      const state = docState()
      if (redoing ? state.canRedo : state.canUndo) void (redoing ? redo() : undo())
      return
    }
    if (key === 'f5' && !ctrl && !event.shiftKey && !event.altKey) {
      event.preventDefault()
      void publishToGame()
    } else if (ctrl && event.shiftKey && key === 'n') {
      event.preventDefault()
      void newProject()
    } else if (ctrl && event.shiftKey && key === 'o') {
      event.preventDefault()
      void browseProject()
    } else if (ctrl && !event.shiftKey && !event.altKey && /^[1-4]$/.test(event.key)) {
      event.preventDefault()
      showPage(PAGES[Number(event.key) - 1])
    }
  }
  window.addEventListener('keydown', onKey)
  return () => window.removeEventListener('keydown', onKey)
}
