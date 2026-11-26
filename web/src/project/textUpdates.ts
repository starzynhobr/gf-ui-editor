// Aviso de atualização dos textos do jogo (serviço game_text_updates, ponte text_updates):
// o launcher baixou .ini novos (IDs novos, textos oficiais alterados) e/ou desfez edições
// deste projeto, que voltam com o próximo F5.
import { create } from 'zustand'
import { call } from '../bridge'

export interface TextUpdateReport {
  update: null | {
    changed_files: string[]
    unavailable: string[]
    new_ids: number
    changed_texts: number
    files: { name: string; new_ids: string[]; removed_ids: string[]; changed: { id: string; before: string[]; after: string[] }[] }[]
  }
  reverted: { file: string; id: string }[]
  official_changed: { file: string; id: string; original: string[]; official: string[] }[]
  missing: { file: string; id: string }[]
}

export const useTextUpdates = create<{ report: TextUpdateReport | null; dismissed: boolean }>(() => ({
  report: null,
  dismissed: false,
}))

/** Projeto aberto mudou (ou voltou de um F5): confere de novo. */
export async function checkTextUpdates(): Promise<void> {
  try {
    const report = await call<TextUpdateReport | null>('text_updates_check')
    useTextUpdates.setState({ report, dismissed: false })
  } catch {
    useTextUpdates.setState({ report: null })
  }
}

/** "Entendi": a atualização vista vira a referência; edições desfeitas continuam avisando até o F5. */
export async function acknowledgeTextUpdates(): Promise<void> {
  await call('text_updates_acknowledge')
  useTextUpdates.setState({ dismissed: true })
}
