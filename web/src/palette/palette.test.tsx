// Paleta de comandos (Ctrl+K) e "Ver código XML" (Ctrl+U) sem janela: ponte e store falsos.
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const XML = '<Root_Node>\n  <BaseWndProperty WindowID="1" WindowLeft="43">\n    <BaseWndProperty WindowID="10"/>\n  </BaseWndProperty>\n</Root_Node>\n'
const bridge = vi.hoisted(() => ({
  call: vi.fn(async (name: string) =>
    name === 'doc_source' ? { path: 'C:\\ui\\Test.xml', text: XML_TEXT(), lines: [2, 3, 3, 3], dirty: true } : undefined,
  ),
}))
// vi.hoisted roda antes das constantes do módulo: o texto vem por função.
function XML_TEXT() {
  return XML
}
const shellApi = vi.hoisted(() => ({
  homeData: vi.fn(async () => ({ projects: [{ root: 'C:\\p\\Outro', title: 'Outro projeto', current: false }] })),
  fileList: vi.fn(async () => ({ directory: 'C:\\ui', files: ['Test.xml', 'Inventory.xml'] })),
  setLanguage: vi.fn(),
}))
const actions = vi.hoisted(() => ({ openXml: vi.fn(async () => undefined), openProject: vi.fn(async () => undefined) }))

vi.mock('../bridge', async (original) => ({ ...(await original<typeof import('../bridge')>()), call: bridge.call }))
vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return { ...actual, api: { ...actual.api, ...shellApi } }
})
vi.mock('../actions', async (original) => ({ ...(await original<typeof import('../actions')>()), ...actions }))
vi.mock('../doc/store', async () => await import('../test/mockStore'))

const { default: CommandPalette, usePalette } = await import('./CommandPalette')
const { default: SourcePanel, useSource } = await import('../source/SourcePanel')
const { installShortcuts } = await import('../shell/shortcuts')
const { useShell } = await import('../store')
const mock = await import('../test/mockStore')

// O CodeMirror mede o texto com Range; o jsdom não implementa a geometria.
const emptyRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList
Range.prototype.getClientRects = emptyRects
Range.prototype.getBoundingClientRect = () => new DOMRect()
// O cmdk observa o tamanho da lista.
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= () => undefined

let uninstall: () => void = () => undefined

beforeEach(() => {
  mock.resetMock()
  mock.loadMockDocument('C:\\ui\\Test.xml', mock.sampleDocument())
  useShell.setState({
    view: 'workspace',
    page: 'xml',
    shell: { project: { root: 'C:\\p\\Teste', name: 'Teste', game_dir: 'C:\\Jogo' }, open_path: 'C:\\ui\\Test.xml', language: 'pt_BR' } as never,
  })
  uninstall = installShortcuts()
})

afterEach(() => {
  uninstall()
  cleanup()
  usePalette.setState({ open: false })
  useSource.setState({ open: false })
})

function press(key: string) {
  act(() => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key, ctrlKey: true, bubbles: true, cancelable: true }))
  })
}

function search(text: string) {
  fireEvent.change(screen.getByTestId('command-input'), { target: { value: text } })
}

describe('paleta de comandos', () => {
  it('Ctrl+K abre e o comando Ver código XML abre o painel de código', async () => {
    render(<><CommandPalette /><SourcePanel /></>)
    press('k')
    expect(await screen.findByTestId('command-palette')).toBeTruthy()
    expect(screen.getByText('Ctrl+U')).toBeTruthy()
    search('código XML')
    fireEvent.keyDown(screen.getByTestId('command-input'), { key: 'Enter' })
    await waitFor(() => expect(useSource.getState().open).toBe(true))
    await waitFor(() => expect(screen.queryByTestId('command-palette')).toBeNull())
    await waitFor(() => expect(document.querySelector('.cm-content')?.textContent).toContain('WindowLeft="43"'))
    expect(bridge.call).toHaveBeenCalledWith('doc_source')
  })

  it('seleciona elemento pelo WindowID e abre XML pelo nome', async () => {
    render(<CommandPalette />)
    press('k')
    await screen.findByTestId('command-palette')
    search('12')
    fireEvent.keyDown(screen.getByTestId('command-input'), { key: 'Enter' })
    await waitFor(() => expect(mock.useDoc.getState().selection).toEqual([3]))

    press('k')
    await screen.findByTestId('command-palette')
    await waitFor(() => expect(shellApi.fileList).toHaveBeenCalled())
    search('Inventory')
    await screen.findByText('Inventory.xml')
    fireEvent.keyDown(screen.getByTestId('command-input'), { key: 'Enter' })
    await waitFor(() => expect(actions.openXml).toHaveBeenCalledWith('C:\\ui\\Inventory.xml'))
  })
})

describe('ver código XML', () => {
  it('Ctrl+U alterna o painel e a seleção marca a linha do elemento', async () => {
    render(<SourcePanel />)
    press('u')
    await waitFor(() => expect(document.querySelector('.cm-content')?.textContent).toContain('WindowID="1"'))
    act(() => mock.select([0]))
    await waitFor(() => expect(document.querySelector('.gf-source-marked')?.textContent).toContain('WindowID="1"'))
    expect(screen.getByText(/com alterações não salvas/)).toBeTruthy()
    press('u')
    await waitFor(() => expect(screen.queryByTestId('source-panel')).toBeNull())
  })
})
