// Fluxos das ferramentas do projeto (versões, puxar, limpar, UI oficial, erro do jogo,
// exportar textos, cópias do F5), com os mesmos textos e a mesma ordem da clássica.
import { errorText } from '../api'
import { openXml, refreshShell, withProgress } from '../actions'
import { t } from '../i18n'
import { showStatus, useShell } from '../store'
import { docState, insertOfficialControls, revert, selectElements, StoreUnavailable } from '../shell/doc'
import { confirmDiscard, saveBeforeProjectAction } from '../shell/saving'
import { chooseFromList } from '../ui/ChooseDialog'
import { confirm, message, prompt } from '../ui/dialogs'
import { promptMultiline } from '../ui/MultilinePrompt'
import { openCleanupDialog } from './CleanupDialog'
import { openOfficialControlsDialog, openOfficialReferenceDialog } from './OfficialDialogs'
import { officialKey, refreshOfficialStatus, startOfficialScan, useOfficial } from './official'
import { openPullDialog } from './PullDialog'
import { toolsApi, type PullCandidate } from './toolsApi'
import { openVersionsDialog } from './VersionsDialog'

const same = (a: string | null | undefined, b: string | null | undefined) => a != null && b != null && a.toLowerCase() === b.toLowerCase()
const isCurrent = (root: string) => same(useShell.getState().shell?.project?.root, root)

/** Depois de mexer nos arquivos do projeto aberto: listas, contador e o XML aberto relidos. */
async function projectFilesChanged(root: string, reopen: boolean): Promise<void> {
  const shell = await refreshShell()
  if (reopen && isCurrent(root) && shell.open_path) await revert().catch(() => undefined)
}

// ---- versões --------------------------------------------------------------------------------
export async function saveProjectVersion(root: string): Promise<boolean> {
  if (isCurrent(root) && !(await saveBeforeProjectAction())) return false
  const label = await prompt(t('Salvar versão'), t('Nome da versão (opcional), ex.: antes de mudar o BasicChar:'))
  if (label === null) return false
  try {
    const saved = await withProgress(t('Salvando versão…'), () => toolsApi.saveVersion(root, label))
    showStatus(t('Versão salva ({size}). Projeto → Versões do projeto para voltar a ela.', { size: saved.size }), 10)
  } catch (error) {
    await message('error', t('Salvar versão'), errorText(error))
    return false
  }
  await refreshShell()
  return true
}

export async function restoreProjectVersion(root: string, name: string, version: string): Promise<boolean> {
  const current = isCurrent(root)
  if (current && !(await confirmDiscard())) return false
  if (!(await confirm(t('Restaurar versão'), t('Deixar {name} como estava nessa versão? A versão atual é salva antes, então dá para voltar.', { name })))) {
    return false
  }
  let result
  try {
    result = await withProgress(t('Restaurando versão…'), () => toolsApi.restoreVersion(root, version))
  } catch (error) {
    await message('error', t('Restaurar versão'), errorText(error))
    return false
  }
  await projectFilesChanged(root, current)
  const text = t('Versão restaurada: {written} arquivo(s) da versão, {reverted} de volta ao oficial, {removed} removido(s).', { written: result.written, reverted: result.reverted, removed: result.removed })
  if (result.unresolved.length) {
    await message(
      'warning',
      t('Restaurar versão'),
      text +
        '\n\n' +
        t('Estes arquivos eram iguais ao oficial nessa versão, mas a cópia oficial não foi encontrada; ficaram como estavam:\n{files}', {
          files: result.unresolved.join('\n'),
        }),
    )
  } else showStatus(text, 10)
  return true
}

export async function projectFromVersion(root: string, name: string, version: string): Promise<void> {
  const typed = (await prompt(t('Criar projeto a partir da versão'), t('Nome do novo projeto:'), t('{name} (versão)', { name })))?.trim()
  if (!typed) return
  try {
    const result = await withProgress(t('Criando o projeto…'), () => toolsApi.branchVersion(root, version, typed))
    if (result.error === 'taken') {
      await message('warning', t('Criar projeto a partir da versão'), t('Já existe um projeto chamado {name}.', { name: result.name }))
      return
    }
    showStatus(t('Projeto criado: {name}.', { name: result.name }), 8)
  } catch (error) {
    await message('error', t('Criar projeto a partir da versão'), errorText(error))
    return
  }
  await refreshShell()
}

