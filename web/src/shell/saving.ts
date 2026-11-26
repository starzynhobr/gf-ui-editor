// Salvar o XML aberto (com o diff antes, como _confirm_diff_preview da clássica) e
// "Descartar alterações?" ao sair dele.
import { publishToGame, refreshShell } from '../actions'
import { api, errorText } from '../api'
import { t } from '../i18n'
import { showStatus, useShell } from '../store'
import { ask, message } from '../ui/dialogs'
import { openDiffDialog } from '../ui/DiffDialog'
import { docState, previewSave, revert, save, StoreUnavailable } from './doc'

const fileName = () => docState().path?.split(/[\\/]/).pop() ?? ''

/** Ctrl+S: mostra o diff, grava e avisa. Devolve true se não sobrou nada por salvar. */
export async function saveDocument(): Promise<boolean> {
  const state = docState()
  if (!state.path) return true
  if (!state.dirty) {
    showStatus(t('Nenhuma alteração para salvar.'), 4)
    return true
  }
  let diff: string
  try {
    diff = await previewSave()
  } catch (error) {
    await message('error', t('Falha ao salvar'), errorText(error))
    return false
  }
  const accepted = await openDiffDialog({
    title: t('Confirmar alterações no XML'),
    explanation: t('Confira as linhas que serão alteradas. O backup exato será criado antes da gravação.'),
    diff,
    confirm: t('Salvar'),
  })
  if (!accepted) return false
  try {
    await save()
  } catch (error) {
    if (error instanceof StoreUnavailable) return false
    await message('error', t('Falha ao salvar'), errorText(error))
    return false
  }
  const shell = await refreshShell()
  const inProject = Boolean(shell.project && state.path.toLowerCase().startsWith(shell.project.ui_dir.toLowerCase()))
  if (inProject && shell.publish_on_save && shell.project?.game_dir) {
    await publishToGame(true)
    return !docState().dirty
  }
  showStatus(
    inProject ? t('Salvo no projeto. O jogo só recebe as mudanças com Enviar para o jogo (F5).') : t('As alterações foram salvas.'),
    10,
  )
  return !docState().dirty
}

/**
 * Antes de trocar de XML ou de projeto, ir para a tela inicial ou fechar a janela:
 * Salvar / Descartar / Cancelar. true = pode seguir.
 */
export async function confirmDiscard(): Promise<boolean> {
  if (!docState().dirty) return true
  const { choice } = await ask({
    tone: 'warning',
    title: t('Descartar alterações?'),
    text: t('{name} tem alterações não salvas. Salvar antes de continuar?', { name: fileName() }),
    choices: [
      { id: 'cancel', label: t('Cancelar') },
      { id: 'discard', label: t('Descartar'), kind: 'danger' },
      { id: 'save', label: t('Salvar'), kind: 'primary' },
    ],
  })
  if (choice === 'save') return saveDocument()
  if (choice === 'discard') {
    try {
      await revert()
    } catch {
      // o XML vai ser fechado de qualquer jeito
    }
    return true
  }
  return false
}

/** F5 e Exportar: com alterações, pergunta se salva antes (como _save_before_project_action). */
export async function saveBeforeProjectAction(): Promise<boolean> {
  if (!docState().dirty) return true
  const { choice } = await ask({
    title: t('Salvar antes?'),
    text: t('{name} tem alterações não salvas. Salvar antes de continuar?', { name: fileName() }),
    choices: [
      { id: 'cancel', label: t('Cancelar') },
      { id: 'discard', label: t('Descartar') },
      { id: 'save', label: t('Salvar'), kind: 'primary' },
    ],
  })
  if (choice === 'save') return saveDocument()
  return choice === 'discard'
}

/** Pedido de fechar a janela (o Python cancelou porque havia alterações). */
export async function closeRequested(): Promise<void> {
  if (await confirmDiscard()) {
    await api.setUnsaved(false)
    await api.closeWindow()
  }
}

export function bumpRevision(): void {
  useShell.setState((state) => ({ revision: state.revision + 1 }))
}
