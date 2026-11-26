// Árvore, painel, salvar/descartar e atalhos contra um store de documento falso (o contrato
// de doc/store.ts implementado em memória em test/mockStore.ts).
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as mock from '../test/mockStore'

vi.mock('../doc/store', () => import('../test/mockStore'))

const shellState = {
  version: '0.0.0',
  language: 'pt_BR',
  ui_mode: 'web',
  project: { root: 'C:\\p', name: 'P', custom_name: 'P', ui_dir: 'C:\\p\\ui', game_dir: null, publish_dir: null },
  open_path: 'C:\\p\\ui\\Panel.xml',
  loose_dir: null,
  pending: 0,
  publish_confirmed: true,
  publish_on_save: false,
}

vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      elementTree: vi.fn(async (_path: string, kinds: string[]) =>
        kinds.map((kind, index) => ({
          index,
          label: index === 2 ? 'Fechar' : '',
          text: index === 2 ? 'Fechar' : '',
          search: `${index} ${kind} ${index === 3 ? 'other.dds' : 'panel.dds'} ${index === 2 ? 'fechar' : ''}`.toLowerCase(),
        })),
      ),
      treeColumns: vi.fn(async () => ['2']),
      setTreeColumns: vi.fn(async (hidden: string[]) => hidden),
      setUnsaved: vi.fn(async () => undefined),
      shellState: vi.fn(async () => shellState),
      textureCopyInfo: vi.fn(async () => ({ exists: true, suggestion: 'Panel_custom.dds' })),
    },
  }
})

const { default: ElementTree } = await import('./ElementTree')
const { default: PropertiesPanel } = await import('./PropertiesPanel')
const { DialogHost } = await import('../ui/dialogs')
const { MenuHost } = await import('../ui/Menu')
const { saveDocument, confirmDiscard } = await import('../shell/saving')
const { installShortcuts } = await import('../shell/shortcuts')
const { useShell } = await import('../store')

beforeEach(() => {
  mock.resetMock()
  mock.loadMockDocument(shellState.open_path, mock.sampleDocument())
  useShell.setState({ shell: shellState as never, view: 'workspace', page: 'elements' })
})
afterEach(() => cleanup())

const rows = () => screen.getAllByTestId('tree-row')

describe('árvore de elementos', () => {
  it('mostra a hierarquia como a clássica, com o texto do jogo no Tipo', async () => {
    render(<ElementTree />)
    await waitFor(() => expect(screen.getByText('Botão · Fechar')).toBeTruthy())
    expect(rows().map((row) => row.dataset.index)).toEqual(['0', '1', '2', '3'])
    // recuo pela profundidade: botão (11) é filho do painel (10), que é filho da janela (1)
    const indent = (index: number) => (rows()[index].querySelector('[style*="padding-left"]') as HTMLElement).style.paddingLeft
    expect([indent(0), indent(1), indent(2), indent(3)]).toEqual(['0px', '14px', '28px', '14px'])
  })

  it('seleciona com clique, Ctrl e Shift', async () => {
    render(<ElementTree />)
    fireEvent.click(rows()[1])
    expect(mock.useDoc.getState().selection).toEqual([1])
    fireEvent.click(rows()[3], { shiftKey: true })
    expect(mock.useDoc.getState().selection).toEqual([3, 1, 2]) // o clicado vira o principal
    fireEvent.click(rows()[2], { ctrlKey: true })
    expect(mock.useDoc.getState().selection).toEqual([3, 1])
    fireEvent.click(rows()[0])
    expect(mock.useDoc.getState().selection).toEqual([0])
  })

  it('filtra pelo texto da clássica e mantém os pais de quem bate', async () => {
    render(<ElementTree />)
    await waitFor(() => expect(screen.getByText('Botão · Fechar')).toBeTruthy())
    fireEvent.change(screen.getByPlaceholderText('Pesquisar WindowID, tipo, texto ou textura…'), { target: { value: 'fechar' } })
    expect(rows().map((row) => row.dataset.index)).toEqual(['0', '1', '2'])
    fireEvent.change(screen.getByPlaceholderText('Pesquisar WindowID, tipo, texto ou textura…'), { target: { value: 'other.dds' } })
    expect(rows().map((row) => row.dataset.index)).toEqual(['0', '3'])
  })

  it('oculta, trava e isola pelos ícones sem mudar a seleção', () => {
    render(<ElementTree />)
    const row = rows()[2]
    fireEvent.click(row.querySelector('[data-state=hidden]')!)
    fireEvent.click(row.querySelector('[data-state=locked]')!)
    fireEvent.click(row.querySelector('[data-state=isolated]')!)
    const state = mock.useDoc.getState()
    expect([state.hidden, state.locked, state.isolated, state.selection]).toEqual([[2], [2], 2, []])
    fireEvent.click(rows()[2].querySelector('[data-state=isolated]')!)
    expect(mock.useDoc.getState().isolated).toBe(null)
  })

  it('mostra e esconde as colunas WindowID e ParentNode pelo cabeçalho', async () => {
    render(
      <>
        <ElementTree />
        <MenuHost />
      </>,
    )
    expect(within(screen.getByTestId('tree-header')).queryByText('ParentNode')).toBeNull()
    fireEvent.contextMenu(screen.getByTestId('tree-header'))
    fireEvent.click(within(screen.getByRole('menu')).getByText('ParentNode'))
    expect(within(screen.getByTestId('tree-header')).getByText('ParentNode')).toBeTruthy()
  })

  it('acompanha a seleção feita no canvas', () => {
    render(<ElementTree />)
    act(() => mock.select([2]))
    expect(rows()[2].getAttribute('aria-selected')).toBe('true')
  })
})

