// Novidades depois de atualizar: abertura automática, clicar fora não fecha, a pílula "Novidades ×"
// da barra (reabrir e dispensar), o voo (com e sem "reduzir movimento"), os toasts segurados e o
// "Voltar para a clássica" do cartão da interface nova. A ponte whats_new_* é falsa.
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReleaseNote } from '../api'

const shellApi = vi.hoisted(() => ({
  whatsNew: vi.fn(),
  whatsNewState: vi.fn(),
  whatsNewClosed: vi.fn(),
  whatsNewPillDismissed: vi.fn(),
  shellState: vi.fn(),
}))
const settings = vi.hoisted(() => ({ set: vi.fn() }))
const saving = vi.hoisted(() => ({ closeRequested: vi.fn() }))
const sonner = vi.hoisted(() => ({ toast: vi.fn() }))

vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return { ...actual, api: { ...actual.api, ...shellApi } }
})
vi.mock('../bridge', async (original) => ({
  ...(await original<typeof import('../bridge')>()),
  call: vi.fn(async (name: string) => (name === 'release_history' ? { releases: [] } : undefined)),
}))
vi.mock('../settings/settingsApi', async (original) => ({
  ...(await original<typeof import('../settings/settingsApi')>()),
  settingsApi: settings,
}))
vi.mock('../shell/saving', async (original) => ({ ...(await original<typeof import('../shell/saving')>()), ...saving }))
vi.mock('sonner', async (original) => ({ ...(await original<typeof import('sonner')>()), toast: sonner.toast }))

const { startWhatsNew, openWhatsNew } = await import('./WhatsNewDialog')
const { useWhatsNew, resetWhatsNew } = await import('./whatsNew')
const { flyIn, flyOut } = await import('./flight')
const { default: WhatsNewPill } = await import('../shell/WhatsNewPill')
const { ReleaseNotes } = await import('../settings/ReleaseNotes')
const { DialogHost, resetDialogs } = await import('../ui/dialogs')
const { showStatus, useShell } = await import('../store')
const { setLanguage } = await import('../i18n')

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
Element.prototype.scrollTo ??= () => undefined

const item = (title: string): [string, string] => [title, `Descrição de ${title}`]
const notes: ReleaseNote = {
  version: '0.8.0',
  date: '2026-11-26',
  spotlight: 'new_interface',
  sections: { new: ['Tela inicial.', 'Temas.', 'Atalhos.', 'Zoom.', 'Projetos.'].map(item), improved: [item('Envio.')], fixed: [] },
}

function Shell() {
  return (
    <>
      <header>
        <div data-topbar-spacer />
        <WhatsNewPill />
      </header>
      <DialogHost />
    </>
  )
}

function setReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes('reduce'),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    onchange: null,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

beforeEach(() => {
  setLanguage('pt_BR')
  resetDialogs()
  resetWhatsNew()
  setReducedMotion(false)
  for (const fn of [...Object.values(shellApi), settings.set, saving.closeRequested, sonner.toast]) fn.mockReset()
  shellApi.whatsNew.mockResolvedValue(notes)
  shellApi.whatsNewState.mockResolvedValue({ version: '0.8.0', auto_open: true, pill: false })
  shellApi.whatsNewClosed.mockResolvedValue(undefined)
  shellApi.whatsNewPillDismissed.mockResolvedValue(undefined)
  shellApi.shellState.mockResolvedValue({ version: '0.8.0', language: 'pt_BR', ui_mode: 'classic', project: null, open_path: null, loose_dir: null, pending: 0, publish_confirmed: true, publish_on_save: false })
  settings.set.mockResolvedValue({})
  saving.closeRequested.mockResolvedValue(undefined)
  useShell.setState({ shell: { version: '0.8.0', language: 'pt_BR', ui_mode: 'web', project: null, open_path: null, loose_dir: null, pending: 0, publish_confirmed: true, publish_on_save: false } })
})
afterEach(cleanup)

async function autoOpen() {
  render(<Shell />)
  let started!: Promise<boolean>
  act(() => {
    started = startWhatsNew()
  })
  await screen.findByTestId('whats-new')
  return { started }
}

const closeButton = () => screen.getByTestId('whats-new-close')

