// "Ver código XML" (Ctrl+U): o XML aberto como ficaria ao salvar, com as edições ainda não
// salvas, num CodeMirror com números de linha, Ctrl+F e dobrar blocos.
// Selecionar um elemento leva à linha dele; clicar numa linha com WindowID seleciona o elemento.
import { ResizeHandle } from '../ui/ResizeHandle'
import { panelWidth, useUi } from '../shell/uiState'
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { create } from 'zustand'
import { Compartment, EditorState, RangeSetBuilder, StateEffect, StateField, Text, type Extension } from '@codemirror/state'
import {
  Decoration, EditorView, drawSelection, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers,
  type DecorationSet,
} from '@codemirror/view'
import { foldGutter, foldKeymap, HighlightStyle, syntaxHighlighting, codeFolding } from '@codemirror/language'
import { xml } from '@codemirror/lang-xml'
import { highlightSelectionMatches, openSearchPanel, search, searchKeymap } from '@codemirror/search'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { tags } from '@lezer/highlight'
import { call } from '../bridge'
import { applySource, select, useDoc, type SourceIssue } from '../doc/store'
import { t, useT } from '../i18n'
import { Icon } from '../ui/Icon'
import { ask } from '../ui/dialogs'
import './source.css'

export interface DocSource {
  path: string
  text: string
  /** Linha (1 em diante) da tag de cada elemento, na ordem dos índices; [] se não deu para mapear. */
  lines: number[]
  dirty: boolean
}

interface Draft {
  source: DocSource
  text: string
  issue?: SourceIssue
  error?: string
  busy?: boolean
}

export const useSource = create<{ open: boolean; draft: Draft | null }>(() => ({ open: false, draft: null }))

async function applyDraft() {
  const draft = useSource.getState().draft
  if (!draft || draft.busy) return !draft
  useSource.setState({ draft: { ...draft, busy: true, issue: undefined, error: undefined } })
  try {
    const issue = await applySource(draft.source.path, draft.text, draft.source.text, t('Editar código XML'))
    useSource.setState({ draft: issue ? { ...draft, issue } : null })
    return issue === null
  } catch (error) {
    useSource.setState({ draft: { ...draft, error: error instanceof Error ? error.message : String(error) } })
    return false
  }
}

export async function confirmSourceDraft(): Promise<boolean> {
  const draft = useSource.getState().draft
  if (draft?.busy) return false
  if (draft && draft.text !== draft.source.text) {
    const { choice } = await ask({
      tone: 'warning',
      title: t('Aplicar alterações no código XML?'),
      text: draft.source.path.split(/[\\/]/).pop() ?? '',
      choices: [
        { id: 'cancel', label: t('Cancelar') },
        { id: 'discard', label: t('Descartar'), kind: 'danger' },
        { id: 'apply', label: t('Aplicar'), kind: 'primary' },
      ],
    })
    if (choice === 'apply') return applyDraft()
    if (choice !== 'discard') return false
  }
  useSource.setState({ draft: null })
  return true
}

export function openSource(): void {
  if (useDoc.getState().path) useSource.setState({ open: true })
}

export function closeSource(): void {
  if (!useSource.getState().draft) useSource.setState({ open: false })
  else void confirmSourceDraft().then((ok) => { if (ok) useSource.setState({ open: false }) })
}

export function toggleSource(): void {
  if (useSource.getState().open) closeSource()
  else openSource()
}

// ---- CodeMirror ------------------------------------------------------------------------------

const markLine = StateEffect.define<number | null>()
const markError = StateEffect.define<{ from: number; to: number } | null>()
const markedError = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, transaction) {
    for (const effect of transaction.effects) {
      if (!effect.is(markError)) continue
      const range = effect.value
      return range ? Decoration.set([range.from === range.to
        ? Decoration.line({ class: 'gf-source-error-line' }).range(transaction.state.doc.lineAt(range.from).from)
        : Decoration.mark({ class: 'gf-source-error' }).range(range.from, range.to)]) : Decoration.none
    }
    return transaction.docChanged ? Decoration.none : value
  },
  provide: (field) => EditorView.decorations.from(field),
})
const markedLine = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, transaction) {
    value = value.map(transaction.changes)
    for (const effect of transaction.effects) {
      if (!effect.is(markLine)) continue
      const builder = new RangeSetBuilder<Decoration>()
      const number = effect.value
      if (number && number <= transaction.state.doc.lines) {
        const line = transaction.state.doc.line(number)
        builder.add(line.from, line.from, Decoration.line({ class: 'gf-source-marked' }))
      }
      value = builder.finish()
    }
    return value
  },
  provide: (field) => EditorView.decorations.from(field),
})

