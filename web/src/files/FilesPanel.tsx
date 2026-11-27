// Lista de Arquivos XML / Texturas: seções Camadas, Alterados e Todos (ordem e alturas
// salvas, como a clássica), filtro e lista virtualizada (com ícones são ~18 mil arquivos).
import { call } from '../bridge'
import { useOfficial } from '../project/official'
import { atlasModule } from '../shell/atlas'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { api, type FileListData, type SectionKind } from '../api'
import { useT } from '../i18n'
import { showStatus, useShell } from '../store'
import { openXml } from '../actions'
import { projectFileItems } from './fileActions'
import { Icon } from '../ui/Icon'
import { EmptyState } from '../ui/EmptyState'
import { openMenu, type MenuItem } from '../ui/Menu'
import { TexturePeek, useTexturePeek } from './TexturePeek'
import StandaloneFiles from '../doc/StandaloneFiles'

const ROW_HEIGHT = 24
const HEADER_HEIGHT = 28
const DEFAULT_ORDER: SectionKind[] = ['layers', 'changed', 'all']

const norm = (path: string) => path.replace(/\//g, '\\').toLowerCase()

function joinPath(directory: string, relative: string): string {
  return `${directory.replace(/[\\/]+$/, '')}\\${relative.replace(/\//g, '\\')}`
}

interface Active {
  kind: SectionKind
  index: number // índice em `files`
}

export default function FilesPanel() {
  const t = useT()
  const page = useShell((state) => state.page)
  const shell = useShell((state) => state.shell)
  const revision = useShell((state) => state.revision)
  const mode = page === 'textures' ? 'textures' : 'xml'
  const [data, setData] = useState<FileListData | null>(null)
  const [filter, setFilter] = useState('')
  const [active, setActive] = useState<Active | null>(null)
  const [editorName, setEditorName] = useState('Notepad++')
  const [heights, setHeights] = useState<Partial<Record<SectionKind, number>>>({})

  useEffect(() => {
    let alive = true
    void api.fileList(mode).then((value) => {
      if (!alive) return
      setData(value)
      setHeights(value.heights)
    })
    return () => {
      alive = false
    }
  }, [mode, revision])

  useEffect(() => {
    void api.textEditorName().then(setEditorName)
  }, [])

  const openPath = shell?.open_path ? norm(shell.open_path) : null
  const modified = useMemo(() => new Set(data?.modified ?? []), [data])
  const layerSet = useMemo(() => new Set(data?.layers ?? []), [data])
  useEffect(() => {
    // A barra do canvas também muda as camadas: a lista relê.
    const reload = () => useShell.setState((state) => ({ revision: state.revision + 1 }))
    window.addEventListener('gf:layers-changed', reload)
    return () => window.removeEventListener('gf:layers-changed', reload)
  }, [])
  const officialDiffs = useOfficial((state) => state.diffs)
  const toggleLayer = useCallback(
    async (index: number, on: boolean) => {
      if (!data?.directory) return
      const path = joinPath(data.directory, data.files[index])
      try {
        await call('canvas_change_layers', path, on ? 'add' : 'remove', data.files[index])
      } catch (error) {
        showStatus(error instanceof Error ? error.message : String(error), 6)
        return
      }
      window.dispatchEvent(new CustomEvent('gf:layers-changed'))
    },
    [data],
  )
  const needle = filter.trim().toLowerCase()
  const sections = useMemo(() => {
    if (!data) return []
    return data.sections.map((section) => ({
      kind: section.kind,
      total: section.items.length,
      items: needle ? section.items.filter((index) => data.files[index].toLowerCase().includes(needle)) : section.items,
    }))
  }, [data, needle])
  const [pendingOrder, setPendingOrder] = useState<SectionKind[] | null>(null)
  useEffect(() => setPendingOrder(null), [data])
  const ordered = pendingOrder ? pendingOrder.map((kind) => sections.find((section) => section.kind === kind)!).filter(Boolean) : sections
  const visible = ordered.filter((section) => section.kind === 'all' || section.items.length > 0)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }))
  const onDragEnd = ({ active: dragged, over }: DragEndEvent) => {
    if (!over || dragged.id === over.id) return
    const kinds = visible.map((section) => section.kind)
    const nextVisible = arrayMove(kinds, kinds.indexOf(dragged.id as SectionKind), kinds.indexOf(over.id as SectionKind))
    // Seções escondidas (vazias) ficam no lugar delas; as visíveis ocupam as próprias vagas na nova ordem.
    const full = ordered.map((section) => section.kind)
    let slot = 0
    const merged = full.map((kind) => (kinds.includes(kind) ? nextVisible[slot++] : kind))
    setPendingOrder(merged)
    void api.setSectionOrder(merged).then(() => useShell.setState((state) => ({ revision: state.revision + 1 })))
  }
  const visibleKinds = visible.map((section) => section.kind)

  const activate = useCallback(
    (index: number) => {
      if (!data?.directory) return
      const relative = data.files[index]
      if (data.mode === 'textures') {
        const path = joinPath(data.directory, relative)
        void atlasModule().then((atlas) => atlas?.previewTexture(path))
        return
      }
      void openXml(joinPath(data.directory, relative))
    },
    [data, t],
  )

  const moveSection = async (kind: SectionKind, step: number) => {
    await api.moveSection(kind, step, visibleKinds)
    useShell.setState((state) => ({ revision: state.revision + 1 }))
  }

  const sectionMenu = (kind: SectionKind, x: number, y: number) => {
    const position = visibleKinds.indexOf(kind)
    const order = data?.sections.map((section) => section.kind) ?? DEFAULT_ORDER
    openMenu({
      x,
      y,
      items: [
        { label: t('Mover para cima'), icon: 'arrow-up', disabled: position <= 0, onClick: () => void moveSection(kind, -1) },
        {
          label: t('Mover para baixo'),
          icon: 'arrow-down',
          disabled: position < 0 || position >= visibleKinds.length - 1,
          onClick: () => void moveSection(kind, 1),
        },
        { separator: true },
        {
          label: t('Restaurar ordem padrão'),
          disabled: order.join() === DEFAULT_ORDER.join(),
          onClick: async () => {
            await api.setSectionOrder(DEFAULT_ORDER)
            useShell.setState((state) => ({ revision: state.revision + 1 }))
          },
        },
      ],
    })
  }

  const fileMenu = (index: number, x: number, y: number) => {
    if (!data?.directory) return
    const path = joinPath(data.directory, data.files[index])
    const items: MenuItem[] = [{ label: t('Abrir'), onClick: () => activate(index) }]
    if (data.mode === 'xml') {
      items.push({
        label: t('Abrir no {program}', { program: editorName }),
        icon: 'type',
        onClick: async () => {
          const label = await api.openInTextEditor(path)
          showStatus(t('Aberto no {program}. Ao salvar lá, o editor mostra a mudança sozinho.', { program: label }), 10)
        },
      })
    }
    items.push({ label: t('Abrir pasta'), icon: 'folder-open', onClick: () => void api.openFolder(data.directory!) })
    void api
      .fileHistory(path)
      .catch(() => null)
      .then((history) => {
        if (history) items.push({ separator: true }, ...projectFileItems(path, history))
        openMenu({ x, y, items })
      })
  }

  // Alça entre duas seções vizinhas (como o QSplitter da clássica): só a fronteira entre elas
  // anda; uma cresce e a outra encolhe. "Todos" ocupa o resto, então nunca sai da tela.
  const listBox = useRef<HTMLDivElement>(null)
  const startResize = (upper: SectionKind, lower: SectionKind, event: React.MouseEvent) => {
    event.preventDefault()
    const handle = event.currentTarget as HTMLElement
    const box = listBox.current
    const measure = (kind: SectionKind) =>
      box?.querySelector<HTMLElement>(`[data-section="${kind}"]`)?.getBoundingClientRect().height ?? 0
    const minimum = HEADER_HEIGHT + ROW_HEIGHT
    const allMinimum = HEADER_HEIGHT + ROW_HEIGHT * 2
    const startY = event.clientY
    const upperStart = measure(upper)
    const lowerStart = measure(lower)
    let latest: Partial<Record<SectionKind, number>> = {}
    const move = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientY - startY
      if (upper === 'all') {
        // Todos em cima: a de baixo encolhe/cresce; Todos fica com o resto.
        const max = lowerStart + (upperStart - allMinimum)
        latest = { [lower]: Math.round(Math.max(minimum, Math.min(max, lowerStart - delta))) }
      } else if (lower === 'all') {
        const max = upperStart + (lowerStart - allMinimum)
        latest = { [upper]: Math.round(Math.max(minimum, Math.min(max, upperStart + delta))) }
      } else {
        const total = upperStart + lowerStart
        const next = Math.round(Math.max(minimum, Math.min(total - minimum, upperStart + delta)))
        latest = { [upper]: next, [lower]: total - next }
      }
      setHeights((current) => ({ ...current, ...latest }))
    }
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
      document.body.classList.remove('is-row-resizing')
      handle.classList.remove('is-dragging')
      if (Object.keys(latest).length) void api.setSectionHeights(latest)
    }
    document.body.classList.add('is-row-resizing')
    handle.classList.add('is-dragging')
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  // Prévia flutuante das texturas: a lista informa a linha sob o mouse; o cartão fica ao lado.
  const peek = useTexturePeek(mode === 'textures')
  const hoverRow = (index: number | null, row: HTMLElement | null) => {
    if (index == null || !row || !data?.directory || data.mode !== 'textures') {
      peek.hover(null)
      return
    }
    const rect = row.getBoundingClientRect()
    peek.hover({
      path: joinPath(data.directory, data.files[index]),
      rowTop: rect.top,
      rowHeight: rect.height,
      anchorRight: listBox.current?.getBoundingClientRect().right ?? rect.right,
    })
  }

  const title = mode === 'textures' ? t('Texturas') : t('Arquivos XML')
  const sectionTitle = (kind: SectionKind, count: number) =>
    kind === 'layers'
      ? t('CAMADAS · {count}', { count })
      : kind === 'changed'
        ? t('ALTERADOS · {count}', { count })
        : t('TODOS · {count}', { count })

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="files-panel">
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">
        <div className="flex-1 text-[13px] font-semibold text-bright">{title}</div>
      </div>
      <div className="relative px-3 pb-2">
        <Icon name="search" size={14} className="pointer-events-none absolute top-2 left-5.5 text-disabled" />
        <input
          className="field h-7 w-full pl-7"
          placeholder={mode === 'textures' ? t('Filtrar texturas…') : t('Filtrar arquivos…')}
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
      </div>
      {mode === 'xml' && <StandaloneFiles filter={needle} />}
      {data && !data.in_project && data.directory && (
        <div className="mx-3 mb-2 rounded-md border border-border bg-card px-2.5 py-2 text-[12px] leading-snug text-muted">
          {t(
            'Arquivos soltos: o jogo só vê estas mudanças se você copiar os arquivos para a pasta da UI escolhida no launcher. Com um projeto, Enviar para o jogo faz isso por você.',
          )}
        </div>
      )}
      {data && !data.in_project && !data.directory && !shell?.standalone_paths?.length && (
        <EmptyState
          icon="folder-plus"
          title={t('Sem projeto')}
          text={t('Crie um projeto para editar fora da pasta do jogo e testar com F5.')}
          testId="files-empty"
        />
      )}
      {data && data.shared_publish.length > 0 && shell?.project && (
        <div className="mx-3 mb-2 hint-warning">
          {t(
            'O projeto {projects} também envia para UICustom/{folder}: um sobrescreve o outro no jogo. Troque em Projeto → Pasta de publicação…',
            { projects: data.shared_publish.join(', '), folder: shell.project.custom_name },
          )}
        </div>
      )}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <SortableContext items={visible.map((section) => section.kind)} strategy={verticalListSortingStrategy}>
      <div ref={listBox} className="flex min-h-0 flex-1 flex-col">
        {data &&
          (data.in_project || data.directory) &&
          visible.map((section, position) => {
            const next = visible[position + 1]
            const isAll = section.kind === 'all'
            const height = heights[section.kind] ?? defaultHeight(section.items.length)
            return (
              <SortableSection
                key={section.kind}
                id={section.kind}
                className="flex min-h-0 flex-col"
                style={isAll ? { flex: '1 1 0', minHeight: HEADER_HEIGHT + ROW_HEIGHT * 2 } : { flex: `0 1 ${height}px`, minHeight: HEADER_HEIGHT + ROW_HEIGHT }}
                header={(handle) => (
                <div
                  {...handle}
                  className="group flex h-7 shrink-0 cursor-grab items-center gap-1 border-t border-border px-3 active:cursor-grabbing"
                  title={t('Arraste para mudar a seção de lugar')}
                  onContextMenu={(event) => {
                    event.preventDefault()
                    sectionMenu(section.kind, event.clientX, event.clientY)
                  }}
                >
                  <span className="section-label flex-1">{sectionTitle(section.kind, section.total)}</span>
                  <button
                    className="icon-button h-5 w-5 opacity-0 group-hover:opacity-100"
                    aria-label={t('Mais ações')}
                    onClick={(event) => {
                      const rect = event.currentTarget.getBoundingClientRect()
                      sectionMenu(section.kind, rect.left, rect.bottom + 4)
                    }}
                  >
                    <Icon name="dots" size={14} />
                  </button>
                </div>
                )}
              >
                <FileRows
                  files={data.files}
                  items={section.items}
                  modified={modified}
                  directory={data.directory}
                  mode={data.mode}
                  openPath={openPath}
                  active={active?.kind === section.kind ? active.index : null}
                  onActive={(index) => setActive({ kind: section.kind, index })}
                  onOpen={activate}
                  onMenu={fileMenu}
                  modifiedTitle={t('alterado')}
                  layers={layerSet}
                  canLayer={Boolean(data.in_project)}
                  onLayer={toggleLayer}
                  diffs={officialDiffs}
                  onHoverRow={hoverRow}
                  onHidePeek={peek.hide}
                />
                {next && (
                  <div
                    className="gf-row-resize"
                    data-testid={`resize-${section.kind}-${next.kind}`}
                    onMouseDown={(event) => startResize(section.kind, next.kind, event)}
                  />
                )}
              </SortableSection>
            )
          })}
      </div>
      </SortableContext>
      </DndContext>
      {mode === 'textures' && <TexturePeek target={peek.target} />}
    </div>
  )
}

