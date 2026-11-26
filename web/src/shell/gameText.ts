// Duplo clique num elemento (canvas ou árvore) abre o texto do T_TextIndex que o jogo escreve
// nele, sem precisar buscar — como edit_game_text da clássica. O canvas emite
// `gf:element-dblclick`; a árvore chama `editGameText` direto.
import { t } from '../i18n'
import { toolsApi } from '../project/toolsApi'
import { showStatus, useShell } from '../store'
import { editTextRecord } from '../texts/editRecord'

export interface ElementDblClick {
  index: number
  windowId: string
  x?: number
  y?: number
}

export async function editGameText({ windowId, x, y }: ElementDblClick): Promise<void> {
  const shell = useShell.getState().shell
  const path = shell?.open_path
  if (!path) return
  const textId = await toolsApi.gameTextId(path, windowId)
  if (textId === null || textId === undefined) {
    showStatus(t('O WindowID {id} não tem texto do jogo mapeado.', { id: windowId }), 5)
    return
  }
  if (!shell?.project?.game_dir) {
    showStatus(t('Abra um projeto com a pasta do jogo para editar os textos.'), 5)
    return
  }
  const at = x !== undefined && y !== undefined ? { x, y } : null
  const opened = await editTextRecord('T_TextIndex.ini', String(textId), at)
  if (opened === false) showStatus(t('O texto {id} não existe no T_TextIndex.ini do jogo.', { id: textId }), 5)
}

export function installGameTextEditing(): () => void {
  const listener = (event: Event) => void editGameText((event as CustomEvent<ElementDblClick>).detail)
  window.addEventListener('gf:element-dblclick', listener)
  return () => window.removeEventListener('gf:element-dblclick', listener)
}