const highlight = HighlightStyle.define([
  { tag: [tags.tagName, tags.angleBracket], color: 'var(--color-accent-text)' },
  { tag: tags.attributeName, color: 'var(--color-gold)' },
  { tag: tags.attributeValue, color: 'var(--color-success)' },
  { tag: tags.comment, color: 'var(--color-muted)', fontStyle: 'italic' },
  { tag: [tags.processingInstruction, tags.documentMeta], color: 'var(--color-muted)' },
  { tag: tags.content, color: 'var(--color-text)' },
  { tag: tags.invalid, color: 'var(--color-danger)' },
])

const theme = EditorView.theme({
  '&': { height: '100%', color: 'var(--color-text)', backgroundColor: 'var(--color-window)', fontSize: '12px' },
  '.cm-scroller': { fontFamily: 'var(--font-mono)', lineHeight: '1.55' },
  '.cm-content': { caretColor: 'var(--color-bright)' },
  '.cm-gutters': { backgroundColor: 'var(--color-panel)', color: 'var(--color-muted)', borderRight: '1px solid var(--color-border)' },
  '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--color-hover) 60%, transparent)' },
  '.cm-activeLineGutter': { backgroundColor: 'var(--color-hover)', color: 'var(--color-bright)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: 'var(--color-selected) !important' },
  '.cm-searchMatch': { backgroundColor: 'color-mix(in srgb, var(--color-gold) 30%, transparent)', outline: '1px solid var(--color-gold)' },
  '.cm-searchMatch-selected': { backgroundColor: 'color-mix(in srgb, var(--color-accent) 45%, transparent)' },
  '.cm-selectionMatch': { backgroundColor: 'color-mix(in srgb, var(--color-accent) 22%, transparent)' },
  '.cm-foldPlaceholder': { backgroundColor: 'var(--color-chip)', border: '1px solid var(--color-border)', color: 'var(--color-muted)' },
  '.cm-foldGutter span': { color: 'var(--color-icon)', cursor: 'pointer' },
  '.cm-panels': { backgroundColor: 'var(--color-panel)', color: 'var(--color-text)' },
  '.cm-panels.cm-panels-top': { borderBottom: '1px solid var(--color-border)' },
  '.cm-panels.cm-panels-bottom': { borderTop: '1px solid var(--color-border)' },
})

function lineOf(lines: number[], index: number | undefined): number | null {
  return index == null ? null : (lines[index] ?? null)
}

function extensions(mode: Compartment, lineSeparator: Compartment): Extension[] {
  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightActiveLine(),
    drawSelection(),
    codeFolding(),
    foldGutter(),
    xml(),
    syntaxHighlighting(highlight),
    search({ top: true }),
    highlightSelectionMatches(),
    markedLine,
    markedError,
    mode.of(editMode(false)),
    lineSeparator.of([]),
    EditorState.phrases.of({
      Find: t('Procurar'), next: t('próximo'), previous: t('anterior'), all: t('todos'),
      'match case': t('diferenciar maiúsculas'), regexp: t('expressão regular'), 'by word': t('palavra inteira'),
      close: t('Fechar'), 'Go to line': t('Ir para a linha'), go: t('ir'),
      'Folded lines': t('Linhas recolhidas'), 'Unfolded lines': t('Linhas expandidas'),
      'Fold line': t('Recolher bloco'), 'Unfold line': t('Expandir bloco'),
    }),
    // Só leitura, mas com foco (para o Ctrl+F e as setas).
    EditorView.contentAttributes.of({ tabindex: '0' }),
    keymap.of([...searchKeymap, ...foldKeymap, ...historyKeymap, ...defaultKeymap]),
    EditorView.updateListener.of((update) => {
      const draft = useSource.getState().draft
      if (update.docChanged && draft && !update.state.readOnly) {
        useSource.setState({ draft: { ...draft, text: update.state.sliceDoc(), issue: undefined, error: undefined } })
      }
    }),
    theme,
  ]
}

