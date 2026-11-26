import { useState } from 'react'
import { useT } from '../i18n'
import { reloadFromDisk, showExternalDiff } from './externalActions'
import { keepExternal, useDoc } from './store'

export default function ExternalChangeBar() {
  const t = useT()
  const change = useDoc((state) => state.externalChange)
  const [busy, setBusy] = useState(false)
  if (!change) return null

  const invoke = async (action: () => Promise<void>) => {
    setBusy(true)
    try {
      await action()
    } catch {
      // The document store already reports bridge errors in the status bar.
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border bg-panel px-3 py-1.5"
      aria-label={t('O arquivo mudou fora do editor')} data-testid="external-change-bar">
      <span className="flex-1" role="status">{t('O arquivo mudou fora do editor')}</span>
      <button className="btn" disabled={busy} onClick={() => void invoke(() => reloadFromDisk(change))}>{t('Recarregar')}</button>
      <button className="btn" disabled={busy} onClick={() => void invoke(() => keepExternal(change))}>{t('Manter as minhas')}</button>
      <button className="btn" disabled={busy} onClick={() => void invoke(() => showExternalDiff(change))}>{t('Comparar')}</button>
    </section>
  )
}
