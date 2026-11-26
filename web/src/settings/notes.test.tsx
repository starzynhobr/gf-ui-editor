// Notas de versão (ReleaseNotes), "Novidades" com "Ver todas" e o cartão STZ Labs, sem janela.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Release } from './ReleaseNotes'

const bridge = vi.hoisted(() => ({ call: vi.fn() }))
const shellApi = vi.hoisted(() => ({ whatsNew: vi.fn(), openUrl: vi.fn() }))
// NumberFlow é um elemento customizado que o jsdom não roda: aqui vira um <span> com o número.
vi.mock('@number-flow/react', () => ({
  default: ({ value, ...props }: { value: number }) => <span {...props}>{value}</span>,
}))
vi.mock('../bridge', async (original) => ({ ...(await original<typeof import('../bridge')>()), call: bridge.call }))
vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return { ...actual, api: { ...actual.api, ...shellApi } }
})

const { ReleaseNotes, highlightIcon } = await import('./ReleaseNotes')
const { openWhatsNew } = await import('../home/WhatsNewDialog')
const { DialogHost, resetDialogs } = await import('../ui/dialogs')
const { default: StzPill, compareVersions } = await import('../shell/StzPill')
const { setLanguage } = await import('../i18n')

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
Element.prototype.scrollTo ??= () => undefined

const item = (title: string): [string, string] => [title, `Descrição de ${title}`]
const current: Release = {
  version: '0.8.0',
  date: '2026-11-20',
  sections: {
    new: ['Tela inicial.', 'Enviar ao salvar.', 'Projetos.', 'Atalhos.', 'Zoom.', 'Temas.'].map(item),
    improved: ['Envio menor.', 'Mãozinha.'].map(item),
    fixed: ['Bug do zoom.'].map(item),
  },
}
const older: Release = { version: '0.7.0', date: '2026-10-01', sections: { new: [item('Antiga.')], improved: [], fixed: [item('Corrigido antigo.')] } }

beforeEach(() => {
  setLanguage('pt_BR')
  resetDialogs()
  bridge.call.mockReset()
  shellApi.whatsNew.mockReset()
})
afterEach(cleanup)

describe('notas de versão', () => {
  it('destaques no topo, o resto recolhido com só o título', () => {
    render(<ReleaseNotes releases={[current]} />)
    const highlights = screen.getByTestId('notes-highlights')
    expect(within(highlights).getAllByText(/\.$/).map((node) => node.textContent)).toEqual([
      'Tela inicial.', 'Descrição de Tela inicial.', 'Enviar ao salvar.', 'Descrição de Enviar ao salvar.',
      'Projetos.', 'Descrição de Projetos.', 'Atalhos.', 'Descrição de Atalhos.',
    ])
    expect(screen.getByText('Zoom.')).toBeTruthy()
    expect(screen.queryByText('Descrição de Zoom.')).toBeNull() // recolhido
    fireEvent.click(screen.getByText('Zoom.'))
    expect(screen.getByText('Descrição de Zoom.')).toBeTruthy()
    expect(screen.queryByTestId('notes-timeline')).toBeNull() // uma versão só: sem linha do tempo
  })

  it('chips com contagem filtram a lista; Expandir tudo / Recolher tudo', async () => {
    render(<ReleaseNotes releases={[current]} />)
    const chip = (filter: string) => document.querySelector(`[data-filter=${filter}]`) as HTMLElement
    expect(chip('all').textContent).toBe('Tudo9')
    expect(chip('new').textContent).toBe('Novo6')
    expect(chip('improved').textContent).toBe('Melhorado2')
    expect(chip('fixed').textContent).toBe('Corrigido1')
    fireEvent.click(chip('fixed'))
    await waitFor(() => expect(screen.queryByText('Zoom.')).toBeNull())
    expect(screen.queryByTestId('notes-highlights')).toBeNull()
    expect(screen.getByText('Bug do zoom.')).toBeTruthy()
    fireEvent.click(chip('fixed')) // de novo: volta a Tudo
    await waitFor(() => expect(screen.getByText('Zoom.')).toBeTruthy())
    fireEvent.click(screen.getByTestId('notes-toggle-all'))
    for (const title of ['Zoom.', 'Temas.', 'Envio menor.', 'Mãozinha.', 'Bug do zoom.'])
      expect(screen.getByText(`Descrição de ${title}`)).toBeTruthy()
    expect(screen.getByTestId('notes-toggle-all').textContent).toBe('Recolher tudo')
    fireEvent.click(screen.getByTestId('notes-toggle-all'))
    await waitFor(() => expect(screen.queryByText('Descrição de Zoom.')).toBeNull())
  })

  it('categoria vazia não vira chip', () => {
    render(<ReleaseNotes releases={[{ ...older, sections: { new: [item('Só novo.')], improved: [], fixed: [] } }]} />)
    expect(document.querySelector('[data-filter=improved]')).toBeNull()
    expect(document.querySelector('[data-filter=fixed]')).toBeNull()
  })

  it('várias versões: linha do tempo com cada uma, que pula até ela', () => {
    render(<ReleaseNotes releases={[current, older]} />)
    const timeline = screen.getByTestId('notes-timeline')
    const entries = within(timeline).getAllByRole('button')
    expect(entries.map((entry) => entry.dataset.version)).toEqual(['0.8.0', '0.7.0'])
    fireEvent.click(entries[1])
    expect(entries[1].getAttribute('aria-current')).toBe('true')
    expect(document.querySelector('[data-release="0.7.0"]')).toBeTruthy()
  })

  it('ícone dos destaques pelo título, nos idiomas', () => {
    expect(highlightIcon('Tela inicial completa.')).toBe('home')
    expect(highlightIcon('Send to game on save.')).toBe('send')
    expect(highlightIcon('Algo diferente.')).toBe('sparkles')
  })

  it('Novidades: "Ver todas as versões" traz o histórico', async () => {
    shellApi.whatsNew.mockResolvedValue(current)
    bridge.call.mockImplementation(async (name: string) => (name === 'release_history' ? { version: '0.8.0', releases: [current, older] } : undefined))
    render(<DialogHost />)
    act(() => openWhatsNew())
    await waitFor(() => expect(screen.getByTestId('whats-new-all')).toBeTruthy())
    expect(screen.queryByTestId('notes-timeline')).toBeNull()
    fireEvent.click(screen.getByTestId('whats-new-all'))
    await waitFor(() => expect(screen.getByTestId('notes-timeline')).toBeTruthy())
    expect(screen.getByText('Só esta versão')).toBeTruthy()
  })

  it('Novidades sem histórico: o "Ver todas" nem aparece', async () => {
    shellApi.whatsNew.mockResolvedValue(current)
    bridge.call.mockResolvedValue({ version: '0.8.0', releases: [current] })
    render(<DialogHost />)
    act(() => openWhatsNew())
    await waitFor(() => expect(screen.getByTestId('whats-new')).toBeTruthy())
    await act(async () => undefined)
    expect(screen.queryByTestId('whats-new-all')).toBeNull()
  })
})