function editMode(editable: boolean, busy = false): Extension {
  return [
    EditorState.readOnly.of(!editable || busy), EditorView.editable.of(editable),
    ...(editable ? [history()] : []),
  ]
}

/** Linha (1 em diante) do nó clicado dentro do texto, ou null. */
function clickedLine(view: EditorView, target: EventTarget | null): number | null {
  if (!(target instanceof Node) || !view.contentDOM.contains(target)) return null
  try {
    return view.state.doc.lineAt(view.posAtDOM(target)).number
  } catch {
    return null // nó fora do documento (ex.: marcador de bloco recolhido)
  }
}

function SourceEditor({ source, draft }: { source: DocSource; draft: Draft | null }) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const linesRef = useRef<number[]>(source.lines)
  const selected = useDoc((state) => state.selection[0])
  const pressed = useRef<[number, number] | null>(null)
  const mode = useRef(new Compartment()).current
  const lineSeparator = useRef(new Compartment()).current
  const editing = draft !== null
  const busy = draft?.busy === true
  const issue = draft?.issue

  useEffect(() => {
    const editor = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: '',
        extensions: extensions(mode, lineSeparator),
      }),
    })
    view.current = editor
    return () => {
      editor.destroy()
      view.current = null
    }
  }, [mode, lineSeparator])

  useEffect(() => {
    const editor = view.current
    if (!editor) return
    editor.dispatch({ effects: mode.reconfigure(editMode(editing, busy)) })
    if (editing && !busy) editor.focus()
  }, [mode, editing, busy])

  // Texto novo (edição, desfazer, salvar): troca o conteúdo mantendo a rolagem.
  useEffect(() => {
    const editor = view.current
    if (!editor || editing) return
    linesRef.current = source.lines
    if (editor.state.sliceDoc() === source.text) return
    const separator = source.text.includes('\r\n') && !/\r(?!\n)|(?<!\r)\n/.test(source.text) ? '\r\n'
      : source.text.includes('\r') && !source.text.includes('\n') ? '\r' : undefined
    const top = editor.scrollDOM.scrollTop
    editor.dispatch({
      effects: lineSeparator.reconfigure(separator ? EditorState.lineSeparator.of(separator) : []),
      changes: { from: 0, to: editor.state.doc.length, insert: Text.of(source.text.split(/\r\n?|\n/)) },
    })
    editor.scrollDOM.scrollTop = top
  }, [editing, lineSeparator, source])

  // Elemento selecionado -> linha dele, centralizada e marcada.
  useEffect(() => {
    const editor = view.current
    if (!editor) return
    if (editing) {
      editor.dispatch({ effects: markLine.of(null) })
      return
    }
    const line = lineOf(source.lines, selected)
    if (!line || line > editor.state.doc.lines) {
      editor.dispatch({ effects: markLine.of(null) })
      return
    }
    const position = editor.state.doc.line(line).from
    editor.dispatch({
      effects: [markLine.of(line), EditorView.scrollIntoView(position, { y: 'center' })],
      selection: editor.state.selection.main.head === position ? undefined : { anchor: position },
    })
  }, [editing, selected, source])

  useEffect(() => {
    const editor = view.current
    if (!editor) return
    if (!issue) {
      editor.dispatch({ effects: markError.of(null) })
      return
    }
    const line = editor.state.doc.line(Math.min(issue.line, editor.state.doc.lines))
    const index = [...line.text].slice(0, issue.column - 1).join('').length
    const from = line.from + index
    const to = Math.min(line.to, from + ((line.text.codePointAt(index) ?? 0) > 0xFFFF ? 2 : 1))
    editor.dispatch({
      effects: [markError.of({ from, to }), EditorView.scrollIntoView(from, { y: 'center' })],
      selection: { anchor: from },
    })
  }, [issue])

  return (
    <div
      ref={host}
      className="gf-source-editor"
      data-testid="source-editor"
      // Clicar (sem arrastar para selecionar texto) numa linha com WindowID seleciona o elemento.
      onPointerDown={(event) => { pressed.current = [event.clientX, event.clientY] }}
      onClick={(event) => {
        const editor = view.current
        const start = pressed.current
        pressed.current = null
        if (editing || !editor || event.button !== 0) return
        if (start && Math.hypot(event.clientX - start[0], event.clientY - start[1]) > 4) return
        const line = clickedLine(editor, event.target)
        const index = line == null ? -1 : linesRef.current.indexOf(line)
        if (index >= 0) select([index])
      }}
      onKeyDown={(event) => {
        // Ctrl+F abre a busca do CodeMirror mesmo com o foco fora do texto (no painel).
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f' && view.current) {
          event.preventDefault()
          event.stopPropagation()
          openSearchPanel(view.current)
        }
      }}
    />
  )
}

