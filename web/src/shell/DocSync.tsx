// Liga a casca ao documento aberto: abre o XML do shell no store, avisa o Python quando há
// alterações não salvas (fechar a janela pergunta), mostra a seleção no rodapé e faz o
// isolamento acompanhar o elemento principal (como a clássica).
import { useEffect, useRef } from 'react'
import { api } from '../api'
import { on } from '../bridge'
import { t } from '../i18n'
import { showStatus, useShell } from '../store'
import { message } from '../ui/dialogs'
import { docState, editingAvailable, openDocument, setIsolated, useDocState } from './doc'
import { closeRequested } from './saving'
import { useSource } from '../source/SourcePanel'
import { openDroppedXmls } from '../actions'

export default function DocSync() {
  const openPath = useShell((state) => state.shell?.open_path ?? null)
  const dirty = useDocState((state) => state.dirty)
  const draftDirty = useSource((state) => state.draft !== null && state.draft.text !== state.draft.source.text)
  const primary = useDocState((state) => state.selection[0] ?? null)
  const count = useDocState((state) => state.selection.length)
  const error = useDocState((state) => state.error)
  const shown = useRef<string | null>(null)

  useEffect(() => {
    if (docState().path !== openPath) {
      openDocument(openPath).catch((reason) => void message('error', t('Não foi possível abrir'), String(reason)))
    }
  }, [openPath])

  useEffect(() => {
    void api.setUnsaved(dirty || draftDirty)
  }, [dirty, draftDirty])

  useEffect(() => on('close_requested', () => void closeRequested()), [])
  useEffect(() => on('drop_xml', (paths) => void openDroppedXmls(paths as string[])), [])

  // Gancho para o harness/web_smoke.py: saber se a edição já existe (store do canvas) e ler o estado.
  useEffect(() => {
    ;(window as unknown as { __gfDoc: object }).__gfDoc = { editing: editingAvailable, state: docState }
  }, [])

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
