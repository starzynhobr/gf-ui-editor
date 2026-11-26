// Puxar arquivos para o projeto (PullDialog da clássica): origem (UI ou UICustom), lista com a
// origem de cada arquivo, nada marcado de início e "Trazer para o projeto (N)". Também mostra as
// cópias que o F5 guardou de arquivos editados fora (lista fixa, sem escolha de origem).
import { Select } from '../ui/Select'
import { useEffect, useState } from 'react'
import { t, useT } from '../i18n'
import { Modal, openDialog } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { toolsApi, type PullCandidate } from './toolsApi'

export function originText(item: PullCandidate): string {
  const texts: Record<string, string> = {
    edited: t('Editado fora do editor'),
    unknown: t('Diferente do projeto'),
    sent: t('Enviado pelo editor (outro projeto ou antes de mudar este)'),
    official: t('Oficial do jogo (trazer desfaz a mudança do projeto)'),
  }
  let text = item.origin === 'ui' ? t('Da UI {name}', { name: item.origin_ui }) : (texts[item.origin] ?? '')
  if (item.new) text += ' · ' + t('o projeto não tem')
  return text
}

interface Props {
  root: string
  name: string
  sources?: { label: string; path: string }[]
  fixed?: PullCandidate[]
  intro?: string
  onPull: (items: PullCandidate[]) => Promise<number | null>
  onClose: (pulled: number) => void
}

function Pull({ root, name, sources, fixed, intro, onPull, onClose }: Props) {
  useT()
  const [source, setSource] = useState(sources?.[0]?.path ?? '')
  const [candidates, setCandidates] = useState<PullCandidate[] | null>(fixed ?? null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [pulled, setPulled] = useState(0)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (fixed || !source) return
    let alive = true
    setLoading(true)
    setCandidates(null)
    setChecked(new Set())
    toolsApi
      .pullCompare(root, source)
      .then((list) => alive && setCandidates(list))
      .catch(() => alive && setCandidates([]))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [root, source, fixed])

  const list = candidates ?? []
  const chosen = list.filter((item) => checked.has(item.relative))
  const mark = (rule: (item: PullCandidate) => boolean) => setChecked(new Set(list.filter(rule).map((item) => item.relative)))
  const pull = async () => {
    const done = await onPull(chosen)
    if (done == null) return
    setPulled((count) => count + done)
    setCandidates(list.filter((item) => !checked.has(item.relative)))
    setChecked(new Set())
  }
  const hasEdited = list.some((item) => item.origin === 'edited' || item.origin === 'unknown')

  return (
    <Modal
      title={t('Puxar arquivos para {name}', { name })}
      width={760}
      onClose={() => onClose(pulled)}
      footer={
        <>
          {hasEdited && (
            <button className="btn" onClick={() => mark((item) => item.origin === 'edited' || item.origin === 'unknown')}>
              {t('Marcar os editados fora')}
            </button>
          )}
          <button className="btn" onClick={() => mark(() => false)}>
            {t('Desmarcar todos')}
          </button>
          <div className="flex-1" />
          <button className="btn btn-primary" disabled={!chosen.length} onClick={() => void pull()} data-testid="pull-confirm">
            <Icon name="file-import" size={15} />
            {t('Trazer para o projeto ({count})', { count: chosen.length })}
          </button>
          <button className="btn" onClick={() => onClose(pulled)}>
            {t('Fechar')}
          </button>
        </>
      }
    >
      <div className="space-y-3" data-testid="pull-dialog">
        <p className="text-[12.5px] leading-snug text-muted">
          {intro ||
            t('Arquivos desta pasta que diferem do projeto. Nada vem marcado: escolha o que trazer. O que for substituído no projeto fica guardado no histórico.')}
        </p>
        {sources && sources.length > 0 && (
          <label className="flex items-center gap-2">
            <span className="text-muted">{t('Comparar com:')}</span>
            <Select
              size="sm"
              className="flex-1"
              name="pull-source"
              value={source}
              onChange={setSource}
              options={sources.map((item) => ({ value: item.path, label: item.label }))}
            />
          </label>
        )}
        {loading ? (
          <div className="px-1 py-4 text-muted">{t('Comparando com a pasta…')}</div>
        ) : list.length === 0 ? (
          <div className="rounded-md border border-dashed border-border-strong px-3 py-4 text-muted">
            {t('Nenhuma diferença: o projeto já tem estes arquivos iguais.')}
          </div>
        ) : (
          <div className="max-h-[340px] overflow-y-auto rounded-md border border-border bg-input">
            <div className="section-label sticky top-0 grid grid-cols-[22px_minmax(0,1fr)_minmax(0,1fr)] gap-2 bg-input px-3 py-1.5">
              <span />
              <span>{t('Arquivo')}</span>
              <span>{t('Na pasta')}</span>
            </div>
            {list.map((item) => (
              <label
                key={item.relative}
                data-testid="pull-row"
                title={item.source}
                className={`grid grid-cols-[22px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2 px-3 py-1 ${checked.has(item.relative) ? 'bg-selected' : 'hover:bg-hover'}`}
              >
                <input
                  type="checkbox"
                  checked={checked.has(item.relative)}
                  onChange={() =>
                    setChecked((current) => {
                      const next = new Set(current)
                      if (next.has(item.relative)) next.delete(item.relative)
                      else next.add(item.relative)
                      return next
                    })
                  }
                />
                <span className="truncate font-mono text-[12px]">{item.relative}</span>
                <span className="truncate text-[12px] text-muted">{originText(item)}</span>
              </label>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}

export function openPullDialog(props: Omit<Props, 'onClose'>): Promise<number> {
  return new Promise((resolve) => {
    openDialog((close) => (
      <Pull
        {...props}
        onClose={(pulled) => {
          close()
          resolve(pulled)
        }}
      />
    ))
  })
}
