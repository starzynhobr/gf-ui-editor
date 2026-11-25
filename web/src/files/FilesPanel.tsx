// Lista de Arquivos XML / Texturas: seções Camadas, Alterados e Todos (ordem e alturas
// salvas, como a clássica), filtro e lista virtualizada (com ícones são ~18 mil arquivos).
import { useVirtualizer } from '@tanstack/react-virtual'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type FileListData, type SectionKind } from '../api'
import { useT } from '../i18n'
import { showStatus, useShell } from '../store'
import { openXml } from '../actions'
import { Icon } from '../ui/Icon'
import { openMenu, type MenuItem } from '../ui/Menu'

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
  const needle = filter.trim().toLowerCase()
  const sections = useMemo(() => {
    if (!data) return []
    return data.sections.map((section) => ({
      kind: section.kind,
      total: section.items.length,
      items: needle ? section.items.filter((index) => data.files[index].toLowerCase().includes(needle)) : section.items,
    }))
  }, [data, needle])
  const visible = sections.filter((section) => section.kind === 'all' || section.items.length > 0)
  const visibleKinds = visible.map((section) => section.kind)

  const activate = useCallback(
    (index: number) => {
      if (!data?.directory) return
      const relative = data.files[index]
      if (data.mode === 'textures') {
        showStatus(t('Prévia de texturas: chega junto com o canvas da interface nova.'), 6)
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
          showStatus(t('Aberto no {program}. Depois de salvar lá, aperte Ctrl+R aqui para ver a mudança.', { program: label }), 10)
        },
      })
    }
    items.push({ label: t('Abrir pasta'), icon: 'folder-open', onClick: () => void api.openFolder(data.directory!) })
    openMenu({ x, y, items })
  }

  const startResize = (kind: SectionKind, event: React.MouseEvent) => {
    event.preventDefault()
    const startY = event.clientY
    const start = heights[kind] ?? defaultHeight(sections.find((section) => section.kind === kind)?.items.length ?? 1)
    let latest = start
    const move = (moveEvent: MouseEvent) => {
      latest = Math.max(HEADER_HEIGHT + ROW_HEIGHT, Math.min(800, start + moveEvent.clientY - startY))
      setHeights((current) => ({ ...current, [kind]: latest }))
    }
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
      void api.setSectionHeights({ [kind]: Math.round(latest) })
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
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
      {data && !data.in_project && (
        <div className="mx-3 mb-2 rounded-md border border-border bg-card px-2.5 py-2 text-[12px] leading-snug text-muted">
          {data.directory
            ? t(
                'Arquivos soltos: o jogo só vê estas mudanças se você copiar os arquivos para a pasta da UI escolhida no launcher. Com um projeto, Enviar para o jogo faz isso por você.',
              )
            : t('Crie um projeto para editar fora da pasta do jogo e testar com F5.')}
        </div>
      )}
      {data && data.shared_publish.length > 0 && shell?.project && (
        <div className="mx-3 mb-2 hint-warning">
          {t(
            'O projeto {projects} também envia para UICustom/{folder}: um sobrescreve o outro no jogo. Troque em Projeto → Pasta de publicação…',
            { projects: data.shared_publish.join(', '), folder: shell.project.custom_name },
          )}
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col">
        {data &&
          visible.map((section) => {
            const isAll = section.kind === 'all'
            const height = heights[section.kind] ?? defaultHeight(section.items.length)
            return (
              <div
                key={section.kind}
                className={`flex min-h-0 flex-col ${isAll ? 'flex-1' : 'shrink-0'}`}
                style={isAll ? undefined : { height }}
                data-section={section.kind}
              >
                <div
                  className="group flex h-7 shrink-0 items-center gap-1 border-t border-border px-3"
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
                />
                {!isAll && (
                  <div
                    className="h-1 shrink-0 cursor-row-resize hover:bg-accent/40"
                    onMouseDown={(event) => startResize(section.kind, event)}
                  />
                )}
              </div>
            )
          })}
      </div>
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
}) {
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
    <div ref={parent} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto outline-none" onKeyDown={onKeyDown}>
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
              title={relative}
            >
              <Icon
                name={mode === 'textures' ? 'image' : 'file'}
                size={14}
                className={isModified ? 'text-accent-text' : 'text-disabled'}
              />
              <span className="min-w-0 flex-1 truncate text-[12.5px]">{relative}</span>
              {isModified && (
                <span className="text-[10px] text-gold" title={modifiedTitle}>
                  ●
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
