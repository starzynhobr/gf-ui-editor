// Tela de Textos (Ctrl+4), como a aba Textos da clássica: busca em data/Translate com
// espera de 200 ms, "Só editados", "Importar textos…", resumo e a lista Texto · Arquivo · ID
// com os marcadores ● (editado), ⚠ (mudou no jogo depois da edição) e ◐ (mudado no jogo).
import { useVirtualizer } from '@tanstack/react-virtual'
import { useCallback, useEffect, useRef, useState } from 'react'
import { refreshShell } from '../actions'
import { on } from '../bridge'
import { t, useT } from '../i18n'
import { useShell } from '../store'
import { ask, message } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { openTextEditor } from './TextEditor'
import { oneLine, textsApi, type TextResults, type TextRow } from './textsApi'

const ROW_HEIGHT = 26

export function summaryText(results: TextResults | null): string {
  if (!results) return ''
  const { summary, values, updates } = results
  let text =
    summary === 'no_game'
      ? t('Defina a pasta do jogo no projeto para ver os textos.')
      : summary === 'type_to_search'
        ? t('Digite para buscar em data/Translate.')
        : summary === 'nothing_edited'
          ? t('Digite para buscar em data/Translate. Nenhum texto editado neste projeto.')
          : summary === 'changed'
            ? t('{total} texto(s) mudado(s) neste projeto. Digite para buscar em todos.', { total: values.total ?? 0 })
            : summary === 'limited'
              ? t('{total} resultados; mostrando os primeiros {shown}.', { total: values.total ?? 0, shown: values.shown ?? 0 })
              : t('{total} resultado(s).', { total: values.total ?? 0 })
  if (updates) text += ' ' + t('⚠ {count} mudou(aram) no jogo depois da edição: confira antes de enviar.', { count: updates })
  return text
}

const MARK: Record<string, [string, string]> = {
  edited: ['●', 'text-accent-text'],
  updated: ['⚠', 'text-warning'],
  changed: ['◐', 'text-warning'],
}

export function rowTooltip(row: TextRow): string {
  if (row.state === 'updated') {
    return t('Uma atualização do jogo mudou este texto depois da sua edição.\nOriginal quando você editou: {original}\nNo jogo agora: {game}\nSua edição: {mine}', {
      original: oneLine(row.original.join(' | ')),
      game: oneLine(row.game_fields.join(' | ')),
      mine: oneLine(row.fields.join(' | ')),
    })
  }
  if (row.state === 'changed') {
    return (
      t('O jogo está com um texto diferente do original (backup do primeiro envio), mas não há edição guardada neste projeto. Abra para voltar ao original.') +
      '\n\n' +
      row.fields.join('\n')
    )
  }
  return row.fields.join('\n')
}

/** Edições de texto mudaram: o rodapé, a árvore (rótulos) e quem ouvir o evento atualizam. */
async function textsChanged(): Promise<void> {
  await refreshShell() // contador do F5 e revisão (a árvore relê os rótulos do jogo)
  window.dispatchEvent(new CustomEvent('gf:text-edits-changed'))
}

