// Estado das Novidades depois de atualizar (ponte whats_new_state/closed/pill_dismissed):
// abrem sozinhas uma vez, antes dos outros avisos; ao fechar, viram a pílula "Novidades ×"
// da barra superior até a pessoa dispensar com o ×.
import { create } from 'zustand'
import { api } from '../api'
import { holdToasts } from '../store'

export type WhatsNewMode = 'auto' | 'pill' | 'manual'

interface WhatsNewUi {
  /** A pílula está na barra (versão ainda não dispensada). */
  pill: boolean
  /** As notas estão abertas por cima da pílula: ela fica invisível (o diálogo "é" ela). */
  covering: boolean
  /** Abertura automática em curso: avisos da tela inicial e banners esperam. */
  hold: boolean
}

export const useWhatsNew = create<WhatsNewUi>(() => ({ pill: false, covering: false, hold: false }))

let openNotes = 0

/** Notas abertas: os toasts esperam elas fecharem (não aparecem por cima). */
export function notesOpened(): void {
  openNotes += 1
  holdToasts(true)
}

export function notesClosed(): void {
  openNotes = Math.max(0, openNotes - 1)
  if (openNotes === 0) holdToasts(false)
}

/** Testes. */
export function resetWhatsNew(): void {
  openNotes = 0
  holdToasts(false)
  useWhatsNew.setState({ pill: false, covering: false, hold: false })
}

/** Fechou as notas abertas sozinhas ou pela pílula: a versão conta como vista e a pílula aparece. */
export function markClosed(): void {
  useWhatsNew.setState({ pill: true })
  void api.whatsNewClosed().catch(() => undefined)
}

/** × da pílula: some até a próxima versão (as Novidades continuam na engrenagem e no Ctrl+K). */
export function dismissPill(): void {
  useWhatsNew.setState({ pill: false, covering: false })
  void api.whatsNewPillDismissed().catch(() => undefined)
}
