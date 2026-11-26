// "Como usar" (F1) e os estados vazios dos painéis, sem janela: a ponte é falsa.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const bridge = vi.hoisted(() => ({
  call: vi.fn(async (name: string) => (name === 'about_info' ? { how_to_url: 'https://stzlabs.com/pt/projects/gf-ui-editor' } : undefined)),
}))
const shellApi = vi.hoisted(() => ({
  openUrl: vi.fn(),
  homeData: vi.fn(async () => ({ projects: [] })),
  fileList: vi.fn(async () => ({ directory: null, files: [] })),
}))

vi.mock('../bridge', async (original) => ({ ...(await original<typeof import('../bridge')>()), call: bridge.call }))
vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return { ...actual, api: { ...actual.api, ...shellApi } }
})
vi.mock('../doc/store', async () => await import('../test/mockStore'))

const { howToShortcuts, howToSteps } = await import('./HowToDialog')
const { DialogHost, resetDialogs } = await import('../ui/dialogs')
const { installShortcuts } = await import('../shell/shortcuts')
const { default: SideRail } = await import('../shell/SideRail')
const { MenuHost } = await import('../ui/Menu')
const { default: CommandPalette, usePalette } = await import('../palette/CommandPalette')
const { default: ElementTree } = await import('../elements/ElementTree')
const { useShell } = await import('../store')
const { setLanguage } = await import('../i18n')

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= () => undefined

let uninstall: () => void = () => undefined

beforeEach(() => {
  setLanguage('pt_BR')
  useShell.setState({ view: 'workspace', page: 'xml', shell: { project: null, open_path: null, language: 'pt_BR' } as never })
  uninstall = installShortcuts()
})

afterEach(() => {
  uninstall()
  act(() => resetDialogs())
  usePalette.setState({ open: false })
  cleanup()
})

describe('Como usar (F1)', () => {
  it('F1 abre os cinco passos da clássica, com o vídeo e os atalhos', async () => {
    render(<DialogHost />)
    const event = new KeyboardEvent('keydown', { key: 'F1', bubbles: true, cancelable: true })
    act(() => void window.dispatchEvent(event))
    expect(event.defaultPrevented).toBe(true)
    const dialog = await screen.findByRole('dialog', { name: 'Como usar' })
    expect(within(dialog).getByText('Do projeto ao jogo em cinco passos')).toBeTruthy()
    const steps = within(dialog).getAllByTestId('how-to-step')
    expect(steps.map((step) => step.querySelector('.font-semibold')?.textContent)).toEqual([
      'Crie um projeto',
      'Edite e salve',
      'Envie para o jogo com F5',
      'Entenda o preview',
      'Compartilhe',
    ])
    expect(within(dialog).getByTestId('how-to-shortcuts').textContent).toBe(
      'Ctrl+Shift+Nnovo projetoCtrl+Shift+Oabrir projetoF5testar no jogo',
    )
    fireEvent.click(await within(dialog).findByTestId('how-to-video'))
    expect(shellApi.openUrl).toHaveBeenCalledWith('https://stzlabs.com/pt/projects/gf-ui-editor')
    // F1 de novo não abre um segundo; Esc fecha.
    act(() => void window.dispatchEvent(new KeyboardEvent('keydown', { key: 'F1', bubbles: true })))
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    act(() => void window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('textos nos outros idiomas vêm dos catálogos da clássica', () => {
    setLanguage('en_US')
    expect(howToSteps().map(([heading]) => heading)).toEqual([
      'Create a project',
      'Edit and save',
      'Send to the game with F5',
      'Understand the preview',
      'Share',
    ])
    expect(howToShortcuts()).toEqual([
      ['Ctrl+Shift+N', 'new project'],
      ['Ctrl+Shift+O', 'open project'],
      ['F5', 'test in game'],
    ])
    for (const language of ['es_ES', 'fr_FR']) {
      setLanguage(language)
      expect(howToShortcuts()).toHaveLength(3)
      expect(howToSteps().every(([heading, text]) => heading && text && !text.startsWith('Arquivo →'))).toBe(true)
    }
  })

  it('engrenagem tem "Como usar" logo depois de Configurações…', async () => {
    render(
      <>
        <SideRail />
        <MenuHost />
        <DialogHost />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Configurações' }))
    const items = (await screen.findAllByRole('menuitem')).map((item) => item.textContent)
    expect(items[0]).toBe('Configurações…')
    expect(items[1]).toBe('Como usarF1')
    fireEvent.click(screen.getAllByRole('menuitem')[1])
    expect(await screen.findByRole('dialog', { name: 'Como usar' })).toBeTruthy()
  })

  it('Ctrl+K encontra "Como usar"', async () => {
    render(
      <>
        <CommandPalette />
        <DialogHost />
      </>,
    )
    act(() => usePalette.setState({ open: true }))
    fireEvent.change(await screen.findByTestId('command-input'), { target: { value: 'como usar' } })
    const item = await screen.findByText('Como usar', { selector: '[cmdk-item] span' })
    fireEvent.click(item)
    expect(await screen.findByRole('dialog', { name: 'Como usar' }, { timeout: 2000 })).toBeTruthy()
  })
})

describe('estados vazios', () => {
  it('árvore sem XML mostra ícone e texto curto', () => {
    render(<ElementTree />)
    const empty = screen.getByTestId('tree-empty')
    expect(empty.textContent).toContain('Nenhum XML aberto')
    expect(empty.querySelector('svg')).toBeTruthy()
  })
})
