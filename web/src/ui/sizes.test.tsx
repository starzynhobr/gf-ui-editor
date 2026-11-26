// Tamanhos animados (NumberFlow): leitura do texto do Python, frase com o número no meio, o
// Limpar (botão e "Depois de limpar" mudam ao escolher a opção).
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// O NumberFlow é um custom element que o jsdom não roda: mostra o valor direto.
vi.mock('@number-flow/react', () => ({
  default: ({ value, suffix }: { value: number; suffix?: string }) => <span data-flow>{value}{suffix}</span>,
}))
import { AnimatedSize, parseSize, sizeParts, withNodes } from './AnimatedSize'
import { openCleanupDialog, sizeAfter } from '../project/CleanupDialog'
import type { CleanupScan } from '../project/toolsApi'
import { DialogHost, resetDialogs } from './dialogs'
import { setLanguage } from '../i18n'

const MB = 1024 ** 2
const plan: CleanupScan = {
  name: 'Meu', days: 30, total: '340 MB', total_bytes: 340 * MB, ui: '200 MB', history: '120 MB', versions: '20 MB',
  history_old: { count: 3, size: 40 * MB }, history_all: { count: 9, size: 110 * MB },
  icons: { count: 2, size: 30 * MB, left: 0 }, maps: { count: 0, size: 0, left: 0 },
  custom: { count: 4, size: 50 * MB, folder: 'Meu' },
} as CleanupScan

beforeEach(() => setLanguage('pt_BR'))
afterEach(() => {
  cleanup()
  resetDialogs()
})

describe('AnimatedSize', () => {
  it('lê os formatos do human_size', () => {
    expect(parseSize('340 MB')).toEqual({ value: 340, unit: 'MB', decimals: 0 })
    expect(parseSize('1.2 GB')).toEqual({ value: 1.2, unit: 'GB', decimals: 1 })
    expect(parseSize('…')).toBeNull()
    expect(sizeParts(110 * MB)).toEqual({ value: 110, unit: 'MB', decimals: 0 })
  })

  it('texto que não é tamanho fica como está; o tamanho guarda o texto final', () => {
    render(<><AnimatedSize value="—" testId="a" /><AnimatedSize value={2 * MB} countUp testId="b" /></>)
    expect(screen.getByTestId('a').textContent).toBe('—')
    expect(screen.getByTestId('b').dataset.size).toBe('2 MB')
  })

  it('withNodes põe o nó no lugar do {nome}', () => {
    render(<p data-testid="p">{withNodes('Limpar ({size}) agora', { size: <b>9</b> })}</p>)
    expect(screen.getByTestId('p').innerHTML).toBe('Limpar (<b>9</b>) agora')
  })
})

describe('Limpar', () => {
  it('o botão e o "Depois de limpar" acompanham a escolha (a cópia no jogo não conta no total)', async () => {
    expect(sizeAfter(plan, { history: 'all', icons: true, maps: false, custom: true })).toBe(200 * MB)
    expect(sizeAfter({ ...plan, total_bytes: undefined }, { history: null, icons: false, maps: false, custom: false })).toBeNull()
    render(<DialogHost />)
    act(() => void openCleanupDialog(plan))
    await screen.findByTestId('cleanup-dialog')
    expect(screen.getByTestId('cleanup-total').dataset.size).toBe('340 MB')
    expect(screen.getByTestId('cleanup-size').dataset.size).toBe('1 KB')
    expect(screen.getByTestId('cleanup-after').getAttribute('aria-hidden')).toBe('true')
    fireEvent.click(screen.getByText(/Apagar todos os backups/))
    await waitFor(() => expect(screen.getByTestId('cleanup-size').dataset.size).toBe('110 MB'))
    expect(screen.getByTestId('cleanup-after-size').dataset.size).toBe('230 MB')
    expect(screen.getByTestId('cleanup-after').getAttribute('aria-hidden')).toBe('false')
    fireEvent.click(screen.getByText(/Cópia no jogo/))
    await waitFor(() => expect(screen.getByTestId('cleanup-size').dataset.size).toBe('160 MB'))
    expect(screen.getByTestId('cleanup-after-size').dataset.size).toBe('230 MB')
  })
})
