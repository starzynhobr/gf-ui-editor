// XML avulso: camada de soltar (só arrastes com arquivos), selo/status/seção, o cartão com o
// destaque da primeira vez, fechar pela lista, toast e voo da importação, e a faixa "mudou fora".
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ShellState } from '../api'

const bridge = vi.hoisted(() => ({ call: vi.fn() }))
const sonner = vi.hoisted(() => ({ toast: vi.fn() }))
const saving = vi.hoisted(() => ({ confirmDiscard: vi.fn(async () => true), saveDocument: vi.fn(async () => true) }))
const docStore = vi.hoisted(() => ({ importStandalone: vi.fn(), checkExternalChange: vi.fn() }))

vi.mock('../bridge', async (original) => ({ ...(await original<typeof import('../bridge')>()), call: bridge.call }))
vi.mock('sonner', async (original) => ({ ...(await original<typeof import('sonner')>()), toast: sonner.toast }))
vi.mock('../shell/saving', async (original) => ({ ...(await original<typeof import('../shell/saving')>()), ...saving }))
vi.mock('./store', async (original) => ({ ...(await original<typeof import('./store')>()), ...docStore }))
vi.mock('../source/SourcePanel', async (original) => ({
  ...(await original<typeof import('../source/SourcePanel')>()),
  confirmSourceDraft: async () => true,
}))

const { readDrag, countLabel, default: DropOverlay } = await import('./DropOverlay')
const { folderOf, shortPath, closeStandaloneFile } = await import('./standalone')
const { default: StandaloneFiles } = await import('./StandaloneFiles')
const { default: StandaloneBar, COACH_FLAG } = await import('./StandaloneBar')
const { default: ExternalChangeBand, showExternalChange, clearExternalChange } = await import('./ExternalChangeBand')
const { importStandaloneFile } = await import('./standaloneActions')
const { default: StatusBar } = await import('../shell/StatusBar')
const { useShell } = await import('../store')
const { useUi } = await import('../shell/uiState')
const { useDoc } = await import('./store')
const { DialogHost, resetDialogs } = await import('../ui/dialogs')
const { setLanguage } = await import('../i18n')

const FILE = 'C:\\Users\\ana\\Desktop\\mods\\WorldMap2.xml'
const shell = (patch: Partial<ShellState> = {}): ShellState => ({
  language: 'pt_BR', project: null, open_path: FILE, standalone_paths: [FILE], pending: 0, version: '0.8.0',
  ...patch,
} as unknown as ShellState)

function dataTransfer(types: string[], items: { kind: string; type: string }[]) {
  return { types, items, dropEffect: 'copy' } as unknown as DataTransfer
}

function drag(name: string, data: DataTransfer) {
  const event = new Event(name, { bubbles: true, cancelable: true })
  Object.assign(event, { dataTransfer: data, relatedTarget: null, clientX: 100, clientY: 100 })
  act(() => void window.dispatchEvent(event))
}

beforeEach(() => {
  setLanguage('pt_BR')
  bridge.call.mockReset()
  sonner.toast.mockReset()
  useShell.setState({ shell: shell(), view: 'workspace', page: 'xml' })
  useUi.setState({ flags: {}, loaded: true })
})
afterEach(() => {
  cleanup()
  resetDialogs()
  clearExternalChange()
  vi.useRealTimers()
})