describe('Novidades depois de atualizar', () => {
  it('abrem sozinhas com auto_open e seguram os outros avisos', async () => {
    const { started } = await autoOpen()
    expect(screen.getByTestId('whats-new').dataset.mode).toBe('auto')
    expect(useWhatsNew.getState().hold).toBe(true)
    expect(screen.getByTestId('notes-spotlight').textContent).toContain('Interface nova')
    fireEvent.click(closeButton())
    await expect(started).resolves.toBe(true)
    expect(useWhatsNew.getState().hold).toBe(false)
  })

  it('sem auto_open não abrem; com pill a pílula já vem na barra', async () => {
    shellApi.whatsNewState.mockResolvedValue({ version: '0.8.0', auto_open: false, pill: true })
    render(<Shell />)
    let shown: boolean | undefined
    await act(async () => {
      shown = await startWhatsNew()
    })
    expect(shown).toBe(false)
    expect(screen.queryByTestId('whats-new')).toBeNull()
    expect(screen.getByTestId('whats-new-pill')).toBeTruthy()
  })

  it('clicar fora não fecha', async () => {
    await autoOpen()
    const overlay = screen.getByRole('dialog').parentElement as HTMLElement
    fireEvent.mouseDown(overlay)
    fireEvent.click(overlay)
    fireEvent.mouseDown(document.body)
    await act(async () => undefined)
    expect(screen.getByTestId('whats-new')).toBeTruthy()
    expect(shellApi.whatsNewClosed).not.toHaveBeenCalled()
  })

  it('Esc também fecha (e vira a pílula)', async () => {
    const { started } = await autoOpen()
    fireEvent.keyDown(window, { key: 'Escape' })
    await expect(started).resolves.toBe(true)
    expect(shellApi.whatsNewClosed).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('whats-new-pill')).toBeTruthy()
  })

  it('fechar mostra a pílula e chama whats_new_closed', async () => {
    const { started } = await autoOpen()
    expect(screen.queryByTestId('whats-new-pill')).toBeNull()
    fireEvent.click(screen.getAllByRole('button', { name: 'Fechar' }).find((button) => button.getAttribute('aria-label') === 'Fechar')!) // o X
    await started
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(shellApi.whatsNewClosed).toHaveBeenCalledTimes(1)
    const pill = screen.getByTestId('whats-new-pill')
    expect(pill.dataset.covered).toBeUndefined()
    expect(pill.textContent).toContain('Novidades')
  })

  it('a pílula reabre as notas e, ao fechar, elas voltam para ela', async () => {
    const { started } = await autoOpen()
    fireEvent.click(closeButton())
    await started
    fireEvent.click(screen.getByTestId('whats-new-pill-open'))
    await screen.findByTestId('whats-new')
    expect(screen.getByTestId('whats-new').dataset.mode).toBe('pill')
    expect(screen.getByTestId('whats-new-pill').dataset.covered).toBe('true') // o diálogo "é" a pílula
    fireEvent.click(closeButton())
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), { timeout: 3000 })
    expect(shellApi.whatsNewClosed).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('whats-new-pill').dataset.covered).toBeUndefined()
  })

  it('o × chama whats_new_pill_dismissed e a pílula some', async () => {
    const { started } = await autoOpen()
    fireEvent.click(closeButton())
    await started
    fireEvent.click(screen.getByTestId('whats-new-pill-dismiss'))
    expect(shellApi.whatsNewPillDismissed).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByTestId('whats-new-pill')).toBeNull())
    expect(useWhatsNew.getState().pill).toBe(false)
    // Pela engrenagem/Ctrl+K continuam abrindo, e fecham sem pílula.
    act(() => openWhatsNew())
    await screen.findByTestId('whats-new')
    expect(screen.getByTestId('whats-new').dataset.mode).toBe('manual')
    fireEvent.click(closeButton())
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByTestId('whats-new-pill')).toBeNull()
    expect(shellApi.whatsNewClosed).toHaveBeenCalledTimes(1)
  })

  it('toasts esperam as notas fecharem', async () => {
    const { started } = await autoOpen()
    act(() => showStatus('Publicado: 1 arquivo.', 10))
    expect(sonner.toast).not.toHaveBeenCalled()
    fireEvent.click(closeButton())
    await started
    expect(sonner.toast).toHaveBeenCalledWith('Publicado: 1 arquivo.', expect.anything())
  })

  it('Voltar para a clássica: grava a interface e oferece reiniciar (com Salvar/Descartar)', async () => {
    await autoOpen()
    fireEvent.click(screen.getByTestId('back-to-classic'))
    await waitFor(() => expect(settings.set).toHaveBeenCalledWith('ui_mode', 'classic'))
    const restart = await screen.findByRole('button', { name: 'Reiniciar agora' })
    expect(screen.getByText('Reiniciar agora para usar a interface Clássica?')).toBeTruthy()
    fireEvent.click(restart)
    await waitFor(() => expect(saving.closeRequested).toHaveBeenCalledWith(true))
    expect(shellApi.whatsNewClosed).toHaveBeenCalled() // a versão conta como vista antes de reiniciar
  })

  it('"Depois" mantém as notas abertas', async () => {
    await autoOpen()
    fireEvent.click(screen.getByTestId('back-to-classic'))
    fireEvent.click(await screen.findByRole('button', { name: 'Depois' }))
    await act(async () => undefined)
    expect(saving.closeRequested).not.toHaveBeenCalled()
    expect(screen.getByTestId('whats-new')).toBeTruthy()
  })
})

