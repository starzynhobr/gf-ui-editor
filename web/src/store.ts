// Estado da casca (projeto e XML abertos, tela, mensagens). O canvas tem o próprio estado.
import { create } from 'zustand'
import type { ShellState } from './api'

export type SidePage = 'xml' | 'textures' | 'elements' | 'texts'

export interface StatusMessage {
  text: string
  id: number
}

export interface Progress {
  label: string
  done: number
  total: number
}

interface Shell {
  shell: ShellState | null
  view: 'home' | 'workspace'
  page: SidePage
  status: StatusMessage | null
  progress: Progress | null
  /** Sobe a cada mudança que pede reler a lista de arquivos e a tela inicial. */
  revision: number
}

export const useShell = create<Shell>(() => ({
  shell: null,
  view: 'home',
  page: 'xml',
  status: null,
  progress: null,
  revision: 0,
}))

let statusTimer: number | undefined
let statusId = 0

/** Mensagem no rodapé por alguns segundos (como statusBar().showMessage da clássica). */
export function showStatus(text: string, seconds = 10): void {
  statusId += 1
  useShell.setState({ status: { text, id: statusId } })
  window.clearTimeout(statusTimer)
  statusTimer = window.setTimeout(() => useShell.setState({ status: null }), seconds * 1000)
}

export function setShell(shell: ShellState, extra: Partial<Shell> = {}): void {
  useShell.setState((state) => ({ shell, revision: state.revision + 1, ...extra }))
}
