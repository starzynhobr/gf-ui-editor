// XML avulso (aberto de fora do projeto): estado, caminhos curtos e fechar pela lista.
import { call } from '../bridge'
import type { ShellState } from '../api'
import { errorText } from '../api'
import { t } from '../i18n'
import { confirmDiscard } from '../shell/saving'
import { setShell, useShell } from '../store'
import { message } from '../ui/dialogs'

export function isStandalone(shell: ShellState | null | undefined, path = shell?.open_path): boolean {
  return !!path && !!shell?.standalone_paths?.includes(path)
}

/** O XML aberto é avulso. */
export function useStandaloneOpen(): string | null {
  return useShell((state) => (isStandalone(state.shell) ? state.shell!.open_path! : null))
}

const split = (path: string) => path.split(/[\\/]/).filter(Boolean)

export function fileName(path: string): string {
  return split(path).at(-1) ?? path
}

/** Pasta de origem, curta: "…\Desktop\mods". */
export function folderOf(path: string, keep = 2): string {
  const parts = split(path).slice(0, -1)
  const separator = path.includes('\\') ? '\\' : '/'
  if (parts.length <= keep + 1) return parts.join(separator) + (parts.length === 1 ? separator : '')
  return `…${separator}${parts.slice(-keep).join(separator)}`
}

/** "C:\…\WorldMap2.xml" (raiz + nome), para a barra de status. */
export function shortPath(path: string): string {
  const parts = split(path)
  const separator = path.includes('\\') ? '\\' : '/'
  if (parts.length <= 2) return path
  const root = /^[A-Za-z]:$/.test(parts[0]) ? parts[0] : path.startsWith(separator) ? '' : parts[0]
  return `${root}${separator}…${separator}${parts.at(-1)}`
}

/** × da lista de avulsos: confirma alterações não salvas se for o aberto e tira da lista. */
export async function closeStandaloneFile(path: string): Promise<void> {
  const shell = useShell.getState().shell
  if (shell?.open_path === path && !(await confirmDiscard())) return
  try {
    const state = await call<ShellState>('standalone_close', path)
    setShell(state, state.open_path ? {} : { view: 'home' })
  } catch (error) {
    await message('error', t('Arquivo avulso'), errorText(error))
  }
}
