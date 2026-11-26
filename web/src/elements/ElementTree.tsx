// Árvore de elementos (Ctrl+3), como a da clássica: Estado (olho, cadeado, foco), ID,
// Tipo (com o texto do jogo) e ParentNode; botão direito no cabeçalho mostra/esconde ID e
// ParentNode; filtro pelo mesmo texto da clássica (text_preview.search_text).
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type TreeRow } from '../api'
import type { CanvasElement } from '../bridge'
import { useT } from '../i18n'
import { useShell } from '../store'
import { selectElements, setHidden, setIsolated, setLocked, useDocState } from '../shell/doc'
import { Icon } from '../ui/Icon'
import { openMenu } from '../ui/Menu'
import { kindLabel } from './kinds'

interface Node {
  element: CanvasElement
  children: Node[]
  depth: number
}

/** Hierarquia como a clássica: filho do primeiro elemento com o WindowID do ParentNode. */
export function buildTree(elements: CanvasElement[]): Node[] {
  const byId = new Map<string, Node>()
  const nodes = elements.map((element) => ({ element, children: [] as Node[], depth: 0 }))
  for (const node of nodes) if (!byId.has(node.element.id)) byId.set(node.element.id, node)
  const roots: Node[] = []
  for (const node of nodes) {
    const parent = node.element.parent != null ? byId.get(node.element.parent) : undefined
    if (parent && parent !== node) parent.children.push(node)
    else roots.push(node)
  }
  const setDepth = (list: Node[], depth: number, seen: Set<Node>) => {
    for (const node of list) {
      if (seen.has(node)) continue
      seen.add(node)
      node.depth = depth
      setDepth(node.children, depth + 1, seen)
    }
  }
  setDepth(roots, 0, new Set())
  return roots
}