describe('painel de propriedades', () => {
  it('sem seleção mostra "Nenhum elemento selecionado"', () => {
    render(<PropertiesPanel />)
    expect(screen.getByText('Nenhum elemento selecionado')).toBeTruthy()
  })

  it('edita X com Enter e Y com a seta como um passo de desfazer cada', async () => {
    act(() => mock.select([1]))
    render(<PropertiesPanel />)
    const field = document.querySelector('input[name=geometry-x]') as HTMLInputElement
    expect(field.value).toBe('10')
    fireEvent.change(field, { target: { value: '42' } })
    fireEvent.keyDown(field, { key: 'Enter' })
    await waitFor(() => expect(mock.calls.applyEdits).toHaveBeenCalledTimes(1))
    expect(mock.calls.applyEdits.mock.calls[0][0]).toEqual([{ index: 1, field: 'geometry', before: [10, 5, 100, 20], after: [42, 5, 100, 20] }])
    const y = document.querySelector('input[name=geometry-y]') as HTMLInputElement
    fireEvent.keyDown(y, { key: 'ArrowUp', shiftKey: true })
    await waitFor(() => expect(mock.calls.applyEdits).toHaveBeenCalledTimes(2))
    expect(mock.calls.applyEdits.mock.calls[1][0][0].after).toEqual([42, 15, 100, 20])
    expect(mock.useDoc.getState().canUndo).toBe(true)
  })

  it('a roda do mouse não muda o campo', () => {
    act(() => mock.select([1]))
    render(<PropertiesPanel />)
    const field = document.querySelector('input[name=geometry-x]') as HTMLInputElement
    fireEvent.wheel(field, { deltaY: -100 })
    expect(field.value).toBe('10')
    expect(mock.calls.applyEdits).not.toHaveBeenCalled()
  })

  it('mostra só os campos de fonte que o controle tem e grava a cor em BGR', async () => {
    act(() => mock.select([2]))
    render(<PropertiesPanel />)
    expect(screen.getByText('Cor do texto')).toBeTruthy()
    expect(screen.getByText('Contorno')).toBeTruthy()
    expect(screen.getByText('Alinhamento')).toBeTruthy()
    expect(screen.queryByText('Tamanho')).toBeNull()
    expect(screen.getByText('#FFFF00')).toBeTruthy() // 65535 = amarelo
    const color = document.querySelector('input[name=font-color]') as HTMLInputElement
    color.value = '#ff0000'
    color.dispatchEvent(new Event('change'))
    await waitFor(() => expect(mock.calls.applyEdits).toHaveBeenCalled())
    expect(mock.calls.applyEdits.mock.calls[0][0]).toEqual([{ index: 2, field: 'font', name: 'FontColor', before: '65535', after: '255' }])
  })

  it('um controle sem texto mostra "Sem texto próprio"; travado não edita', () => {
    act(() => {
      mock.select([1])
      mock.setLocked([1], true)
    })
    render(<PropertiesPanel />)
    expect(screen.getByText('Sem texto próprio')).toBeTruthy()
    expect((document.querySelector('input[name=geometry-x]') as HTMLInputElement).disabled).toBe(true)
  })
})