function defaultHeight(count: number): number {
  return Math.min(HEADER_HEIGHT + 4 + ROW_HEIGHT * Math.max(1, count), HEADER_HEIGHT + 4 + ROW_HEIGHT * 6)
}

function FileRows({
  files,
  items,
  modified,
  directory,
  mode,
  openPath,
  active,
  onActive,
  onOpen,
  onMenu,
  modifiedTitle,
  layers,
  canLayer,
  onLayer,
  diffs,
  onHoverRow,
  onHidePeek,
}: {
  files: string[]
  items: number[]
  modified: Set<number>
  directory: string | null
  mode: 'xml' | 'textures'
  openPath: string | null
  active: number | null
  onActive: (index: number) => void
  onOpen: (index: number) => void
  onMenu: (index: number, x: number, y: number) => void
  modifiedTitle: string
  layers: Set<number>
  canLayer: boolean
  onLayer: (index: number, on: boolean) => void
  diffs: Record<string, { new_ids: string[]; other_ids: string[] }>
  onHoverRow?: (index: number | null, row: HTMLElement | null) => void
  onHidePeek?: (mute?: boolean) => void
}) {
  const t = useT()
  const parent = useRef<HTMLDivElement>(null)
  const timer = useRef<number | undefined>(undefined)
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parent.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!items.length) return
    const position = active != null ? items.indexOf(active) : -1
    let next = position
    if (event.key === 'ArrowDown') next = Math.min(items.length - 1, position + 1)
    else if (event.key === 'ArrowUp') next = Math.max(0, position - 1)
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = items.length - 1
    else if (event.key === 'PageDown') next = Math.min(items.length - 1, position + 15)
    else if (event.key === 'PageUp') next = Math.max(0, position - 15)
    else if (event.key === 'Enter' && active != null) {
      onOpen(active)
      return
    } else return
    event.preventDefault()
    if (next < 0 || next === position) return
    onActive(items[next])
    virtualizer.scrollToIndex(next, { align: 'auto' })
    // Pelas setas, só os XMLs abrem (como a clássica), com um respiro para não abrir cada um.
    if (mode === 'xml') {
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => onOpen(items[next]), 140)
    }
  }

  return (
    <div
      ref={parent}
      tabIndex={0}
      className="min-h-0 flex-1 overflow-y-auto outline-none"
      onKeyDown={(event) => {
        onHidePeek?.()
        onKeyDown(event)
      }}
      onMouseMove={(event) => {
        const row = (event.target as HTMLElement).closest<HTMLElement>('[data-index]')
        onHoverRow?.(row ? Number(row.dataset.index) : null, row)
      }}
      onMouseLeave={() => onHoverRow?.(null, null)}
      onScroll={() => onHidePeek?.()}
      onMouseDownCapture={() => onHidePeek?.(true)}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((row) => {
          const index = items[row.index]
          const relative = files[index]
          const isModified = modified.has(index)
          const isOpen = openPath != null && directory != null && norm(joinPath(directory, relative)) === openPath
          return (
            <div
              key={row.key}
              data-file={relative}
              data-index={index}
              className={`absolute inset-x-0 flex items-center gap-2 px-3 ${
                active === index ? 'bg-selected' : 'hover:bg-hover'
              } ${isOpen ? 'font-semibold text-bright' : 'text-text'}`}
              style={{ height: ROW_HEIGHT, transform: `translateY(${row.start}px)` }}
              onMouseDown={() => onActive(index)}
              onClick={() => onOpen(index)}
              onContextMenu={(event) => {
                event.preventDefault()
                onActive(index)
                onMenu(index, event.clientX, event.clientY)
              }}
              title={mode === 'textures' ? undefined : relative}
            >
              {canLayer && mode === 'xml' && (
                <input
                  type="checkbox"
                  data-testid="layer-check"
                  checked={layers.has(index)}
                  title={t('Marque para ver esta janela junto, onde o jogo a desenha (Preview do jogo)')}
                  onMouseDown={(event) => event.stopPropagation()}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => onLayer(index, event.target.checked)}
                />
              )}
              <Icon
                name={mode === 'textures' ? 'image' : 'file'}
                size={14}
                className={isModified ? 'text-accent-text' : 'text-disabled'}
              />
              <span className="min-w-0 flex-1 truncate text-[12.5px]">{relative}</span>
              {(() => {
                const diff = diffs[relative.replace(/\\/g, '/').toLowerCase()]
                if (diff?.new_ids.length)
                  return (
                    <span className="font-mono text-[10.5px] text-warning" title={t('A atualização do jogo trouxe {count} controle(s) que este arquivo não tem', { count: diff.new_ids.length })}>
                      +{diff.new_ids.length}
                    </span>
                  )
                if (diff?.other_ids.length)
                  return (
                    <span className="font-mono text-[10.5px] text-disabled" title={t('A UI oficial tem {count} controle(s) que este arquivo não tem (podem ter sido removidos de propósito)', { count: diff.other_ids.length })}>
                      {isModified ? <span className="mr-1 text-gold">●</span> : null}
                      {diff.other_ids.length}
                    </span>
                  )
                return isModified ? (
                  <span className="text-[10px] text-gold" title={modifiedTitle}>
                    ●
                  </span>
                ) : null
              })()}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Seção da lista que muda de lugar arrastando o título (dnd-kit, com animação dos vizinhos). */
function SortableSection({
  id,
  className,
  style,
  header,
  children,
}: {
  id: SectionKind
  className: string
  style?: React.CSSProperties
  header: (handle: Record<string, unknown>) => ReactNode
  children: ReactNode
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  return (
    <div
      ref={setNodeRef}
      data-section={id}
      className={`${className} ${isDragging ? 'gf-section-dragging' : ''}`}
      style={{ ...style, transform: CSS.Translate.toString(transform), transition, zIndex: isDragging ? 20 : undefined }}
    >
      {header({ ...attributes, ...listeners })}
      {children}
    </div>
  )
}
