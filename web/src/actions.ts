// Fluxos da casca (os mesmos da clássica, com os mesmos textos e a mesma ordem de perguntas).
import { api, errorText, type ShellState } from './api'
import { t } from './i18n'
import { setShell, showStatus, useShell, type SidePage } from './store'
import { ask, confirm, message, prompt } from './ui/dialogs'
import { openNewProjectDialog } from './home/NewProjectDialog'
import { confirmDiscard, saveBeforeProjectAction } from './shell/saving'

/** Roda `work` com a barra de progresso (o Python manda os passos pelo evento "progress"). */
export async function withProgress<T>(label: string, work: () => Promise<T>): Promise<T> {
  useShell.setState({ progress: { label, done: 0, total: 0 } })
  try {
    return await work()
  } finally {
    useShell.setState({ progress: null })
  }
}

export async function refreshShell(): Promise<ShellState> {
  const shell = await api.shellState()
  setShell(shell)
  return shell
}

function enterWorkspace(shell: ShellState): void {
  setShell(shell, { view: shell.project || shell.open_path || shell.loose_dir ? 'workspace' : 'home' })
}

export async function goHome(): Promise<void> {
  if (!(await confirmDiscard())) return
  setShell(await api.goHome(), { view: 'home' })
}

export function showPage(page: SidePage): void {
  const { shell } = useShell.getState()
  if (!shell?.project && !shell?.open_path && !shell?.loose_dir) return
  useShell.setState({ page, view: 'workspace' })
}

export async function openProject(root: string): Promise<void> {
  const current = useShell.getState().shell
  const switching = current?.project?.root.toLowerCase() !== root.toLowerCase() || !current?.open_path
  if (switching && !(await confirmDiscard())) return
  try {
    const shell = await api.openProject(root)
    setShell(shell, { view: 'workspace', page: 'xml' })
  } catch (error) {
    await message('error', t('Não foi possível abrir o projeto'), errorText(error))
  }
}

export async function continueProject(): Promise<void> {
  const shell = useShell.getState().shell
  if (shell?.project) await openProject(shell.project.root)
}

export async function browseProject(): Promise<void> {
  if (!(await confirmDiscard())) return
  const result = await api.browseProject()
  if (result == null) return
  if ('error' in result) {
    await message('warning', t('Não é um projeto'), t('A pasta escolhida não é um projeto do editor.'))
    return
  }
  setShell(result, { view: 'workspace', page: 'xml' })
}

export async function newProject(looseDir?: string | null, focus?: string | null): Promise<void> {
  if (!(await confirmDiscard())) return
  const created = await openNewProjectDialog(looseDir ?? null, focus ?? null)
  if (!created) return
  enterWorkspace(created.state)
  useShell.setState({ page: 'xml' })
  showStatus(t('Projeto criado com {count} arquivos.', { count: created.count }), 8)
}

export async function openLooseXml(): Promise<void> {
  if (!(await confirmDiscard())) return
  const picked = await api.pickXml()
  if (!picked) return
  if (picked.offer_project) {
    const name = picked.path.split(/[\\/]/).pop() ?? picked.path
    const { choice, checked } = await ask({
      title: t('Criar um projeto?'),
      text: t('Editar {name} dentro de um projeto?', { name }),
      detail: t(
        'Num projeto suas alterações ficam guardadas com histórico, e Enviar para o jogo copia tudo para a pasta certa. Arquivos soltos o jogo só vê se você copiá-los manualmente.',
      ),
      choices: [
        { id: 'open', label: t('Só abrir') },
        { id: 'create', label: t('Criar projeto'), kind: 'primary' },
      ],
      check: { label: t('Não perguntar de novo'), checked: false },
    })
    if (checked) await api.setOfferProject(false)
    if (choice === 'create') {
      const folder = picked.path.replace(/[\\/][^\\/]*$/, '')
      await newProject(folder, picked.path)
      return
    }
    if (choice === null) return
  }
  enterWorkspace(await api.openLoose(picked.path))
  useShell.setState({ page: 'xml' })
}