describe('cartão da interface nova', () => {
  it('só aparece na nota com spotlight e o botão só onde há como voltar', () => {
    const { rerender } = render(<ReleaseNotes releases={[{ ...notes, spotlight: undefined }]} />)
    expect(screen.queryByTestId('notes-spotlight')).toBeNull()
    rerender(<ReleaseNotes releases={[notes]} />) // ex.: atualizador, antes de instalar
    expect(screen.getByTestId('notes-spotlight')).toBeTruthy()
    expect(screen.queryByTestId('back-to-classic')).toBeNull()
    rerender(<ReleaseNotes releases={[notes]} onBackToClassic={() => undefined} />)
    expect(screen.getByTestId('back-to-classic').textContent).toBe('Voltar para a clássica')
    expect(screen.getByTestId('notes-back-classic').textContent).toContain('Configurações → Interface')
    // Acima dos outros destaques.
    const spotlight = screen.getByTestId('notes-spotlight')
    expect(spotlight.compareDocumentPosition(screen.getByTestId('notes-highlights')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('voo até a pílula', () => {
  function boxes() {
    const overlay = document.createElement('div')
    const box = document.createElement('div')
    box.appendChild(document.createElement('div'))
    overlay.appendChild(box)
    document.body.appendChild(overlay)
    box.getBoundingClientRect = () => new DOMRect(400, 200, 640, 480)
    return { overlay, box }
  }
  const pill = new DOMRect(900, 6, 120, 32)

  it('encolhe até o retângulo da pílula (translação + escala)', async () => {
    const { overlay, box } = boxes()
    const landed = vi.fn()
    await flyOut(box, overlay, pill, landed)
    expect(landed).toHaveBeenCalled()
    expect(box.style.transform).toMatch(/scale/)
    expect(Number(box.style.opacity)).toBe(0)
    overlay.remove()
  })

  it('reabrir nasce do tamanho da pílula, sem um quadro no tamanho final', async () => {
    const { overlay, box } = boxes()
    const done = flyIn(box, overlay, pill)
    expect(box.style.transform).toMatch(/scale\(0\.1875, 0\.0666/) // 120/640 e 32/480
    expect(box.style.opacity).toBe('0')
    await done
    expect(Number(box.style.opacity)).toBe(1)
    overlay.remove()
  })

  it('com "reduzir movimento": só um fade, sem escala', async () => {
    setReducedMotion(true)
    const { overlay, box } = boxes()
    await flyOut(box, overlay, pill)
    expect(box.style.transform).not.toMatch(/scale|translate/)
    expect(Number(box.style.opacity)).toBe(0)
    overlay.remove()
  })

  it('com "reduzir movimento" a abertura automática continua virando pílula', async () => {
    setReducedMotion(true)
    const { started } = await autoOpen()
    fireEvent.click(closeButton())
    await started
    expect(screen.getByTestId('whats-new-pill')).toBeTruthy()
  })
})