export default function TextsPage() {
  useT()
  const project = useShell((state) => state.shell?.project ?? null)
  const [query, setQuery] = useState('')
  const [editedOnly, setEditedOnly] = useState(false)
  const [results, setResults] = useState<TextResults | null>(null)
  const [canImport, setCanImport] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const current = useRef({ query, editedOnly })
  current.current = { query, editedOnly }
  const parent = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    const { query: text, editedOnly: only } = current.current
    const found = await textsApi.search(text, only)
    if (current.current.query === text && current.current.editedOnly === only) setResults(found)
  }, [])

  useEffect(() => {
    void textsApi.state().then((state) => setCanImport(state.can_import))
    void refresh()
  }, [project?.root, project?.game_dir, refresh])

  // Busca com espera de 200 ms (o QTimer da clássica).
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 200)
    return () => window.clearTimeout(timer)
  }, [query, refresh])

  useEffect(() => {
    void refresh()
  }, [editedOnly, refresh])

  // Índice pronto: a busca fica completa e rápida (só refaz se há texto buscado).
  useEffect(() => on('texts_index_ready', () => current.current.query.trim() && void refresh()), [refresh])
  useEffect(() => on('text_edits_changed', () => void refresh()), [refresh])

  const rows = results?.rows ?? []
  const virtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => parent.current, estimateSize: () => ROW_HEIGHT, overscan: 12 })

  const open = async (row: TextRow, at: { x: number; y: number } | null) => {
    setSelected(`${row.name}/${row.id}`)
    const record = await textsApi.open(row.name, row.id)
    if (!record) return
    const result = await openTextEditor(record, at)
    if (result) {
      await refresh()
      await textsChanged()
    }
  }

  const importTexts = async () => {
    const folder = await textsApi.pickImport()
    if (!folder) return
    const plan = await textsApi.planImport(folder)
    const notes: string[] = []
    if (plan.missing_ids) notes.push(t('{count} ID(s) não existem mais no jogo e foram ignorados.', { count: plan.missing_ids }))
    if (plan.unsupported) notes.push(t('{count} texto(s) têm caracteres que o jogo não aceita e foram ignorados.', { count: plan.unsupported }))
    if (plan.unknown_files.length) notes.push(t('Arquivos que o jogo não tem: {files}.', { files: plan.unknown_files.join(', ') }))
    if (!plan.count) {
      await message(
        'info',
        t('Importar textos'),
        [
          t(
            'Nenhum texto diferente do jogo foi encontrado em {folder}.\n\nSe a pasta do jogo já está com esses arquivos copiados, deixe o launcher baixar os originais de novo e importe depois.',
            { folder: plan.folder },
          ),
          ...notes,
        ].join('\n\n'),
      )
      return
    }
    if (plan.replaced) notes.unshift(t('{count} substituem edições que você já tinha.', { count: plan.replaced }))
    const text = t(
      '{count} texto(s) diferentes do jogo serão guardados como edições deste projeto:\n\n{files}\n\nIDs que não estão nos arquivos importados continuam com o texto do jogo.',
      { count: plan.count, files: plan.per_file.map(([name, count]) => `${name}: ${count}`).join('\n') },
    )
    const { choice } = await ask({
      title: t('Importar textos'),
      text: [text, ...notes].join('\n\n'),
      choices: [
        { id: 'no', label: t('Não') },
        { id: 'yes', label: t('Sim'), kind: 'primary' },
      ],
    })
    if (choice !== 'yes') return
    await textsApi.applyImport()
    setQuery('')
    current.current = { query: '', editedOnly }
    await refresh()
    await textsChanged()
  }

  const available = Boolean(project?.game_dir)
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="texts-page">
      <div className="px-3 pt-3 pb-2 text-[13px] font-semibold text-bright">{t('Textos')}</div>
      <div className="relative px-3 pb-2">
        <Icon name="search" size={14} className="pointer-events-none absolute top-2 left-5.5 text-disabled" />
        <input
          className="field h-7 w-full pl-7"
          name="texts-search"
          disabled={!available}
          placeholder={t('Buscar em todos os textos do jogo…')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <div className="flex items-center gap-2 px-3 pb-2">
        <label className="flex flex-1 items-center gap-2 text-[12.5px]">
          <input type="checkbox" name="texts-edited-only" checked={editedOnly} onChange={(event) => setEditedOnly(event.target.checked)} />
          {t('Só editados')}
        </label>
        <button
          className="btn h-7 px-2.5 text-[12.5px]"
          disabled={!canImport}
          title={t(
            'Traz alterações de arquivos T_*.ini que você já tinha editado. Compara ID por ID com o jogo:\nsó o que mudou vira edição do projeto, e IDs novos de atualizações continuam com o texto oficial.',
          )}
          onClick={() => void importTexts()}
        >
          {t('Importar textos…')}
        </button>
      </div>
      <div className="px-3 pb-2 text-[12px] leading-snug text-muted" data-testid="texts-summary">
        {summaryText(results)}
      </div>
      <div className="grid shrink-0 grid-cols-[minmax(0,1fr)_96px_52px] gap-2 border-y border-border px-3 py-1.5 section-label">
        <span>{t('Texto')}</span>
        <span>{t('Arquivo')}</span>
        <span>ID</span>
      </div>
      <div ref={parent} className="min-h-0 flex-1 overflow-y-auto">
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((item) => {
            const row = rows[item.index]
            const [mark, color] = MARK[row.state] ?? ['', 'text-text']
            const key = `${row.name}/${row.id}`
            return (
              <div
                key={key}
                data-testid="text-row"
                data-id={row.id}
                data-state={row.state}
                title={rowTooltip(row)}
                className={`absolute inset-x-0 grid grid-cols-[minmax(0,1fr)_96px_52px] items-center gap-2 px-3 ${
                  selected === key ? 'bg-selected' : 'hover:bg-hover'
                }`}
                style={{ height: ROW_HEIGHT, transform: `translateY(${item.start}px)` }}
                onClick={(event) => void open(row, { x: event.clientX, y: event.clientY })}
              >
                <span className={`truncate text-[12.5px] ${color}`}>
                  {mark && `${mark} `}
                  {oneLine(row.fields.join(' | '))}
                </span>
                <span className="truncate font-mono text-[11.5px] text-muted">{row.name}</span>
                <span className="truncate font-mono text-[11.5px] text-muted">{row.id}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