export default function ElementTree() {
  const t = useT()
  const path = useDocState((state) => state.path)
  const doc = useDocState((state) => state.doc)
  const selection = useDocState((state) => state.selection)
  const hidden = useDocState((state) => state.hidden)
  const locked = useDocState((state) => state.locked)
  const isolated = useDocState((state) => state.isolated)
  const language = useShell((state) => state.shell?.language)
  const revision = useShell((state) => state.revision)
  const [rows, setRows] = useState<Record<number, TreeRow>>({})
  const [filter, setFilter] = useState('')
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [hiddenColumns, setHiddenColumns] = useState<string[]>(['2'])
  const anchor = useRef<number | null>(null)
  const list = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void api.treeColumns().then(setHiddenColumns)
  }, [])

  const kinds = useMemo(() => (doc ? doc.elements.map((element) => kindLabel(element.kind, element.ctrl_type)) : []), [doc, language]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!path || !doc) {
      setRows({})
      return
    }
    let alive = true
    api.elementTree(path, kinds).then(
      (list) => alive && setRows(Object.fromEntries(list.map((row) => [row.index, row]))),
      () => alive && setRows({}),
    )
    return () => {
      alive = false
    }
  }, [path, doc, kinds, revision])

  useEffect(() => setCollapsed(new Set()), [path])

  const tree = useMemo(() => (doc ? buildTree(doc.elements) : []), [doc])
  const query = filter.trim().toLocaleLowerCase()

  // Linhas visíveis (pré-ordem), respeitando o filtro e o que está recolhido.
  const visible = useMemo(() => {
    const result: Node[] = []
    const matches = (node: Node): boolean => {
      const own = !query || (rows[node.element.index]?.search ?? '').includes(query)
      const child = node.children.map(matches).some(Boolean)
      matched.set(node, own || child)
      return own || child
    }
    const matched = new Map<Node, boolean>()
    tree.forEach(matches)
    const walk = (nodes: Node[]) => {
      for (const node of nodes) {
        if (!matched.get(node)) continue
        result.push(node)
        if (query || !collapsed.has(node.element.index)) walk(node.children)
      }
    }
    walk(tree)
    return result
  }, [tree, rows, query, collapsed])

  const order = visible.map((node) => node.element.index)
  const primary = selection[0] ?? null

  // Seleção vinda do canvas: abre os pais e rola até o item.
  useEffect(() => {
    if (primary == null || !doc) return
    const byId = new Map(doc.elements.map((element) => [element.id, element]))
    let parent = doc.elements[primary]?.parent
    const open: number[] = []
    const seen = new Set<string>()
    while (parent != null && !seen.has(parent)) {
      seen.add(parent)
      const element = byId.get(parent)
      if (!element) break
      open.push(element.index)
      parent = element.parent
    }
    if (open.some((index) => collapsed.has(index))) {
      setCollapsed((current) => new Set([...current].filter((index) => !open.includes(index))))
    }
    requestAnimationFrame(() => list.current?.querySelector(`[data-index="${primary}"]`)?.scrollIntoView({ block: 'nearest' }))
  }, [primary, doc]) // eslint-disable-line react-hooks/exhaustive-deps

  const click = (index: number, event: React.MouseEvent) => {
    if (event.shiftKey && anchor.current != null && order.includes(anchor.current)) {
      const [from, to] = [order.indexOf(anchor.current), order.indexOf(index)].sort((a, b) => a - b)
      const range = order.slice(from, to + 1).filter((item) => item !== index)
      selectElements([index, ...range], 'replace')
      return
    }
    if (event.ctrlKey || event.metaKey) selectElements([index], 'toggle')
    else selectElements([index], 'replace')
    anchor.current = index
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!order.length || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')) return
    event.preventDefault()
    const position = primary != null ? order.indexOf(primary) : -1
    const next = event.key === 'ArrowDown' ? Math.min(order.length - 1, position + 1) : Math.max(0, position - 1)
    selectElements([order[next]], 'replace')
    anchor.current = order[next]
  }

  const headerMenu = (event: React.MouseEvent) => {
    event.preventDefault()
    const toggle = (column: string) => {
      const next = hiddenColumns.includes(column) ? hiddenColumns.filter((item) => item !== column) : [...hiddenColumns, column]
      setHiddenColumns(next)
      void api.setTreeColumns(next)
    }
    openMenu({
      x: event.clientX,
      y: event.clientY,
      items: [
        { label: 'WindowID', checked: !hiddenColumns.includes('0'), onClick: () => toggle('0') },
        { label: 'ParentNode', checked: !hiddenColumns.includes('2'), onClick: () => toggle('2') },
      ],
    })
  }

  const showId = !hiddenColumns.includes('0')
  const showParent = !hiddenColumns.includes('2')
  const columns = `72px ${showId ? 'minmax(44px,auto) ' : ''}minmax(0,1fr)${showParent ? ' minmax(56px,auto)' : ''}`
  const selected = new Set(selection)

  const stateButton = (index: number, kind: 'hidden' | 'locked' | 'isolated') => {
    const on = kind === 'hidden' ? hidden.includes(index) : kind === 'locked' ? locked.includes(index) : isolated === index
    const icon = kind === 'hidden' ? (on ? 'eye-off' : 'eye') : kind === 'locked' ? 'lock' : 'focus'
    const title = kind === 'hidden' ? t('Ocultar') : kind === 'locked' ? t('Bloquear') : t('Isolar')
    return (
      <button
        className={`flex h-5 w-5 items-center justify-center rounded hover:bg-pressed ${
          on ? (kind === 'isolated' ? 'text-warning' : 'text-accent-text') : 'text-disabled opacity-0 group-hover:opacity-100'
        }`}
        title={title}
        aria-label={title}
        aria-pressed={on}
        data-state={kind}
        onClick={(event) => {
          event.stopPropagation()
          if (kind === 'hidden') setHidden([index], !on)
          else if (kind === 'locked') setLocked([index], !on)
          else setIsolated(on ? null : index)
        }}
      >
        <Icon name={icon} size={14} />
      </button>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="element-tree">
      <div className="px-3 pt-3 pb-2 text-[13px] font-semibold text-bright">{t('Elementos')}</div>
      <div className="relative px-3 pb-2">
        <Icon name="search" size={14} className="pointer-events-none absolute top-2 left-5.5 text-disabled" />
        <input
          className="field h-7 w-full pl-7"
          placeholder={t('Pesquisar WindowID, tipo, texto ou textura…')}
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
      </div>
      {!doc ? (
        <div className="px-3 py-2 text-muted">{t('Selecione um item no canvas ou na lista para editar sua geometria.')}</div>
      ) : (
        <>
          <div
            className="section-label grid shrink-0 items-center gap-2 border-y border-border px-3 py-1.5"
            style={{ gridTemplateColumns: columns }}
            onContextMenu={headerMenu}
            data-testid="tree-header"
          >
            <span>{t('Estado')}</span>
            {showId && <span title="WindowID">ID</span>}
            <span>{t('Tipo')}</span>
            {showParent && <span>ParentNode</span>}
          </div>
          <div ref={list} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto py-1 outline-none" onKeyDown={onKeyDown}>
            {visible.map((node) => {
              const { element } = node
              const row = rows[element.index]
              const kind = kinds[element.index] ?? element.kind
              const label = row?.label ? `${kind} · ${row.label}` : kind
              const hasChildren = node.children.length > 0
              const isCollapsed = !query && collapsed.has(element.index)
              return (
                <div
                  key={element.index}
                  data-index={element.index}
                  data-testid="tree-row"
                  role="treeitem"
                  aria-selected={selected.has(element.index)}
                  className={`group grid h-[26px] items-center gap-2 px-3 ${
                    selected.has(element.index)
                      ? element.index === primary
                        ? 'bg-selected text-bright'
                        : 'bg-selected/60 text-bright'
                      : 'hover:bg-hover'
                  } ${hidden.includes(element.index) ? 'opacity-55' : ''}`}
                  style={{ gridTemplateColumns: columns }}
                  onClick={(event) => click(element.index, event)}
                >
                  <span className="flex items-center gap-0.5">
                    {stateButton(element.index, 'hidden')}
                    {stateButton(element.index, 'locked')}
                    {stateButton(element.index, 'isolated')}
                  </span>
                  {showId && <span className="truncate font-mono text-[11.5px] text-muted">{element.id}</span>}
                  <span className="flex min-w-0 items-center" style={{ paddingLeft: node.depth * 14 }}>
                    <span
                      className={`mr-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-muted ${hasChildren ? 'hover:text-bright' : 'invisible'}`}
                      onClick={(event) => {
                        event.stopPropagation()
                        setCollapsed((current) => {
                          const next = new Set(current)
                          if (next.has(element.index)) next.delete(element.index)
                          else next.add(element.index)
                          return next
                        })
                      }}
                    >
                      <Icon name={isCollapsed ? 'chevron-right' : 'chevron-down'} size={12} />
                    </span>
                    <span className="truncate" title={row?.label || undefined}>
                      {label}
                    </span>
                  </span>
                  {showParent && <span className="truncate font-mono text-[11.5px] text-muted">{element.parent ?? ''}</span>}
                </div>
              )
            })}
            {query && visible.length === 0 && <div className="px-3 py-2 text-muted">—</div>}
          </div>
        </>
      )}
    </div>
  )
}
