// UI oficial de referência (OfficialUIDialog) e os controles do oficial que o XML não tem
// (OfficialControlsDialog), como na clássica.
import { useEffect, useMemo, useRef, useState } from 'react'
import { kindLabel } from '../elements/kinds'
import { t, useT } from '../i18n'
import { Modal, openDialog } from '../ui/dialogs'
import { refreshOfficialStatus } from './official'
import { toolsApi, type OfficialControls, type OfficialStatus } from './toolsApi'

const LAUNCHER_NAME = 'UI Padrão'

function statusText(status: OfficialStatus | null): string {
  if (!status) return ''
  if (status.total === 0) return t('Não encontrei o GameDataFileList.txt do launcher nesta pasta do jogo.')
  return status.ready
    ? t('Guardada: {cached} de {total} arquivos da UI oficial atual.', { cached: status.cached, total: status.total })
    : t('Ainda não guardada: {cached} de {total} arquivos da UI oficial atual.', { cached: status.cached, total: status.total })
}

function OfficialReference({ onClose }: { onClose: () => void }) {
  useT()
  const [status, setStatus] = useState<OfficialStatus | null>(null)
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    void refreshOfficialStatus().then(setStatus)
    return () => window.clearInterval(timer.current)
  }, [])

  const snapshot = async () => {
    setBusy(true)
    try {
      const next = await toolsApi.officialSnapshot()
      setStatus(next)
      setTried(true)
      void refreshOfficialStatus()
      if (next.ready) window.clearInterval(timer.current)
      // Até o launcher deixar a UI oficial na pasta, tenta de novo sozinho a cada 3 s.
      else if (!timer.current) timer.current = window.setInterval(() => void snapshot(), 3000)
    } finally {
      setBusy(false)
    }
  }

  const ready = Boolean(status?.ready)
  return (
    <Modal
      title={t('UI oficial de referência')}
      width={560}
      onClose={onClose}
      footer={
        <button className="btn" onClick={onClose}>
          {t('Fechar')}
        </button>
      }
    >
      <div className="space-y-3" data-testid="official-dialog">
        <p className="text-[12.5px] leading-snug text-muted">
          {t('O editor guarda uma cópia da UI oficial do jogo para comparar com a sua: é assim que ele sabe quais controles faltam e quais vieram de uma atualização. Basta guardar uma vez por atualização do jogo.')}
        </p>
        <div className="font-semibold text-bright" data-testid="official-status">
          {statusText(status)}
        </div>
        <button className="btn btn-primary" disabled={busy || ready || !status?.total} onClick={() => void snapshot()} data-testid="official-save">
          {ready && tried ? t('Pronto') : t('Guardar UI oficial agora')}
        </button>
        {tried && !ready && (
          <div className="card space-y-2 px-3.5 py-3">
            <div className="font-semibold text-bright">{t('A pasta UI do jogo está com outra UI')}</div>
            <p className="whitespace-pre-wrap text-[12.5px] leading-snug text-text">
              {t('1. No launcher, escolha "{name}" na lista de UIs.\n2. Clique em Jogar uma vez (pode fechar o jogo logo depois).\n3. Volte aqui: o editor tenta de novo sozinho a cada poucos segundos.\n\nDepois você pode voltar a escolher a sua UI no launcher.', { name: LAUNCHER_NAME })}
            </p>
            <div className="text-[12px] text-muted">{t('No launcher agora: {name}', { name: status?.launcher_ui ?? '' })}</div>
            <button className="btn h-7" onClick={() => void snapshot()}>
              {t('Já fiz, tentar de novo')}
            </button>
          </div>
        )}
      </div>
    </Modal>
  )
}

export function openOfficialReferenceDialog(): Promise<void> {
  return new Promise((resolve) =>
    openDialog((close) => (
      <OfficialReference
        onClose={() => {
          close()
          resolve()
        }}
      />
    )),
  )
}

function Controls({
  controls,
  focusId,
  onDone,
}: {
  controls: OfficialControls
  focusId: string | null
  onDone: (ids: string[] | null) => void
}) {
  useT()
  const newIds = useMemo(() => controls.new_ids ?? [], [controls])
  const otherIds = useMemo(() => controls.other_ids ?? [], [controls])
  const [checked, setChecked] = useState<Set<string>>(() => new Set(focusId != null ? [focusId] : newIds))
  const [search, setSearch] = useState(focusId ?? '')
  const toggle = (id: string) =>
    setChecked((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const sections: [string, string[]][] = [
    [t('NOVOS NA ATUALIZAÇÃO DO JOGO'), newIds],
    [t('OUTROS QUE O OFICIAL TEM (PODEM TER SIDO REMOVIDOS DE PROPÓSITO)'), otherIds],
  ]
  const columns = 'grid grid-cols-[20px_70px_120px_minmax(0,1fr)_110px] items-center gap-2.5'
  return (
    <Modal
      title={t('Controles da UI oficial')}
      width={640}
      onClose={() => onDone(null)}
      footer={
        <>
          <button className="btn" onClick={() => onDone(null)}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" disabled={!checked.size} onClick={() => onDone([...checked])} data-testid="controls-add">
            {t('Adicionar {count}', { count: checked.size })}
          </button>
        </>
      }
    >
      <div className="space-y-3" data-testid="official-controls">
        <div className="font-semibold text-bright">{t('Controles do oficial que {file} não tem', { file: controls.file })}</div>
        <input className="field w-full" placeholder={t('Buscar WindowID, ex.: 8301')} value={search} onChange={(event) => setSearch(event.target.value)} />
        <div className={`${columns} section-label px-2.5`}>
          <span />
          <span>{t('ID')}</span>
          <span>{t('TIPO')}</span>
          <span>{t('TEXTURA DO OFICIAL')}</span>
          <span>{t('POSIÇÃO')}</span>
        </div>
        <div className="max-h-[320px] space-y-1.5 overflow-y-auto">
          {sections.map(([heading, ids]) => {
            const shown = ids.filter((id) => !search.trim() || id.startsWith(search.trim()))
            if (!shown.length) return null
            return (
              <div key={heading} className="space-y-1.5">
                <div className="section-label pt-1">{heading}</div>
                {shown.map((id) => {
                  const info = controls.infos?.[id]
                  return (
                    <label key={id} data-testid="control-row" className={`${columns} rounded-md border px-2.5 py-1.5 ${checked.has(id) ? 'border-accent-border/60 bg-accent-soft' : 'border-border hover:bg-hover'}`}>
                      <input type="checkbox" checked={checked.has(id)} onChange={() => toggle(id)} />
                      <span className="font-mono text-[12px]">{id}</span>
                      <span className="truncate">{info ? kindLabel(info.kind, null) : '—'}</span>
                      <span className="truncate font-mono text-[12px]">{info?.texture || '—'}</span>
                      <span className="font-mono text-[12px]">{info ? `${info.position[0]}, ${info.position[1]}` : '—'}</span>
                    </label>
                  )
                })}
              </div>
            )
          })}
        </div>
        <p className="text-[12px] leading-snug text-muted">
          {t('Entram na mesma posição do arquivo oficial e o resto do arquivo não muda. Dá para desfazer (Ctrl+Z); nada é gravado até você salvar.')}
        </p>
      </div>
    </Modal>
  )
}

export function openOfficialControlsDialog(controls: OfficialControls, focusId: string | null): Promise<string[] | null> {
  return new Promise((resolve) =>
    openDialog((close) => (
      <Controls
        controls={controls}
        focusId={focusId}
        onDone={(ids) => {
          close()
          resolve(ids)
        }}
      />
    )),
  )
}
