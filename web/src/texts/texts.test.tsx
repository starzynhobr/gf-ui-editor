// Tela de Textos sem janela: a ponte (textsApi) é falsa e guarda o que foi pedido.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ImportPlan, OpenText, TextResults } from './textsApi'

const rows: TextResults = {
  rows: [
    { name: 'T_Item.ini', id: '539', fields: ['Runa Nova', 'Uma runa.'], state: 'edited', game_fields: ['Runa', 'Uma runa.'], original: [] },
    { name: 'T_Item.ini', id: '540', fields: ['Pedra Nova', 'x'], state: 'updated', game_fields: ['Pedra Antiga', 'x'], original: ['Pedra', 'x'] },
    { name: 'T_Npc.ini', id: '7', fields: ['Guarda\nda vila'], state: 'changed', game_fields: ['Guarda\nda vila'], original: [] },
    { name: 'T_Npc.ini', id: '8', fields: ['Ferreiro'], state: '', game_fields: ['Ferreiro'], original: [] },
  ],
  total: 4,
  summary: 'count',
  values: { total: 4 },
  updates: 1,
  limit: 500,
}

const record: OpenText = {
  name: 'T_Item.ini',
  id: '539',
  fields: ['Runa Nova', 'Uma runa.'],
  original: ['Runa', 'Uma runa.'],
  can_restore: true,
  encoding: 'cp1252',
  newline: '\r\n',
}

const plan: ImportPlan = { count: 2, missing_ids: 1, unsupported: 0, unknown_files: [], replaced: 0, per_file: [['T_Item.ini', 2]], folder: 'C:\\old' }

const fake = vi.hoisted(() => ({
  search: vi.fn(),
  open: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  state: vi.fn(),
  pickImport: vi.fn(),
  planImport: vi.fn(),
  applyImport: vi.fn(),
  reload: vi.fn(),
}))

vi.mock('./textsApi', async (original) => ({ ...(await original<typeof import('./textsApi')>()), textsApi: fake }))
vi.mock('../actions', () => ({ refreshShell: vi.fn(async () => ({})) }))

const { default: TextsPage } = await import('./TextsPage')
const { DialogHost, resetDialogs } = await import('../ui/dialogs')
const { useShell } = await import('../store')

// jsdom não mede layout: a lista virtualizada precisa de uma altura para desenhar as linhas.
Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 600 })
Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 400 })

beforeEach(() => {
  resetDialogs()
  Object.values(fake).forEach((fn) => fn.mockReset())
  fake.search.mockResolvedValue(rows)
  fake.state.mockResolvedValue({ available: true, can_import: true, index_ready: false })
  fake.open.mockResolvedValue(record)
  fake.save.mockResolvedValue({ saved: true })
  fake.restore.mockResolvedValue({ saved: true })
  fake.pickImport.mockResolvedValue('C:\\old')
  fake.planImport.mockResolvedValue(plan)
  fake.applyImport.mockResolvedValue(2)
  useShell.setState({
    shell: { project: { root: 'C:\\p', name: 'P', custom_name: 'P', ui_dir: 'C:\\p\\ui', game_dir: 'C:\\game', publish_dir: null } } as never,
  })
})
afterEach(() => cleanup())

const page = () =>
  render(
    <>
      <TextsPage />
      <DialogHost />
    </>,
  )