describe('camada de soltar', () => {
  it('conta XMLs e ignora arrastes sem arquivos', () => {
    expect(readDrag(dataTransfer(['text/plain'], []))).toBeNull()
    const files = readDrag(dataTransfer(['Files'], [
      { kind: 'file', type: 'text/xml' }, { kind: 'file', type: '' }, { kind: 'file', type: 'image/png' },
    ]))!
    expect(files).toEqual({ xmls: 1, unknown: 1, others: 1 })
    expect(countLabel(files)).toBe('2 XMLs')
    expect(countLabel({ xmls: 1, unknown: 0, others: 0 })).toBe('1 XML')
  })

  it('aparece com arquivos, avisa do projeto, some ao soltar e não reage ao arraste interno', async () => {
    useShell.setState({ shell: shell({ project: { root: 'C:/p' } as ShellState['project'] }) })
    render(<DropOverlay />)
    drag('dragover', dataTransfer(['text/plain'], []))
    expect(screen.queryByTestId('drop-overlay')).toBeNull()
    const xmls = dataTransfer(['Files'], [{ kind: 'file', type: 'text/xml' }, { kind: 'file', type: 'text/xml' }, { kind: 'file', type: 'application/xml' }])
    drag('dragenter', xmls)
    expect(screen.getByTestId('drop-overlay').dataset.state).toBe('ok')
    expect(screen.getByTestId('drop-count').textContent).toContain('3 XMLs')
    expect(screen.getByTestId('drop-overlay').textContent).toContain('Abre sem mexer no projeto')
    drag('drop', xmls)
    await waitFor(() => expect(screen.queryByTestId('drop-overlay')).toBeNull())
    expect(sonner.toast).not.toHaveBeenCalled()
  })

  it('só .xml: estado de recusa, cursor de proibido e toast ao soltar', async () => {
    render(<DropOverlay />)
    const png = dataTransfer(['Files'], [{ kind: 'file', type: 'image/png' }])
    drag('dragover', png)
    expect(screen.getByTestId('drop-overlay').dataset.state).toBe('reject')
    expect(screen.getByTestId('drop-overlay').textContent).toContain('Só arquivos .xml')
    expect(png.dropEffect).toBe('none')
    drag('drop', png)
    expect(sonner.toast).toHaveBeenCalledWith('Só arquivos .xml abrem no editor.')
  })

  it('some sozinha quando os dragover param (saiu da janela)', async () => {
    vi.useFakeTimers()
    render(<DropOverlay />)
    drag('dragover', dataTransfer(['Files'], [{ kind: 'file', type: 'text/xml' }]))
    expect(screen.getByTestId('drop-overlay')).toBeTruthy()
    act(() => void vi.advanceTimersByTime(400))
    vi.useRealTimers()
    await waitFor(() => expect(screen.queryByTestId('drop-overlay')).toBeNull())
  })
})

describe('estado avulso', () => {
  it('caminhos curtos', () => {
    expect(folderOf(FILE)).toBe('…\\Desktop\\mods')
    expect(folderOf('C:\\mods\\A.xml')).toBe('C:\\mods')
    expect(shortPath(FILE)).toBe('C:\\…\\WorldMap2.xml')
  })

  it('barra de status mostra "Avulso — C:\\…\\arquivo"', () => {
    render(<StatusBar />)
    const chip = screen.getByTestId('standalone-status')
    expect(chip.textContent).toBe('Avulso — C:\\…\\WorldMap2.xml')
    expect(chip.title).toBe(FILE)
  })

  it('seção "Arquivos avulsos" com a pasta de origem e o × que fecha', async () => {
    bridge.call.mockResolvedValue(shell({ open_path: null, standalone_paths: [] }))
    render(<StandaloneFiles filter="" />)
    expect(screen.getByTestId('standalone-files').textContent).toContain('ARQUIVOS AVULSOS · 1')
    expect(screen.getByTestId('standalone-files').textContent).toContain('…\\Desktop\\mods')
    fireEvent.click(screen.getByTestId('standalone-close'))
    await waitFor(() => expect(bridge.call).toHaveBeenCalledWith('standalone_close', FILE))
    expect(saving.confirmDiscard).toHaveBeenCalled()
    await waitFor(() => expect(useShell.getState().view).toBe('home'))
  })

  it('fechar cancelado em Descartar? não chama a ponte', async () => {
    saving.confirmDiscard.mockResolvedValueOnce(false)
    await closeStandaloneFile(FILE)
    expect(bridge.call).not.toHaveBeenCalled()
  })
})

