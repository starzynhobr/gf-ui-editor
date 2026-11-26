// Troca de interface (Configurações → Interface, "Voltar para a clássica" das Novidades, da
// engrenagem e do Ctrl+K): grava ui_mode e oferece reiniciar agora. O reinício passa pelo
// closeRequested, que pergunta Salvar/Descartar se houver alteração.
import { errorText } from '../api'
import { refreshShell } from '../actions'
import { t } from '../i18n'
import { closeRequested } from '../shell/saving'
import { confirm, message } from '../ui/dialogs'
import { settingsApi } from './settingsApi'

export type UiMode = 'classic' | 'web'

/** "Reiniciar agora para usar a interface …?" (Depois / Reiniciar agora). */
export async function offerRestart(mode: UiMode, beforeRestart?: () => Promise<void> | void): Promise<boolean> {
  const name = mode === 'web' ? t('Nova (beta)') : t('Clássica')
  const yes = await confirm(t('Interface'), t('Reiniciar agora para usar a interface {name}?', { name }), {
    no: t('Depois'),
    yes: t('Reiniciar agora'),
  })
  if (!yes) return false
  await beforeRestart?.()
  await closeRequested(true)
  return true
}

/** Voltar para a clássica: o mesmo fluxo da opção Interface das Configurações. */
export async function backToClassic(beforeRestart?: () => Promise<void> | void): Promise<void> {
  try {
    await settingsApi.set('ui_mode', 'classic')
  } catch (error) {
    await message('warning', t('Configurações'), errorText(error))
    return
  }
  window.dispatchEvent(new CustomEvent('gf:settings-changed', { detail: { name: 'ui_mode', value: 'classic' } }))
  window.dispatchEvent(new Event('gf:settings-refresh'))
  await refreshShell()
  await offerRestart('classic', beforeRestart)
}
