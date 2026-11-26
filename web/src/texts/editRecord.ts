// Abrir o editor de um registro de texto e avisar quem depende das edições (rodapé, árvore,
// canvas). Usado pela tela de Textos e pelo duplo clique num elemento (edit_record da clássica).
import { refreshShell } from '../actions'
import { openTextEditor, type EditorResult } from './TextEditor'
import { textsApi } from './textsApi'

export async function textsChanged(): Promise<void> {
  await refreshShell() // contador do F5 e revisão (a árvore relê os rótulos do jogo)
  window.dispatchEvent(new CustomEvent('gf:text-edits-changed'))
}

/** false se o registro não existe no jogo (ou não há projeto); o resultado do editor senão. */
export async function editTextRecord(name: string, id: string, at: { x: number; y: number } | null): Promise<EditorResult | false> {
  const record = await textsApi.open(name, id)
  if (!record) return false
  const result = await openTextEditor(record, at)
  if (result) await textsChanged()
  return result
}