export async function showVersions(root: string, name: string): Promise<void> {
  await openVersionsDialog(root, name)
  await refreshShell()
}

// ---- puxar ------------------------------------------------------------------------------------
async function pullInto(root: string, items: PullCandidate[]): Promise<number | null> {
  const open = useShell.getState().shell?.open_path
  const affected = isCurrent(root) && items.some((item) => same(open, `${useShell.getState().shell?.project?.ui_dir}\\${item.relative.replace(/\//g, '\\')}`))
  if (affected && !(await confirmDiscard())) return null
  let result
  try {
    result = await toolsApi.pullApply(root, items.map((item) => [item.relative, item.source]))
  } catch (error) {
    await message('error', t('Puxar da pasta do jogo'), errorText(error))
    return null
  }
  await projectFilesChanged(root, result.open_affected)
  showStatus(t('{count} arquivo(s) trazidos para o projeto. O que foi substituído está no histórico.', { count: result.count }), 10)
  return result.count
}

export async function showPull(root: string, name: string): Promise<void> {
  const sources = await toolsApi.pullSources(root)
  if (!sources.length) {
    await message('info', t('Puxar da pasta do jogo'), t('Este projeto não tem pasta do jogo.'))
    return
  }
  if (isCurrent(root) && !(await saveBeforeProjectAction())) return
  await openPullDialog({ root, name, sources, onPull: (items) => pullInto(root, items) })
}

/** Banner do F5: cópias dos arquivos da pasta do jogo editados fora que o envio substituiu. */
export async function showGameBackups(): Promise<void> {
  const project = useShell.getState().shell?.project
  if (!project) return
  const fixed = await toolsApi.gameBackups()
  await openPullDialog({
    root: project.root,
    name: project.name,
    fixed,
    intro: t(
      'Estes arquivos da pasta UI do jogo estavam diferentes do que o editor enviou e o envio os substituiu. A versão de antes ficou guardada no histórico do projeto; marque o que quiser trazer para o projeto.',
    ),
    onPull: (items) => pullInto(project.root, items),
  })
}

// ---- limpar -----------------------------------------------------------------------------------
export async function showCleanup(root: string): Promise<void> {
  if (isCurrent(root) && !(await saveBeforeProjectAction())) return
  let plan
  try {
    plan = await withProgress(t('Vendo o que dá para limpar…'), () => toolsApi.cleanupScan(root))
  } catch (error) {
    await message('error', t('Limpar projeto'), errorText(error))
    return
  }
  const choice = await openCleanupDialog(plan)
  if (!choice) return
  try {
    const result = await withProgress(t('Limpando o projeto…'), () =>
      toolsApi.cleanupApply(root, choice.history, choice.icons, choice.maps, choice.custom),
    )
    showStatus(t('Projeto limpo: {count} arquivo(s) apagados, {size} liberados.', { count: result.removed, size: result.freed }), 10)
  } catch (error) {
    await message('error', t('Limpar projeto'), errorText(error))
    return
  }
  await projectFilesChanged(root, false)
}

// ---- UI oficial ---------------------------------------------------------------------------------
export async function openOfficialReference(): Promise<void> {
  const status = await refreshOfficialStatus()
  if (!status.game_dir) {
    await message('info', t('UI oficial de referência'), t('Defina a pasta do jogo primeiro (Arquivo → Novo projeto → Pasta do jogo).'))
    return
  }
  await openOfficialReferenceDialog()
  startOfficialScan(useShell.getState().shell?.project?.root ?? null)
}

/** "Ver e adicionar" / resolver erro: controles do oficial que o XML aberto não tem. */
export async function openOfficialCompare(focusId: string | null = null): Promise<void> {
  const path = useShell.getState().shell?.open_path
  if (!path) return
  const name = path.split(/[\\/]/).pop() ?? path
  const controls = await toolsApi.officialControls(path)
  if (controls.unavailable) {
    if (await confirm(t('UI oficial indisponível'), t('Não há cópia oficial de {file} para comparar. Guardar a UI oficial agora?', { file: name }))) {
      await openOfficialReference()
    }
    return
  }
  if (controls.complete) {
    await message('info', t('Controles da UI oficial'), t('{file} já tem todos os controles da UI oficial.', { file: name }))
    return
  }
  const ids = await openOfficialControlsDialog(controls, focusId)
  if (!ids?.length) return
  try {
    await insertOfficialControls(ids, t('Adicionar {count}', { count: ids.length }))
    showStatus(t('{count} controle(s) do oficial adicionado(s). Ajuste a posição se precisar; salve para gravar.', { count: ids.length }), 10)
  } catch (error) {
    if (error instanceof StoreUnavailable) showStatus(t('Edição indisponível: o canvas editável ainda não chegou nesta versão.'), 8)
    else await message('error', t('Não foi possível adicionar'), errorText(error))
  }
}

