// Editor flutuante de um registro (TextEditDialog da clássica): uma caixa por coluna,
// a dica do "|", Salvar, Cancelar e "Voltar ao texto original" quando há original diferente.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { t, useT } from '../i18n'
import { message, openDialog } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { oneLine, textsApi, type OpenText } from './textsApi'

export type EditorResult = 'saved' | 'restored' | null

function Editor({ record, at, onDone }: { record: OpenText; at: { x: number; y: number } | null; onDone: (result: EditorResult) => void }) {
  useT()
  const [values, setValues] = useState(record.fields)
  const [busy, setBusy] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)

  useLayoutEffect(() => {
    const rect = box.current?.getBoundingClientRect()
    if (!rect) return
    const start = at ?? { x: (window.innerWidth - rect.width) / 2 - 12, y: (window.innerHeight - rect.height) / 2 - 12 }
    setPosition({
      left: Math.max(8, Math.min(start.x + 12, window.innerWidth - rect.width - 8)),
      top: Math.max(8, Math.min(start.y + 12, window.innerHeight - rect.height - 8)),
    })
  }, [at])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onDone(null)
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onDone])

  const save = async () => {
    setBusy(true)
    let result
    try {
      result = await textsApi.save(record.name, record.id, values)
    } finally {
      setBusy(false)
    }
    {
      if (result.error === 'pipe') {
        await message('warning', t('Texto inválido'), t('Tire o "|" do texto: o jogo o usa para separar colunas.'))
        return
      }
      if (result.error === 'encoding') {
        await message(
          'warning',
          t('Caractere não suportado'),
          t('Este arquivo está em {encoding} e não aceita algum caractere digitado.', { encoding: result.encoding ?? record.encoding }),
        )
        return
      }
      onDone('saved')
    }
  }

  const restore = async () => {
    setBusy(true)
    try {
      await textsApi.restore(record.name, record.id)
      onDone('restored')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/30" onMouseDown={(event) => event.target === event.currentTarget && onDone(null)}>
      <div
        ref={box}
        role="dialog"
        aria-label={t('{file} · ID {id}', { file: record.name, id: record.id })}
        data-testid="text-editor"
        className="fixed flex w-[520px] max-w-[calc(100vw-16px)] flex-col rounded-xl border border-border-strong bg-panel shadow-2xl shadow-black/50"
        style={position ?? { left: -9999, top: -9999 }}
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          <div className="flex-1 font-semibold text-bright">{t('{file} · ID {id}', { file: record.name, id: record.id })}</div>
          <button className="icon-button" onClick={() => onDone(null)} aria-label={t('Fechar')}>
            <Icon name="x" />
          </button>
        </div>
        <div className="max-h-[60vh] space-y-2 overflow-y-auto px-4 py-3">
          {values.map((value, index) => (
            <label key={index} className="block space-y-1">
              {values.length > 1 && <span className="text-[12px] text-muted">{t('Coluna {number}', { number: index + 1 })}</span>}
              <textarea
                autoFocus={index === 0}
                name={`text-column-${index}`}
                className="field block h-auto w-full resize-y py-1.5 leading-snug"
                rows={Math.min(10, Math.max(1, value.split('\n').length))}
                value={value}
                onChange={(event) => setValues((current) => current.map((item, at) => (at === index ? event.target.value : item)))}
              />
            </label>
          ))}
          <p className="text-[12px] leading-snug text-muted">{t('O jogo usa "|" para separar as colunas, então ele não pode aparecer no texto.')}</p>
        </div>
        <div className="flex items-center gap-2 border-t border-border px-4 py-2.5">
          {record.can_restore && record.original && (
            <button className="btn" disabled={busy} title={oneLine(record.original.join(' | '))} onClick={() => void restore()}>
              {t('Voltar ao texto original')}
            </button>
          )}
          <div className="flex-1" />
          <button className="btn" disabled={busy} onClick={() => onDone(null)}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" disabled={busy} onClick={() => void save()} data-testid="text-save">
            {t('Salvar')}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Abre o editor perto do clique (como a clássica, que abre ao lado do cursor). */
export function openTextEditor(record: OpenText, at: { x: number; y: number } | null): Promise<EditorResult> {
  return new Promise((resolve) => {
    openDialog((close) => (
      <Editor
        record={record}
        at={at}
        onDone={(result) => {
          close()
          resolve(result)
        }}
      />
    ))
  })
}