describe('cartão do avulso', () => {
  it('três ações com a linha do que fazem e o destaque da primeira vez que não volta', async () => {
    bridge.call.mockResolvedValue(undefined)
    useDoc.setState({ path: FILE, doc: { elements: [] } } as never)
    render(<StandaloneBar />)
    const card = screen.getByTestId('standalone-bar')
    expect(card.textContent).toContain('Você está vendo um arquivo de fora do projeto')
    expect(screen.getByTestId('standalone-save').textContent).toContain('cópia de antes')
    expect(screen.getByTestId('standalone-import').textContent).toContain('Escolhe um projeto')
    expect(screen.getByTestId('standalone-compare').textContent).toContain('oficial')
    expect(screen.getByTestId('standalone-coach')).toBeTruthy()
    fireEvent.click(screen.getByTestId('standalone-coach-ok'))
    expect(bridge.call).toHaveBeenCalledWith('ui_set_flag', COACH_FLAG, true)
    await waitFor(() => expect(screen.queryByTestId('standalone-coach')).toBeNull())
  })

  it('não aparece para um XML do projeto', () => {
    useShell.setState({ shell: shell({ standalone_paths: [] }) })
    render(<StandaloneBar />)
    expect(screen.queryByTestId('standalone-bar')).toBeNull()
  })
})

describe('importar', () => {
  it('toast com as texturas copiadas e o voo até a linha do projeto', async () => {
    const imported = shell({ open_path: 'C:/p/ui/WorldMap2.xml', standalone_paths: [], project: { root: 'C:/p' } as ShellState['project'] })
    useShell.setState({ shell: shell({ project: { root: 'C:/p' } as ShellState['project'] }) })
    docStore.importStandalone.mockResolvedValue({ conflict: false, name: 'WorldMap2.xml', path: 'C:/p/ui/WorldMap2.xml', state: imported, textures: ['a.dds', 'b.dds'] })
    const row = document.createElement('div')
    row.dataset.file = 'WorldMap2.xml'
    row.getBoundingClientRect = () => new DOMRect(10, 200, 200, 26)
    document.body.appendChild(row)
    render(<DialogHost />)
    const done = importStandaloneFile(FILE, new DOMRect(500, 60, 120, 40))
    fireEvent.click(await screen.findByText('Importar'))
    await done
    expect(sonner.toast).toHaveBeenCalledWith('Importado para o projeto · 2 texturas copiadas', expect.anything())
    expect(useShell.getState().shell?.open_path).toBe('C:/p/ui/WorldMap2.xml')
    await waitFor(() => expect(row.classList.contains('gf-row-imported')).toBe(true), { timeout: 2000 })
    row.remove()
  })
})

describe('faixa "o arquivo mudou fora do editor" (stub)', () => {
  it('mostra Recarregar / Manter as minhas / Comparar e chama as ações', async () => {
    const reload = vi.fn()
    const keep = vi.fn()
    const compare = vi.fn()
    render(<ExternalChangeBand />)
    act(() => showExternalChange({ path: FILE, reload, keep, compare }))
    expect(screen.getByTestId('external-change-band').textContent).toContain('O arquivo mudou fora do editor')
    fireEvent.click(screen.getByTestId('external-compare'))
    await waitFor(() => expect(compare).toHaveBeenCalled())
    expect(screen.getByTestId('external-change-band')).toBeTruthy()
    fireEvent.click(screen.getByTestId('external-reload'))
    await waitFor(() => expect(reload).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByTestId('external-change-band')).toBeNull())
  })

  it('arquivo apagado: só "Manter as minhas"; outro XML aberto: some', async () => {
    render(<ExternalChangeBand />)
    act(() => showExternalChange({ path: FILE, missing: true, reload: vi.fn(), keep: vi.fn(), compare: vi.fn() }))
    expect(screen.queryByTestId('external-reload')).toBeNull()
    expect(screen.queryByTestId('external-compare')).toBeNull()
    expect(screen.getByTestId('external-keep')).toBeTruthy()
    act(() => useShell.setState({ shell: shell({ open_path: 'C:/outro.xml' }) }))
    await waitFor(() => expect(screen.queryByTestId('external-change-band')).toBeNull())
  })
})