describe('tela de Textos', () => {
  it('sem pasta do jogo mostra o estado vazio em vez da lista', async () => {
    fake.search.mockResolvedValue({ ...rows, rows: [], summary: 'no_game', values: {}, updates: 0 })
    useShell.setState({ shell: { project: { root: 'C:\\p', name: 'P', custom_name: 'P', ui_dir: 'C:\\p\\ui', game_dir: null, publish_dir: null } } as never })
    page()
    const empty = await screen.findByTestId('texts-empty')
    expect(empty.textContent).toContain('Defina a pasta do jogo no projeto para ver os textos.')
    expect(screen.queryByTestId('texts-summary')).toBeNull()
    expect(screen.queryByText('Arquivo')).toBeNull()
  })

  it('mostra os marcadores, os tooltips e o resumo como a clássica', async () => {
    page()
    await waitFor(() => expect(screen.getAllByTestId('text-row')).toHaveLength(4))
    const texts = screen.getAllByTestId('text-row').map((row) => row.textContent)
    expect(texts[0]).toContain('● Runa Nova | Uma runa.')
    expect(texts[1]).toContain('⚠ Pedra Nova | x')
    expect(texts[2]).toContain('◐ Guarda ⏎ da vila')
    expect(texts[3]?.startsWith('Ferreiro')).toBe(true)
    const tip = screen.getAllByTestId('text-row')[1].getAttribute('title')!
    expect(tip).toContain('Original quando você editou: Pedra | x')
    expect(tip).toContain('No jogo agora: Pedra Antiga | x')
    expect(screen.getByTestId('texts-summary').textContent).toBe(
      '4 resultado(s). ⚠ 1 mudou(aram) no jogo depois da edição: confira antes de enviar.',
    )
  })

  it('busca depois de 200 ms e com "Só editados"', async () => {
    page()
    await waitFor(() => expect(fake.search).toHaveBeenCalled())
    fake.search.mockClear()
    fireEvent.change(screen.getByPlaceholderText('Buscar em todos os textos do jogo…'), { target: { value: 'runa' } })
    expect(fake.search).not.toHaveBeenCalledWith('runa', false)
    await waitFor(() => expect(fake.search).toHaveBeenCalledWith('runa', false), { timeout: 1000 })
    fireEvent.click(screen.getByLabelText('Só editados'))
    await waitFor(() => expect(fake.search).toHaveBeenCalledWith('runa', true))
  })

  it('abre o editor com uma caixa por coluna e grava', async () => {
    const changed = vi.fn()
    window.addEventListener('gf:text-edits-changed', changed)
    page()
    await waitFor(() => screen.getAllByTestId('text-row'))
    fireEvent.click(screen.getAllByTestId('text-row')[0])
    await waitFor(() => screen.getByTestId('text-editor'))
    expect(screen.getByText('T_Item.ini · ID 539')).toBeTruthy()
    expect(screen.getByText('Coluna 1')).toBeTruthy()
    expect(screen.getByText('O jogo usa "|" para separar as colunas, então ele não pode aparecer no texto.')).toBeTruthy()
    fireEvent.change(document.querySelector('textarea[name=text-column-0]')!, { target: { value: 'Runa Brilhante' } })
    fireEvent.click(screen.getByTestId('text-save'))
    await waitFor(() => expect(fake.save).toHaveBeenCalledWith('T_Item.ini', '539', ['Runa Brilhante', 'Uma runa.']))
    await waitFor(() => expect(changed).toHaveBeenCalled())
    expect(screen.queryByTestId('text-editor')).toBeNull()
    window.removeEventListener('gf:text-edits-changed', changed)
  })

  it('recusa o "|" e volta ao original pelo botão', async () => {
    fake.save.mockResolvedValueOnce({ error: 'pipe', encoding: 'cp1252' })
    page()
    await waitFor(() => screen.getAllByTestId('text-row'))
    fireEvent.click(screen.getAllByTestId('text-row')[0])
    await waitFor(() => screen.getByTestId('text-editor'))
    fireEvent.click(screen.getByTestId('text-save'))
    await waitFor(() => screen.getByText('Tire o "|" do texto: o jogo o usa para separar colunas.'))
    fireEvent.click(screen.getByText('OK'))
    expect(screen.getByTestId('text-editor')).toBeTruthy() // continua aberto
    const restore = screen.getByText('Voltar ao texto original')
    expect(restore.getAttribute('title')).toBe('Runa | Uma runa.')
    fireEvent.click(restore)
    await waitFor(() => expect(fake.restore).toHaveBeenCalledWith('T_Item.ini', '539'))
  })

  it('sem original diferente não oferece "Voltar ao texto original"', async () => {
    fake.open.mockResolvedValueOnce({ ...record, original: null, can_restore: false, fields: ['Ferreiro'] })
    page()
    await waitFor(() => screen.getAllByTestId('text-row'))
    fireEvent.click(screen.getAllByTestId('text-row')[3])
    await waitFor(() => screen.getByTestId('text-editor'))
    expect(screen.queryByText('Voltar ao texto original')).toBeNull()
    expect(screen.queryByText('Coluna 1')).toBeNull() // uma coluna só: sem rótulo
  })

  it('importa depois de confirmar, com o resumo por arquivo', async () => {
    page()
    await waitFor(() => screen.getAllByTestId('text-row'))
    const button = screen.getByText('Importar textos…')
    expect(button.getAttribute('title')).toContain('Compara ID por ID com o jogo')
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(button)
    await waitFor(() => screen.getByText(/2 texto\(s\) diferentes do jogo/))
    expect(screen.getByRole('dialog').textContent).toContain('T_Item.ini: 2')
    expect(screen.getByRole('dialog').textContent).toContain('1 ID(s) não existem mais no jogo e foram ignorados.')
    fireEvent.click(screen.getByText('Sim'))
    await waitFor(() => expect(fake.applyImport).toHaveBeenCalled())
  })

  it('importação sem diferenças só avisa', async () => {
    fake.planImport.mockResolvedValueOnce({ ...plan, count: 0, missing_ids: 0, per_file: [] })
    page()
    await waitFor(() => screen.getAllByTestId('text-row'))
    await waitFor(() => expect((screen.getByText('Importar textos…') as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByText('Importar textos…'))
    await waitFor(() => screen.getByText(/Nenhum texto diferente do jogo foi encontrado em C:\\old/))
    expect(fake.applyImport).not.toHaveBeenCalled()
  })
})
