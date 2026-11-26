// Faixa "O arquivo mudou fora do editor": Recarregar / Manter as minhas / Comparar.
//
// STUB até o contrato do Codex (observador de arquivos + recarga automática) chegar: a faixa é só
// visual e lê um store próprio. Quem detecta a mudança chama showExternalChange({ ... }) com as
// três ações; enquanto isso, o evento de ponte `doc_changed_outside` { path, missing? } liga a
// faixa com ações provisórias (recarregar = doc_revert pelo store; comparar = `doc_external_diff`
// se existir). Trocar o stub = chamar showExternalChange do lugar certo e apagar installStub.
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { create } from 'zustand'
import { call, on } from '../bridge'
import { errorText } from '../api'
import { t, useT } from '../i18n'
import { useShell } from '../store'
import { openDiffDialog } from '../ui/DiffDialog'
import { message } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { checkExternalChange } from './store'
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

/** Ações provisórias (stub) para o evento doc_changed_outside. */
export function stubChange(path: string, missing = false): ExternalChange {
  return {
    path,
    missing,
    reload: () => checkExternalChange(path, () => true),
    keep: () => undefined,
    compare: async () => {
      try {
        const diff = await call<string | null>('doc_external_diff', path)
        if (!diff) await message('info', t('Comparar'), t('Os XMLs são iguais.'))
        else await openDiffDialog({ title: t('O que mudou fora do editor'), explanation: '', diff, confirm: t('Fechar'), readOnly: true })
      } catch (error) {
        await message('info', t('Comparar'), errorText(error))
      }
    },
  }
}

export function installExternalChangeStub(): () => void {
  return on('doc_changed_outside', (payload) => {
    const { path, missing } = payload as { path: string; missing?: boolean }
    showExternalChange(stubChange(path, missing))
  })
}

export default function ExternalChangeBand() {
  useT()
  const change = useExternalChange((state) => state.change)
  const openPath = useShell((state) => state.shell?.open_path ?? null)
  const reduced = useReducedMotion()
  const [busy, setBusy] = useState(false)
  const visible = change && change.path === openPath ? change : null

  useEffect(() => {
    if (change && openPath && change.path !== openPath) clearExternalChange()
  }, [change, openPath])

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
          key={visible.path}
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