export async function openXml(path: string): Promise<void> {
  const open = useShell.getState().shell?.open_path
  if (open?.toLowerCase() !== path.toLowerCase() && !(await confirmDiscard())) return
  try {
    setShell(await api.openXml(path), { view: 'workspace' })
  } catch (error) {
    await message('error', t('Não foi possível abrir'), errorText(error))
  }
}

// ---- tela inicial: duplicar, renomear, excluir ----------------------------------------------
export async function duplicateProject(root: string, title: string): Promise<void> {
  const name = await prompt(t('Duplicar projeto'), t('Nome da cópia:'), t('{name} (cópia)', { name: title }))
  if (!name?.trim()) return
  try {
    const result = await withProgress(t('Duplicando o projeto…'), () => api.duplicateProject(root, name))
    if (result.error === 'taken') {
      await message('warning', t('Duplicar projeto'), t('Já existe um projeto chamado {name}.', { name: result.name }))
      return
    }
    showStatus(t('Cópia criada: {name}.', { name: result.name }), 8)
  } catch (error) {
    await message('error', t('Duplicar projeto'), errorText(error))
  }
  await refreshShell()
}

export async function renameProject(root: string, title: string): Promise<void> {
  const name = await prompt(t('Renomear projeto'), t('Novo nome:'), title)
  if (!name?.trim() || name.trim() === title) return
  const result = await api.renameProject(root, name)
  if (result.error === 'taken') {
    await message('warning', t('Renomear projeto'), t('Já existe um projeto chamado {name}.', { name: result.name }))
    return
  }
  if (result.error === 'busy') {
    await message(
      'error',
      t('Renomear projeto'),
      t('Não foi possível renomear. Feche o jogo, o Explorer e programas com arquivos do projeto abertos.\n\n{error}', {
        error: result.detail ?? '',
      }),
    )
    return
  }
  if (result.state) setShell(result.state)
  showStatus(t('Projeto renomeado para {name}.', { name: result.name }), 8)
}

/** Excluir (Lixeira). Devolve true se algo saiu. */
export async function deleteProjects(roots: string[]): Promise<boolean> {
  if (!roots.length) return false
  const info = await api.deleteInfo(roots)
  if (!info.projects.length) return false
  const names = info.projects.map((project) => project.name).join(', ')
  const { choice, checked } = await ask({
    tone: 'warning',
    title: t('Excluir projeto'),
    text:
      info.projects.length === 1
        ? t('Mandar {name} para a Lixeira?', { name: names })
        : t('Mandar {count} projetos para a Lixeira?\n\n{names}', { count: info.projects.length, names }),
    detail: t('Dá para recuperar pela Lixeira do Windows.'),
    check: info.owned.length ? { label: t('Apagar também a cópia no jogo ({folders})', { folders: info.owned.join(', ') }), checked: true } : undefined,
    choices: [
      { id: 'cancel', label: t('Cancelar') },
      { id: 'delete', label: t('Excluir'), kind: 'danger' },
    ],
  })
  if (choice !== 'delete') return false
  const result = await api.deleteProjects(
    info.projects.map((project) => project.root),
    info.owned.length > 0 && checked,
  )
  setShell(result.state)
  if (result.failed.length) {
    await message(
      'warning',
      t('Excluir projeto'),
      t(
        'Não foi possível excluir: {names}. Algum programa está usando arquivos do projeto: outra janela do STZ GF UI, o jogo, o Explorer ou um editor de texto. Feche e tente de novo.',
        { names: result.failed.join(', ') },
      ),
    )
  }
  return true
}

// ---- Enviar para o jogo (F5) e exportar ----------------------------------------------------
let publishing = false