export default function SourcePanel() {
  useT()
  const open = useSource((state) => state.open)
  const draft = useSource((state) => state.draft)
  const path = useDoc((state) => state.path)
  const doc = useDoc((state) => state.doc)
  const [loaded, setLoaded] = useState<{ path: string; doc: typeof doc; source: DocSource } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!path) closeSource()
  }, [path])

  // Relê a cada mudança do documento (cada edição devolve um documento novo).
  useEffect(() => {
    if (!open || !path) return
    let active = true
    call<DocSource | null>('doc_source').then(
      (result) => {
        if (!active) return
        setLoaded(result ? { path, doc, source: result } : null)
        setError('')
      },
      (reason) => active && setError(reason instanceof Error ? reason.message : String(reason)),
    )
    return () => {
      active = false
    }
  }, [open, path, doc])

  const name = path?.split(/[\\/]/).pop() ?? ''
  const current = loaded?.path === path ? loaded : null
  const source = draft?.source ?? current?.source
  const codeWidth = panelWidth('code', useUi((state) => state.layout))
  return (
    <AnimatePresence>
      {open && path && (
        <motion.section
          key="source"
          className="gf-source-panel"
          data-testid="source-panel"
          aria-label={t('Código XML')}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 24 }}
          transition={{ duration: 0.16, ease: 'easeOut' }}
          style={{ width: codeWidth }}
        >
          <ResizeHandle side="code" className="gf-source-resize" />
          <header className="gf-source-header">
            <Icon name="code" size={16} className="text-accent-text" />
            <div className="min-w-0 flex-1">
              <div className="truncate font-semibold text-bright">{t('Código XML')}</div>
              <div className="truncate text-[11px] text-muted" title={path}>
                {name}{!draft && <> · {t('só leitura')}</>}
                {(source?.dirty || (draft && draft.text !== draft.source.text)) &&
                  <span className="text-gold"> · {t('com alterações não salvas')}</span>}
              </div>
            </div>
            {draft ? (
              <>
                <button className="btn btn-primary h-7 px-2" data-testid="source-apply" disabled={draft.busy}
                  onClick={() => void applyDraft()}>{t('Aplicar')}</button>
                <button className="btn h-7 px-2" disabled={draft.busy}
                  onClick={() => useSource.setState({ draft: null })}>{t('Cancelar')}</button>
              </>
            ) : (
              <button className="btn h-7 px-2" data-testid="source-edit" disabled={!current || current.doc !== doc}
                onClick={() => current && useSource.setState({
                  draft: { source: current.source, text: current.source.text },
                })}>{t('Editar')}</button>
            )}
            <button
              className="icon-button"
              title={`${t('Buscar')} (Ctrl+F)`}
              aria-label={t('Buscar')}
              onClick={() => {
                const node = document.querySelector('.gf-source-editor .cm-editor') as HTMLElement | null
                const editor = node ? EditorView.findFromDOM(node) : null
                if (editor) openSearchPanel(editor)
              }}
            >
              <Icon name="search" size={15} />
            </button>
            <button className="icon-button" title={`${t('Fechar')} (Ctrl+U)`} aria-label={t('Fechar')} onClick={closeSource}>
              <Icon name="x" size={16} />
            </button>
          </header>
          {draft?.issue && (
            <p className="px-4 py-2 text-danger" role="alert">
              {t('Linha {line}, coluna {column}', { line: draft.issue.line, column: draft.issue.column })} · {draft.issue.message}
            </p>
          )}
          {draft?.error && <p className="px-4 py-2 text-danger" role="alert">{draft.error}</p>}
          {error && !source ? (
            <p className="p-4 text-danger" role="alert">{error}</p>
          ) : source ? (
            <SourceEditor key={path} source={source} draft={draft} />
          ) : (
            <p className="p-4 text-muted">{t('Carregando…')}</p>
          )}
        </motion.section>
      )}
    </AnimatePresence>
  )
}