export function dismissOfficialBanner(): void {
  const shell = useShell.getState().shell
  const key = officialKey(shell?.project?.ui_dir, shell?.open_path)
  if (key) useOfficial.setState((state) => ({ dismissed: [...state.dismissed, key] }))
}

// ---- resolver erro do jogo ------------------------------------------------------------------------
async function waitForDocument(path: string, timeout = 8000): Promise<boolean> {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const state = docState()
    if (same(state.path, path) && state.doc) return true
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  return false
}

export async function resolveGameError(): Promise<void> {
  const title = t('Resolver erro do jogo')
  const text = await promptMultiline(title, t('Cole a mensagem de erro do jogo (por exemplo, a que tem "Child control can not found"):'))
  if (!text?.trim()) return
  const located = await toolsApi.locateGameError(text)
  if (located.error) {
    await message('info', title, t('Não encontrei um arquivo .cpp e um ID=… nessa mensagem.'))
    return
  }
  const { cpp, id, candidates } = located
  if (!candidates.length) {
    await message(
      'info',
      title,
      t('Não sei qual XML o {cpp} usa com o ID {id}, ou não há cópia da UI oficial para conferir. Escolha "UI Padrão" no launcher, clique em Jogar uma vez e tente de novo.', { cpp, id }),
    )
    return
  }
  let name: string | null = candidates[0]
  if (candidates.length > 1) name = await chooseFromList(title, t('Qual destes arquivos?'), candidates, candidates[0])
  if (!name) return
  if (!located.folder) {
    await message('info', title, t('O controle {id} fica em {file}. Abra a UI e tente de novo.', { id, file: name }))
    return
  }
  if (!located.exists[name]) {
    await message('info', title, t('Esta UI não tem o arquivo {file}.', { file: name }))
    return
  }
  const path = located.paths[name]
  if (!same(useShell.getState().shell?.open_path, path)) {
    await openXml(path) // pergunta "Descartar alterações?" se precisar
    if (!same(useShell.getState().shell?.open_path, path)) return
  }
  useShell.setState({ view: 'workspace', page: 'elements' })
  await waitForDocument(path)
  const element = docState().doc?.elements.find((item) => item.id === id)
  if (element) {
    selectElements([element.index])
    await message(
      'info',
      title,
      t('{file} já tem o controle {id}. O erro deve vir de outra coisa no arquivo, como texto solto entre as tags; o editor avisa ao abrir quando encontra algo assim.', {
        file: name,
        id,
      }),
    )
    return
  }
  await openOfficialCompare(id)
}

// ---- exportar textos -----------------------------------------------------------------------------
export async function exportTexts(): Promise<void> {
  const title = t('Exportar textos')
  const info = await toolsApi.textsExportInfo()
  if (!info.available) return
  if (info.disabled) {
    await message('info', 'STZ GF UI', t('Esta função está desativada temporariamente por causa de um problema conhecido. Ela volta numa atualização.'))
    return
  }
  if (!info.has_edits) {
    await message('info', title, t('Este projeto ainda não tem textos editados para exportar.'))
    return
  }
  const target = await toolsApi.textsPickExport()
  if (!target) return
  let result
  try {
    result = await withProgress(t('Compactando os textos…'), () => toolsApi.textsExport(target))
  } catch (error) {
    await message('error', t('Falha ao exportar'), errorText(error))
    return
  }
  if (!result.names.length) {
    await message('warning', title, t('Nenhum arquivo editado foi encontrado em data/Translate do jogo.'))
    return
  }
  let text = t(
    'Exportado para {path}.\n\nArquivos: {files}\n\nNo outro PC, extraia o .zip na pasta do jogo (a que tem a pasta data) e substitua os arquivos. Use com a mesma versão do jogo: o launcher troca estes arquivos ao atualizar ou mudar o idioma.',
    { path: result.path, files: result.names.join(', ') },
  )
  if (result.warnings.length) text += '\n\n' + t('Não foram incluídos (não existem mais no jogo):\n{items}', { items: result.warnings.join('\n') })
  await message('info', title, text)
}
