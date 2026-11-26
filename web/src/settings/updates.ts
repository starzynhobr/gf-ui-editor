// Atualizador e manifesto remoto na interface nova, com a mesma ordem e os mesmos textos da
// clássica (EditorWindow.check_for_updates, _offer_update, _install_update, apply_remote_manifest).
import { api, errorText } from '../api'
import { withProgress } from '../actions'
import { t } from '../i18n'
import { showStatus, useShell } from '../store'
import { saveBeforeProjectAction } from '../shell/saving'
import { ask, confirm, message } from '../ui/dialogs'
import { openUpdateDialog } from './UpdateDialog'
import { settingsApi, type UpdateCheck, type UpdateOffer } from './settingsApi'

let checking = false

/** Verificar atualizações… (manual = avisa também quando não há nada ou deu erro). */
export async function checkForUpdates(manual: boolean): Promise<void> {
  if (checking) return
  checking = true
  if (manual) showStatus(t('Verificando atualizações…'), 6)
  let result: UpdateCheck
  try {
    result = await settingsApi.updateCheck(manual)
  } catch (error) {
    result = { status: 'error', error: errorText(error), current: '', include_betas: false }
  } finally {
    checking = false
  }
  await handleCheck(result, manual)
}

/** Ao abrir: só com "Verificar ao abrir" ligado e uma vez por dia (o Python decide). */
export async function automaticUpdateCheck(): Promise<void> {
  let result: UpdateCheck
  try {
    result = await settingsApi.updateAutoCheck()
  } catch {
    return // sem rede ao abrir: silêncio, como na clássica
  }
  await handleCheck(result, false)
}

async function handleCheck(result: UpdateCheck, manual: boolean): Promise<void> {
  if (result.status === 'error') {
    if (manual)
      await message('warning', t('Atualizações'), t('Não foi possível verificar atualizações.\n\n{error}', { error: result.error }))
    return
  }
  if (result.status === 'latest') {
    if (manual) {
      useShell.setState({ status: null })
      await message(
        'info',
        t('Atualizações'),
        result.include_betas
          ? t('Você já está na versão mais recente ({version}), contando as betas.', { version: result.current })
          : t('Você já está na versão mais recente ({version}).', { version: result.current }),
      )
    }
    return
  }
  if (result.status === 'offer' && result.offer) await offerUpdate(result.offer)
}

export async function offerUpdate(offer: UpdateOffer): Promise<void> {
  const choice = await openUpdateDialog(offer)
  if (choice === 'skip') {
    await settingsApi.updateSkip(offer.version)
    window.dispatchEvent(new Event('gf:settings-refresh'))
  }
  else if (choice === 'update') await installUpdate(offer)
}

async function installUpdate(offer: UpdateOffer): Promise<void> {
  if (offer.can_install && !(await saveBeforeProjectAction())) return
  try {
    const run = () => settingsApi.updateInstall(offer.version)
    const result = offer.can_install
      ? await withProgress(t('Baixando a versão {version}…', { version: offer.version }), run, 'bytes')
      : await run()
    if (result.installing) showStatus(t('Baixando a versão {version}…', { version: offer.version }), 4)
  } catch (error) {
    await message('error', t('Falha na atualização'), t('A atualização foi cancelada.\n\n{error}', { error: errorText(error) }))
  }
}

// ---- manifesto remoto ------------------------------------------------------------------------

/** Versão mínima e avisos do manifesto lido ao abrir (no máximo 3, cada um uma vez). */
export async function showManifestNotices(): Promise<void> {
  let notices
  try {
    notices = await settingsApi.manifestNotices()
  } catch {
    return
  }
  if (!notices) return
  if (notices.needs_update) {
    const yes = await confirm(
      t('Atualização necessária'),
      t('Esta versão ({version}) tem um problema conhecido e precisa ser atualizada (mínima: {minimum}). Procurar a atualização agora?', {
        version: notices.version,
        minimum: notices.min_version ?? '',
      }),
    )
    if (yes) await checkForUpdates(true)
  }
  for (const notice of notices.messages) {
    const choices = [
      ...(notice.url ? [{ id: 'link', label: t('Abrir link') }] : []),
      { id: 'ok', label: t('OK'), kind: 'primary' as const },
    ]
    const { choice } = await ask({
      tone: notice.level === 'warning' ? 'warning' : 'info',
      title: t('Aviso do {name}', { name: 'STZ GF UI' }),
      text: notice.text,
      choices,
    })
    if (choice === 'link' && notice.url) void api.openUrl(notice.url)
    await settingsApi.manifestMarkSeen(notice.id)
  }
}

/** Ao abrir, como a clássica: atualização primeiro e, depois, o manifesto. */
export async function startupChecks(): Promise<void> {
  await automaticUpdateCheck()
  await showManifestNotices()
}
