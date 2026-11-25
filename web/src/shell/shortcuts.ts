// Atalhos da janela (os mesmos da clássica): F5, Ctrl+Shift+N, Ctrl+Shift+O, Ctrl+1..4.
import { browseProject, newProject, publishToGame, showPage } from '../actions'
import type { SidePage } from '../store'

const PAGES: SidePage[] = ['xml', 'textures', 'elements', 'texts']

function modalOpen(): boolean {
  return document.querySelector('[role="dialog"]') !== null
}

export function installShortcuts(): () => void {
  const onKey = (event: KeyboardEvent) => {
    if (modalOpen() || event.repeat) return
    const key = event.key.toLowerCase()
    const ctrl = event.ctrlKey || event.metaKey
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
