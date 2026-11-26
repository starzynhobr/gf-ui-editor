// Faixa "O arquivo mudou fora do editor": Recarregar / Manter as minhas / Comparar.
//
// A detecção é do store (`useDoc(state => state.externalChange)`, observador do XML aberto):
// a faixa aparece quando o disco tem uma revisão válida nova e há edições não salvas.
// `showExternalChange` continua disponível para outros avisos (ex.: arquivo apagado).
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { create } from 'zustand'
import { errorText } from '../api'
import { t, useT } from '../i18n'
import { useShell } from '../store'
import { message } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { reloadFromDisk, showExternalDiff } from './externalActions'
import { keepExternal, useDoc } from './store'
import { fileName } from './standalone'

export interface ExternalChange {
  path: string
  /** O arquivo sumiu do disco (apagado ou renomeado). */
  missing?: boolean
  reload: () => unknown
  keep: () => unknown
  compare?: () => unknown
}

export const useExternalChange = create<{ change: ExternalChange | null }>(() => ({ change: null }))

export function showExternalChange(change: ExternalChange): void {
  useExternalChange.setState({ change })
}

export function clearExternalChange(): void {
  useExternalChange.setState({ change: null })
}

export default function ExternalChangeBand() {
  useT()
  const manual = useExternalChange((state) => state.change)
  const detected = useDoc((state) => state.externalChange)
  const change: ExternalChange | null = detected
    ? {
        path: detected.path,
        reload: () => reloadFromDisk(detected),
        keep: () => keepExternal(detected),
        compare: () => showExternalDiff(detected),
      }
    : manual
  const openPath = useShell((state) => state.shell?.open_path ?? null)
  const reduced = useReducedMotion()
  const [busy, setBusy] = useState(false)
  const visible = change && (detected || change.path === openPath) ? change : null

  useEffect(() => {
    if (manual && openPath && manual.path !== openPath) clearExternalChange()
  }, [manual, openPath])

  const run = async (action: (() => unknown) | undefined, close: boolean) => {
    if (!action) return
    setBusy(true)
    try {
      await action()
      if (close) clearExternalChange()
    } catch (error) {
      await message('error', t('O arquivo mudou fora do editor'), errorText(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AnimatePresence initial={false}>
      {visible && (
        <motion.div
          key={detected ? `${visible.path}:${detected.token}` : visible.path}
          className="gf-external-band"
          data-testid="external-change-band"
          role="alert"
          initial={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
          transition={{ duration: reduced ? 0.01 : 0.2, ease: 'easeOut' }}
        >
          <div className="gf-external-band-inner">
            <Icon name="alert" size={16} className="shrink-0 text-warning" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-bright">
                {visible.missing ? t('O arquivo foi apagado ou renomeado fora do editor') : t('O arquivo mudou fora do editor')}
              </div>
              <div className="truncate text-[12px] text-muted" title={visible.path}>
                {visible.missing
                  ? t('{name} não está mais no disco. O que está aberto continua aqui até você fechar.', { name: fileName(visible.path) })
                  : t('Outro programa salvou {name}. As suas alterações ainda não salvas continuam aqui.', { name: fileName(visible.path) })}
              </div>
            </div>
            {!visible.missing && (
              <button className="btn btn-primary h-7" disabled={busy} data-testid="external-reload" onClick={() => void run(visible.reload, true)}>
                {t('Recarregar')}
              </button>
            )}
            <button className="btn h-7" disabled={busy} data-testid="external-keep" onClick={() => void run(visible.keep, true)}>
              {t('Manter as minhas')}
            </button>
            {!visible.missing && visible.compare && (
              <button className="btn h-7" disabled={busy} data-testid="external-compare" onClick={() => void run(visible.compare, false)}>
                {t('Comparar')}
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