/** F5. `quiet`: envio automático depois de salvar (não pergunta se salva antes). */
export async function publishToGame(quiet = false): Promise<void> {
  const shell = useShell.getState().shell
  if (!shell?.project?.game_dir || publishing || useShell.getState().progress) return
  publishing = true
  try {
    if (!quiet && !(await saveBeforeProjectAction())) return
    const info = await api.publishInfo()
    if (!info.confirmed) {
      const yes = await confirm(
        t('Enviar para o jogo'),
        t(
          'Isto vai:\n\n• atualizar {custom}\n• copiar os arquivos do projeto para a pasta UI do jogo\n• selecionar "{name}" no Launcher.ini, para o launcher não reaplicar outra UI ao clicar Jogar\n\nOutras UIs em UICustom não são alteradas. Continuar?',
          { custom: info.custom_dir, name: info.custom_name },
        ),
      )
      if (!yes) return
      await api.confirmPublish()
    }
    let result
    try {
      result = await withProgress(t('Conferindo o que mudou e enviando para o jogo…'), () => api.publish())
    } catch (error) {
      await message(
        'error',
        t('Falha ao publicar'),
        t('Não foi possível copiar os arquivos. Feche o jogo se ele estiver aberto e tente de novo.\n\n{error}', {
          error: errorText(error),
        }),
      )
      return
    }
    await refreshShell()
    let text = result.copied
      ? t('Publicado: {count} arquivo(s) enviados para a pasta UI. Abra o jogo pelo launcher ou direto.', { count: result.copied })
      : t('Nada mudou: a pasta UI do jogo já está igual ao projeto.')
    if (result.texts_changed)
      text += ' ' + t('Textos: {count} arquivo(s) de data/Translate atualizados.', { count: result.texts_changed })
    if (result.texts_blocked)
      text += ' ' + t('Os textos não foram enviados: função desativada temporariamente por um problema conhecido.')
    if (result.game_backups)
      text +=
        ' ' +
        t(
          '{count} arquivo(s) da pasta do jogo estavam diferentes do que o editor enviou (editados fora?) e foram substituídos pelo envio; a versão de antes ficou guardada.',
          { count: result.game_backups },
        )
    showStatus(text, 12)
    if (result.text_warnings.length) {
      await message(
        'warning',
        t('Textos não aplicados'),
        t('Estes textos editados não existem mais no jogo (a atualização pode ter mudado os arquivos):\n\n{items}', {
          items: result.text_warnings.join('\n'),
        }),
      )
    }
    if (result.select_in_launcher) {
      await message(
        'info',
        t('Selecione a UI no launcher'),
        t(
          'Os arquivos foram publicados, mas o launcher está aberto com outra UI selecionada.\n\nAntes de clicar em Jogar, escolha "{name}" na lista de UIs do launcher (ou feche e abra o launcher). Senão ele reaplica a UI anterior por cima do seu teste.',
          { name: result.custom_name },
        ),
      )
    }
  } finally {
    publishing = false
  }
}

export async function exportZip(): Promise<void> {
  if (!useShell.getState().shell?.project) return
  if (!(await saveBeforeProjectAction())) return
  const target = await api.pickExportTarget()
  if (!target) return
  let result
  try {
    result = await withProgress(t('Compactando a UI…'), () => api.exportZip(target))
  } catch (error) {
    await message('error', t('Falha ao exportar'), errorText(error))
    return
  }
  if ('empty' in result) {
    await message(
      'info',
      t('Exportar UI'),
      t('Todos os arquivos do projeto são iguais aos da UI oficial: não há nada para exportar ainda.'),
    )
    return
  }
  let text = t('Exportado para {path}. No launcher: Adicionar UI Customizada.', { path: result.path })
  if (result.skipped)
    text += ' ' + t('{count} arquivo(s); {skipped} igual(is) ao oficial ficaram de fora.', { count: result.count, skipped: result.skipped })
  showStatus(text, 12)
}

// ---- configurações ---------------------------------------------------------------------------
export async function setUiMode(mode: 'classic' | 'web'): Promise<void> {
  await api.setUiMode(mode)
  await refreshShell()
  showStatus(t('A interface escolhida vale na próxima vez que o editor abrir.'), 8)
}
