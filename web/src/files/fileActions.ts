// Menu de contexto da lista de arquivos: renomear, apagar e restaurar versão (como a clássica).
import { api, errorText, type FileHistory } from '../api'
import { openXml, refreshShell } from '../actions'
import { t } from '../i18n'
import { showStatus, useShell } from '../store'
import { docState, revert } from '../shell/doc'
import { confirmDiscard } from '../shell/saving'
import { confirm, message, prompt } from '../ui/dialogs'
import { openDiffDialog } from '../ui/DiffDialog'
import type { MenuItem } from '../ui/Menu'

const baseName = (path: string) => path.split(/[\\/]/).pop() ?? path
const same = (a: string | null | undefined, b: string) => a != null && a.toLowerCase() === b.toLowerCase()
const isOpen = (path: string) => same(useShell.getState().shell?.open_path, path)

/** "hoje 14:03:22", "ontem 09:10:00" ou "21/11 18:00:00" (o _backup_label da clássica). */
export function backupLabel(name: string, stamp: string | null, now = new Date()): string {
  if (!stamp) return name
  const date = new Date(stamp)
  const time = date.toTimeString().slice(0, 8)
  const day = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
  const days = Math.round((day(now) - day(date)) / 86400000)
  if (days === 0) return `${t('hoje')} ${time}`
  if (days === 1) return `${t('ontem')} ${time}`
  return `${String(date.getDate()).padStart(2, '0')}/${String(date.getMonth() + 1).padStart(2, '0')} ${time}`
}

export async function renameFile(path: string): Promise<void> {
  const current = baseName(path)
  const typed = (await prompt(t('Renomear'), t('Novo nome:'), current))?.trim()
  if (!typed || typed === current) return
  const check = await api.renameCheck(path, typed)
  if (check.invalid) {
    await message('warning', t('Renomear'), t('O nome não pode ter \\ / : * ? " < > |.'))
    return
  }
  if (check.replacing) {
    const yes = await confirm(
      t('Substituir arquivo?'),
      t('Já existe {name} no projeto. Substituir? A versão atual vai para o histórico.', { name: check.name }),
    )
    if (!yes) return
  }
  const reopen = isOpen(path) || (check.replacing && isOpen(check.target))
  if (reopen && !(await confirmDiscard())) return
  let renamed
  try {
    renamed = await api.renameFile(path, typed)
  } catch (error) {
    await message('error', t('Renomear'), errorText(error))
    return
  }
  if (check.texture_users) {
    const yes = await confirm(
      t('Atualizar XMLs?'),
      t('{count} XML(s) do projeto usam {old}. Trocar para {new} neles também?', { count: check.texture_users, old: current, new: renamed.name }),
    )
    if (yes) await api.retargetTexture(current, renamed.name)
  }
  await refreshShell()
  if (reopen && renamed.name.toLowerCase().endsWith('.xml')) await openXml(renamed.path)
  showStatus(t('{old} agora se chama {new}.', { old: current, new: renamed.name }), 8)
}

export async function deleteFile(path: string): Promise<void> {
  const name = baseName(path)
  const warning = await api.deleteFileInfo(path)
  const details = warning.official
    ? t('Este arquivo existe na UI oficial: sem ele, o jogo pode usar o da UI padrão ou acusar erro. Uma cópia fica no histórico do projeto.')
    : warning.texture_users
      ? t('{count} XML(s) do projeto ainda usam esta textura e ficariam sem imagem. Uma cópia fica no histórico do projeto.', {
          count: warning.texture_users,
        })
      : t('Uma cópia fica no histórico do projeto.')
  if (!(await confirm(t('Apagar {name}?', { name }), details))) return
  if (isOpen(path) && !(await confirmDiscard())) return
  try {
    await api.deleteFile(path)
  } catch (error) {
    await message('error', t('Apagar'), errorText(error))
    return
  }
  await refreshShell()
  showStatus(t('{name} apagado. A cópia está no histórico do projeto.', { name }), 8)
}

export async function restoreFile(path: string, source: string): Promise<void> {
  const name = baseName(path)
  const open = isOpen(path)
  if (open && docState().dirty) {
    const yes = await confirm(t('Descartar alterações?'), t('{name} tem alterações não salvas que serão perdidas ao restaurar. Continuar?', { name }))
    if (!yes) return
  }
  let diff: string
  try {
    diff = await api.restorePreview(path, source, t('{name} (atual)', { name }), t('versão restaurada'))
  } catch (error) {
    await message('error', t('Falha ao restaurar'), errorText(error))
    return
  }
  if (!diff) {
    showStatus(t('Essa versão é igual ao arquivo atual.'), 5)
    return
  }
  const accepted = await openDiffDialog({
    title: t('Restaurar {name}', { name }),
    explanation: t('Estas linhas vão mudar. O estado atual fica guardado no histórico, então dá para voltar.'),
    diff,
    confirm: t('Restaurar'),
  })
  if (!accepted) return
  try {
    await api.restoreFile(path, source)
  } catch (error) {
    await message('error', t('Falha ao restaurar'), errorText(error))
    return
  }
  if (open) await revert().catch(() => undefined) // relê do disco
  await refreshShell()
  showStatus(t('{name} restaurado.', { name }), 6)
}

/** Itens de projeto do menu (renomear, apagar, histórico); vazio para um arquivo solto. */
export function projectFileItems(path: string, history: FileHistory): MenuItem[] {
  const items: MenuItem[] = []
  if (history.in_project) {
    items.push(
      { label: t('Renomear…'), icon: 'pencil', onClick: () => void renameFile(path) },
      { label: t('Apagar…'), icon: 'trash', danger: true, onClick: () => void deleteFile(path) },
      { separator: true },
    )
  }
  items.push(
    {
      label: t('Restaurar versão anterior'),
      disabled: !history.backups.length,
      submenu: history.backups.map((backup) => ({
        label: backupLabel(backup.name, backup.stamp),
        onClick: () => void restoreFile(path, backup.path),
      })),
    },
    {
      label: t('Desfazer todas as alterações'),
      disabled: !history.original,
      hint: '',
      onClick: () => history.original && void restoreFile(path, history.original),
    },
    { separator: true },
    { label: t('Abrir pasta do histórico'), disabled: !history.folder, onClick: () => history.folder && void api.openFolder(history.folder) },
  )
  return items
}
