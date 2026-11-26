import { toast } from 'sonner'
import { t } from '../i18n'
import { useSource } from '../source/SourcePanel'
import { showStatus } from '../store'
import { openDiffDialog } from '../ui/DiffDialog'
import { checkExternalChange, compareExternal, reloadExternal, type ExternalChange } from './store'

const sourceDraft = (path: string) => {
  const draft = useSource.getState().draft
  return draft?.source.path.toLowerCase() === path.toLowerCase() ? draft : null
}

function showReloaded() {
  toast(t('Recarregado: alterado fora do editor'), { duration: 3500 })
}

export async function pollExternalChange(path: string) {
  const result = await checkExternalChange(path, () => {
    const draft = sourceDraft(path)
    if (draft?.busy || (draft && draft.text !== draft.source.text)) return true
    return false
  })
  if (result && 'reloaded' in result) {
    const draft = sourceDraft(path)
    if (draft && draft.text === draft.source.text) useSource.setState({ draft: null })
    showReloaded()
  } else if (result) {
    showStatus(result.error, 8)
  }
}

export async function reloadFromDisk(change: ExternalChange) {
  if (await reloadExternal(change)) {
    if (sourceDraft(change.path)) useSource.setState({ draft: null })
    showReloaded()
  } else {
    showStatus(t('O arquivo mudou novamente no disco.'), 6)
  }
}

export async function showExternalDiff(change: ExternalChange) {
  const draft = sourceDraft(change.path)
  const diff = await compareExternal(change, draft && draft.text !== draft.source.text ? draft.text : null)
  if (diff === null) {
    showStatus(t('O arquivo mudou novamente no disco.'), 6)
    return
  }
  await openDiffDialog({
    title: t('O arquivo mudou fora do editor'),
    explanation: t('Diferenças entre o XML no disco e o XML no editor.'),
    diff: diff || t('Nenhuma diferença no texto do XML.'),
    confirm: t('Fechar'),
    readOnly: true,
  })
}