describe('cartão STZ Labs: quem ajudou', () => {
  const about = {
    version: '0.8.0', author: 'StarzynhoBR', site: 'https://stzlabs.com/pt', github: 'https://github.com/x', discord: 'https://discord.com/invite/x',
    contributors: [
      { name: 'Harlem', color: '#7C3AED', tags: ['ideas', 'qa'], since: '0.7.0', items: [
        { text: 'Setas entre XMLs', version: '0.7.0' }, { text: 'Atalhos', version: '0.7.0' }, { text: 'Zoom 100%', version: '0.6.0' }, { text: 'Limpar', version: '0.6.0' },
      ] },
      { name: 'Wisin', color: '#0E7490', tags: ['navigation'], since: null, items: [{ text: 'Estilos de navegação', version: null }] },
    ],
  }

  async function openCard() {
    bridge.call.mockImplementation(async (name: string) => (name === 'about_info' ? about : undefined))
    render(<StzPill />)
    fireEvent.click(screen.getByTestId('stz-pill'))
    await waitFor(() => expect(document.querySelector('[data-person=Harlem]')).toBeTruthy())
  }

  it('cabeçalho com avatares, contagens e tags coloridas por tipo', async () => {
    await openCard()
    expect(document.querySelectorAll('.gf-stz-stack .gf-stz-avatar')).toHaveLength(2)
    expect(screen.getByTestId('stz-people-count').getAttribute('data-value')).toBe('2')
    expect(screen.getByTestId('stz-items-count').getAttribute('data-value')).toBe('5')
    expect([...document.querySelectorAll('[data-person=Harlem] .gf-stz-tag')].map((tag) => (tag as HTMLElement).dataset.tag)).toEqual(['ideas', 'qa'])
    expect(screen.getByText('Discord')).toBeTruthy()
    expect(screen.getByText('GitHub')).toBeTruthy()
  })

  it('cartão da pessoa expande com todas as contribuições (sem "+N")', async () => {
    await openCard()
    expect(screen.queryByText(/^\+\d/)).toBeNull()
    expect(screen.queryByTestId('stz-person-items')).toBeNull()
    fireEvent.click(within(document.querySelector('[data-person=Harlem]') as HTMLElement).getByRole('button'))
    const items = await screen.findByTestId('stz-person-items')
    expect(within(items).getAllByRole('listitem')).toHaveLength(4)
  })

  it('vista por versão: linha do tempo da mais nova para a mais antiga', async () => {
    await openCard()
    fireEvent.click(document.querySelector('[data-view=versions]') as HTMLElement)
    await waitFor(() => expect(screen.getByTestId('stz-view-versions')).toBeTruthy())
    await waitFor(() => expect(document.querySelectorAll('[data-version]')).toHaveLength(3))
    const versions = [...document.querySelectorAll('.gf-stz-timeline [data-version]')].map((node) => (node as HTMLElement).dataset.version)
    expect(versions).toEqual(['0.7.0', '0.6.0', 'earlier'])
    expect(screen.getByText('Setas entre XMLs').closest('li')?.textContent).toContain('Harlem — Setas entre XMLs')
  })

  it('ordem de versões com betas', () => {
    expect(compareVersions('0.7.0', '0.7.0-beta.2')).toBeGreaterThan(0)
    expect(compareVersions('0.7.0-beta.1', '0.7.0-beta.2')).toBeLessThan(0)
    expect(compareVersions('0.10.0', '0.9.9')).toBeGreaterThan(0)
  })
})
