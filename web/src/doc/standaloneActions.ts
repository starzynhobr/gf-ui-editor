import { call } from '../bridge'
import { t } from '../i18n'
import { confirmSourceDraft } from '../source/SourcePanel'
import { setShell, showStatus, useShell } from '../store'
import { openDiffDialog } from '../ui/DiffDialog'
import { ask, message, prompt } from '../ui/dialogs'
import { importStandalone } from './store'

export async function importStandaloneFile(path: string) {
  if (!(await confirmSourceDraft())) return
  let root = useShell.getState().shell?.project?.root ?? null
  if (!root) root = await call<string | null>('standalone_pick_project')
  if (!root) return
  const options = await ask({
    title: t('Importar para o projeto'),
    text: path.split(/[\\/]/).pop() ?? path,
    check: { label: t('Trazer as texturas que faltam no projeto'), checked: true },
    choices: [
      { id: 'cancel', label: t('Cancelar') },
      { id: 'import', label: t('Importar'), kind: 'primary' },
    ],
  })
  if (options.choice !== 'import') return
  let name: string | null = null
  let replace = false
  for (;;) {
    const result = await importStandalone(path, name, replace, options.checked, root)
    if (!result.conflict) {
      setShell(result.state)
      showStatus(t('XML importado: {name}', { name: result.name }))
      return
    }
    const { choice } = await ask({
      title: t('O XML já existe no projeto'),
      text: result.name,
      detail: t('Ao substituir, a versão atual vai para o histórico do projeto.'),
      choices: [
        { id: 'cancel', label: t('Cancelar') },
        { id: 'replace', label: t('Substituir'), kind: 'danger' },
        { id: 'rename', label: t('Salvar como…'), kind: 'primary' },
      ],
    })
    if (choice === 'replace') replace = true
    else if (choice === 'rename') {
      name = await prompt(t('Salvar como…'), t('Nome do XML no projeto:'), result.name)
      if (!name?.trim()) return
    } else return
  }
}

export async function compareStandaloneFile(path: string) {
  const { choice } = await ask({
    title: t('Comparar XML avulso'),
    text: t('Qual versão você quer comparar com o XML aberto?'),
    choices: [
      { id: 'cancel', label: t('Cancelar') },
      ...(useShell.getState().shell?.project ? [{ id: 'project', label: t('Mesmo nome no projeto') }] : []),
      { id: 'official', label: t('XML oficial') },
    ],
  })
  if (choice !== 'project' && choice !== 'official') return
  const diff = await call<string | null>('standalone_compare', path, choice)
  const title = t('Comparar XML avulso')
  if (diff === null) await message('info', title, t('A versão de referência não está disponível.'))
  else if (!diff) await message('info', title, t('Os XMLs são iguais.'))
  else await openDiffDialog({ title, explanation: '', diff, confirm: t('Fechar'), readOnly: true })
}
