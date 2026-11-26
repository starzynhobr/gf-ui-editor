// Liga a casca ao documento aberto: abre o XML do shell no store, avisa o Python quando há
// alterações não salvas (fechar a janela pergunta), mostra a seleção no rodapé e faz o
// isolamento acompanhar o elemento principal (como a clássica).
import { useEffect, useRef } from 'react'
import { api } from '../api'
import { on } from '../bridge'
import { t } from '../i18n'
import { showStatus, useShell } from '../store'
import { message } from '../ui/dialogs'
import { docState, openDocument, setIsolated, useDocState } from './doc'
import { closeRequested } from './saving'

export default function DocSync() {
  const openPath = useShell((state) => state.shell?.open_path ?? null)
  const dirty = useDocState((state) => state.dirty)
  const primary = useDocState((state) => state.selection[0] ?? null)
  const count = useDocState((state) => state.selection.length)
  const error = useDocState((state) => state.error)
  const shown = useRef<string | null>(null)

  useEffect(() => {
    openDocument(openPath).catch((reason) => void message('error', t('Não foi possível abrir'), String(reason)))
  }, [openPath])

  useEffect(() => {
    void api.setUnsaved(dirty)
  }, [dirty])

  useEffect(() => on('close_requested', () => void closeRequested()), [])

  useEffect(() => {
    if (primary == null) return
    const state = docState()
    const element = state.doc?.elements[primary]
    if (!element) return
    if (state.isolated != null && state.isolated !== primary) setIsolated(primary)
    const suffix = count > 1 ? t(' · {count} selecionados', { count }) : ''
    showStatus(t('WindowID {id} · índice {index}', { id: element.id, index: primary }) + suffix, 6)
  }, [primary, count])

  useEffect(() => {
    if (error && error !== shown.current) {
      shown.current = error
      showStatus(error, 10)
    }
  }, [error])

  return null
}
