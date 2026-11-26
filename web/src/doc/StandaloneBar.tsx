import { useState } from 'react'
import { errorText } from '../api'
import { t } from '../i18n'
import { useDocState } from '../shell/doc'
import { saveDocument } from '../shell/saving'
import { useShell } from '../store'
import { message } from '../ui/dialogs'
import { compareStandaloneFile, importStandaloneFile } from './standaloneActions'

export default function StandaloneBar() {
  const shell = useShell((state) => state.shell)
  const docPath = useDocState((state) => state.doc ? state.path : null)
  const [busy, setBusy] = useState(false)
  const path = shell?.open_path
  if (!path || !shell.standalone_paths?.includes(path)) return null

  const invoke = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await action()
    } catch (error) {
      await message('error', t('Arquivo avulso'), errorText(error))
    } finally {
      setBusy(false)
    }
  }
  const disabled = busy || docPath !== path
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-2" data-testid="standalone-bar">
      <span className="min-w-0 flex-1 truncate" title={path}>{t('Arquivo avulso: {path}', { path })}</span>
      <button className="btn" disabled={disabled} onClick={() => void invoke(saveDocument)}>{t('Salvar no lugar')}</button>
      <button className="btn" disabled={disabled} onClick={() => void invoke(() => importStandaloneFile(path))}>{t('Importar para o projeto')}</button>
      <button className="btn" disabled={disabled} onClick={() => void invoke(() => compareStandaloneFile(path))}>{t('Comparar')}</button>
    </div>
  )
}