describe('salvar e descartar', () => {
  it('Ctrl+S mostra o diff e só grava depois de confirmar', async () => {
    await mock.applyEdits([{ index: 1, field: 'geometry', before: [10, 5, 100, 20], after: [11, 5, 100, 20] }], 'x')
    render(<DialogHost />)
    const uninstall = installShortcuts()
    fireEvent.keyDown(window, { key: 's', ctrlKey: true })
    await waitFor(() => expect(screen.getByTestId('diff').textContent).toContain('+new'))
    expect(mock.calls.save).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('diff-confirm'))
    await waitFor(() => expect(mock.calls.save).toHaveBeenCalledTimes(1))
    expect(mock.useDoc.getState().dirty).toBe(false)
    uninstall()
  })

  it('cancelar o diff não grava', async () => {
    await mock.applyEdits([{ index: 1, field: 'geometry', before: [10, 5, 100, 20], after: [11, 5, 100, 20] }], 'x')
    render(<DialogHost />)
    const saving = saveDocument()
    await waitFor(() => screen.getByTestId('diff'))
    fireEvent.click(screen.getByText('Cancelar'))
    expect(await saving).toBe(false)
    expect(mock.calls.save).not.toHaveBeenCalled()
  })

  it('Descartar alterações? com Cancelar, Descartar e Salvar', async () => {
    render(<DialogHost />)
    expect(await confirmDiscard()).toBe(true) // sem alterações, não pergunta
    await mock.applyEdits([{ index: 1, field: 'geometry', before: [10, 5, 100, 20], after: [11, 5, 100, 20] }], 'x')
    let answer = confirmDiscard()
    fireEvent.click(await screen.findByText('Cancelar'))
    expect(await answer).toBe(false)
    answer = confirmDiscard()
    fireEvent.click(await screen.findByText('Descartar'))
    expect(await answer).toBe(true)
    expect(mock.calls.revert).toHaveBeenCalled()
    await mock.applyEdits([{ index: 1, field: 'geometry', before: [10, 5, 100, 20], after: [12, 5, 100, 20] }], 'x')
    answer = confirmDiscard()
    fireEvent.click(await screen.findByText('Salvar'))
    fireEvent.click(await screen.findByTestId('diff-confirm'))
    expect(await answer).toBe(true)
    expect(mock.calls.save).toHaveBeenCalled()
  })

  it('Ctrl+Z desfaz e Ctrl+Y / Ctrl+Shift+Z refazem', async () => {
    await mock.applyEdits([{ index: 1, field: 'geometry', before: [10, 5, 100, 20], after: [11, 5, 100, 20] }], 'x')
    const uninstall = installShortcuts()
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    await waitFor(() => expect(mock.useDoc.getState().doc!.elements[1].geometry[0]).toBe(10))
    fireEvent.keyDown(window, { key: 'y', ctrlKey: true })
    await waitFor(() => expect(mock.useDoc.getState().doc!.elements[1].geometry[0]).toBe(11))
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    await waitFor(() => expect(mock.useDoc.getState().canRedo).toBe(true))
    fireEvent.keyDown(window, { key: 'Z', ctrlKey: true, shiftKey: true })
    await waitFor(() => expect(mock.useDoc.getState().doc!.elements[1].geometry[0]).toBe(11))
    uninstall()
  })
})
