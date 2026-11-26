// Estado da UI oficial de referência: status (guardada ou não), diferenças do projeto aberto
// (controles que a atualização do jogo trouxe) e o que o usuário dispensou nos banners.
import { create } from 'zustand'
import { on } from '../bridge'
import { toolsApi, type FileDiff, type OfficialStatus } from './toolsApi'

interface Official {
  status: OfficialStatus | null
  root: string | null
  diffs: Record<string, FileDiff>
  dismissed: string[]
  referenceDismissed: boolean
  /** Cópias que o último F5 guardou (arquivos da pasta do jogo editados fora). */
  gameBackups: number
}

export const useOfficial = create<Official>(() => ({
  status: null,
  root: null,
  diffs: {},
  dismissed: [],
  referenceDismissed: false,
  gameBackups: 0,
}))

export async function refreshOfficialStatus(): Promise<OfficialStatus> {
  const status = await toolsApi.officialStatus()
  useOfficial.setState({ status })
  return status
}

/** Projeto aberto mudou: compara com a oficial em segundo plano (chega pelo evento). */
export function startOfficialScan(root: string | null): void {
  useOfficial.setState({ root, diffs: {}, gameBackups: 0 })
  void refreshOfficialStatus()
  if (root) void toolsApi.officialScan()
}

export function installOfficialEvents(): () => void {
  return on('official_scan', (payload) => {
    const { root, diffs } = payload as { root: string; diffs: Record<string, FileDiff> }
    if (useOfficial.getState().root?.toLowerCase() === root.toLowerCase()) useOfficial.setState({ diffs })
    void refreshOfficialStatus()
  })
}

/** Chave da diferença de um XML do projeto: caminho relativo à pasta ui/, em minúsculas. */
export function officialKey(uiDir: string | null | undefined, path: string | null | undefined): string | null {
  if (!uiDir || !path) return null
  const base = uiDir.replace(/[\\/]+$/, '').toLowerCase() + '\\'
  const full = path.replace(/\//g, '\\').toLowerCase()
  return full.startsWith(base) ? full.slice(base.length).replace(/\\/g, '/') : null
}
