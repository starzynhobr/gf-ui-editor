// Configurações, atualizador e avisos do manifesto sem janela: a ponte (settingsApi) é falsa.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ManifestNotices, SettingsState, UpdateCheck } from './settingsApi'

const fake = vi.hoisted(() => ({
  state: vi.fn(),
  set: vi.fn(),
  reset: vi.fn(),
  pickGameDir: vi.fn(),
  chooseBackground: vi.fn(),
  updateCheck: vi.fn(),
  updateAutoCheck: vi.fn(),
  updateSkip: vi.fn(),
  updateInstall: vi.fn(),
  manifestNotices: vi.fn(),
  manifestMarkSeen: vi.fn(),
}))
const shellApi = vi.hoisted(() => ({ setLanguage: vi.fn(), openUrl: vi.fn(), openLoose: vi.fn(), shellState: vi.fn() }))
const canvas = vi.hoisted(() => ({ applyCanvasPreference: vi.fn() }))

vi.mock('./settingsApi', async (original) => ({ ...(await original<typeof import('./settingsApi')>()), settingsApi: fake }))
vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return { ...actual, api: { ...actual.api, ...shellApi } }
})
vi.mock('../doc/store', async () => ({ ...(await import('../test/mockStore')), ...canvas }))
vi.mock('../bridge', async (original) => ({ ...(await original<typeof import('../bridge')>()), call: vi.fn(async () => undefined) }))

const { default: SettingsHost, openSettings, closeSettings, useSettings } = await import('./SettingsScreen')
const { checkForUpdates, showManifestNotices } = await import('./updates')
const { DialogHost, resetDialogs } = await import('../ui/dialogs')
const { useShell } = await import('../store')
const { useLanguage } = await import('../i18n')

const baseState: SettingsState = {
  version: '0.9.0',
  beta_build: false,
  can_install: false,
  values: {
    language: 'pt_BR',
    ui_mode: 'web',
    web_theme: 'dark',
    web_font: 'system',
    navigation_style: 'corel',
    auto_update_check: true,
    beta_updates: false,
    publish_on_save: false,
    publish_confirmed: true,
    offer_project_on_open: true,
    canvas_saved_positions: true,
    canvas_character: true,
    game_dir: '',
    game_resolution: 'game',
    background_mode: 'builtin',
  },
  game_dir_valid: false,
  game_dir_default: 'C:\\Jogo',
  game_background: '',
  has_custom_background: false,
  resolutions: ['1024x768', '1920x1080'],
  review: { skipped_update: '1.0.0', manifest_seen: 2, layout: true },
}

const shell = {
  version: '0.9.0', language: 'pt_BR', ui_mode: 'web', project: null, open_path: null, loose_dir: null,
  pending: 0, publish_confirmed: true, publish_on_save: false,
}

let current: SettingsState

beforeEach(() => {
  resetDialogs()
  Object.values(fake).forEach((fn) => fn.mockReset())
  Object.values(shellApi).forEach((fn) => fn.mockReset())
  canvas.applyCanvasPreference.mockReset()
  current = structuredClone(baseState)
  fake.state.mockImplementation(async () => current)
  fake.set.mockImplementation(async (name: keyof SettingsState['values'], value: never) => {
    current = { ...current, values: { ...current.values, [name]: value } }
    return current
  })
  fake.reset.mockImplementation(async (what: 'skipped_update' | 'manifest_seen' | 'layout') => {
    current = { ...current, review: { ...current.review, [what]: what === 'manifest_seen' ? 0 : what === 'layout' ? false : '' } }
    return current
  })
  shellApi.shellState.mockResolvedValue(shell)
  shellApi.setLanguage.mockImplementation(async (language: string) => {
    current = { ...current, values: { ...current.values, language } }
    return { ...shell, language }
  })
  useShell.setState({ shell: shell as never, view: 'home' })
  useLanguage.setState({ language: 'pt_BR' })
  useSettings.setState({ open: false, section: 'general', canvasEpoch: 0 })
})
afterEach(() => {
  cleanup()
  closeSettings()
})

function renderSettings(section?: Parameters<typeof openSettings>[0]) {
  render(
    <>
      <SettingsHost />
      <DialogHost />
    </>,
  )
  act(() => openSettings(section))
}

const toggle = (name: string) => document.querySelector(`[data-setting="${name}"]`) as HTMLButtonElement

describe('tela de Configurações', () => {
  it('abre na seção Geral e navega pelas cinco seções', async () => {
    renderSettings()
    await waitFor(() => expect(screen.getByTestId('settings-general')).toBeTruthy())
    expect(screen.getByText('Versão pulada')).toBeTruthy()
    for (const [section, text] of [
      ['editor', 'Navegação do canvas'],
      ['screen', 'Resolução do jogo'],
      ['publish', 'Enviar para o jogo ao salvar'],
      ['updates', 'Receber versões beta'],
    ]) {
      fireEvent.click(document.querySelector(`[data-section=${section}]`)!)
      await waitFor(() => expect(screen.getByTestId(`settings-${section}`)).toBeTruthy())
      expect(within(screen.getByTestId(`settings-${section}`)).getAllByText(text).length).toBeGreaterThan(0)
    }
  })

  it('switch grava a preferência pela ponte', async () => {
    renderSettings('publish')
    await waitFor(() => expect(toggle('publish_on_save')).toBeTruthy())
    expect(toggle('publish_on_save').getAttribute('aria-checked')).toBe('false')
    fireEvent.click(toggle('publish_on_save'))
    await waitFor(() => expect(fake.set).toHaveBeenCalledWith('publish_on_save', true))
    await waitFor(() => expect(toggle('publish_on_save').getAttribute('aria-checked')).toBe('true'))
    // "Confirmar antes do primeiro envio" é o inverso de publish_confirmed.
    expect(toggle('publish_confirmed').getAttribute('aria-checked')).toBe('false')
    fireEvent.click(toggle('publish_confirmed'))
    await waitFor(() => expect(fake.set).toHaveBeenCalledWith('publish_confirmed', false))
  })

  it('duas trocas rápidas gravam as duas, na ordem', async () => {
    renderSettings('editor')
    await waitFor(() => expect(document.querySelector('select[name=navigation_style]')).toBeTruthy())
    const select = () => document.querySelector('select[name=navigation_style]')!
    fireEvent.change(select(), { target: { value: 'paintnet' } })
    fireEvent.change(select(), { target: { value: 'photoshop' } })
    await waitFor(() => expect(fake.set.mock.calls).toEqual([['navigation_style', 'paintnet'], ['navigation_style', 'photoshop']]))
    await waitFor(() => expect((select() as HTMLSelectElement).value).toBe('photoshop'))
  })

  it('erro da ponte volta o switch e avisa', async () => {
    fake.set.mockRejectedValueOnce(new Error('sem permissão'))
    renderSettings('updates')
    await waitFor(() => expect(toggle('auto_update_check')).toBeTruthy())
    fireEvent.click(toggle('auto_update_check'))
    await waitFor(() => expect(screen.getByText('sem permissão')).toBeTruthy())
    expect(toggle('auto_update_check').getAttribute('aria-checked')).toBe('true')
  })

  it('idioma pela lista troca a interface na hora', async () => {
    renderSettings()
    await waitFor(() => expect(document.querySelector('select[name=language]')).toBeTruthy())
    fireEvent.change(document.querySelector('select[name=language]')!, { target: { value: 'en_US' } })
    await waitFor(() => expect(shellApi.setLanguage).toHaveBeenCalledWith('en_US'))
    await waitFor(() => expect(useLanguage.getState().language).toBe('en_US'))
    expect(screen.getAllByText('General').length).toBeGreaterThan(0)
  })

  it('resolução com um XML aberto passa pelo canvas (mesma preferência da barra)', async () => {
    useShell.setState({ shell: { ...shell, open_path: 'C:\\p\\Bag.xml' } as never })
    canvas.applyCanvasPreference.mockResolvedValue({})
    renderSettings('screen')
    await waitFor(() => expect(document.querySelector('select[name=game_resolution]')).toBeTruthy())
    fireEvent.change(document.querySelector('select[name=game_resolution]')!, { target: { value: '1920x1080' } })
    await waitFor(() => expect(canvas.applyCanvasPreference).toHaveBeenCalledWith('C:\\p\\Bag.xml', 'resolution', '1920x1080'))
    expect(fake.set).not.toHaveBeenCalled()
    await waitFor(() => expect(useSettings.getState().canvasEpoch).toBe(1))
  })

  it('sem XML aberto, a resolução vai direto às preferências', async () => {
    renderSettings('screen')
    await waitFor(() => expect(document.querySelector('select[name=game_resolution]')).toBeTruthy())
    fireEvent.change(document.querySelector('select[name=game_resolution]')!, { target: { value: 'off' } })
    await waitFor(() => expect(fake.set).toHaveBeenCalledWith('game_resolution', 'off'))
    expect(canvas.applyCanvasPreference).not.toHaveBeenCalled()
  })

  it('rever e limpar: o botão some quando não há mais o que limpar', async () => {
    renderSettings()
    await waitFor(() => expect(screen.getByText('Oferecer de novo')).toBeTruthy())
    fireEvent.click(screen.getByText('Oferecer de novo'))
    await waitFor(() => expect(fake.reset).toHaveBeenCalledWith('skipped_update'))
    await waitFor(() => expect(screen.queryByText('Oferecer de novo')).toBeNull())
    expect(screen.getByText('Nenhuma versão pulada.')).toBeTruthy()
    fireEvent.click(screen.getByText('Mostrar de novo'))
    await waitFor(() => expect(fake.reset).toHaveBeenCalledWith('manifest_seen'))
    await waitFor(() => expect(screen.queryByText('Mostrar de novo')).toBeNull())
    expect(screen.getByText('Nenhum aviso do STZ Labs mostrado ainda.')).toBeTruthy()
    fireEvent.click(screen.getByText('Restaurar'))
    await waitFor(() => expect(screen.queryByText('Restaurar')).toBeNull())
  })

  it('sem nada para rever, nenhum botão apagado aparece', async () => {
    current = { ...current, review: { skipped_update: '', manifest_seen: 0, layout: false } }
    renderSettings()
    await waitFor(() => expect(screen.getByTestId('settings-general')).toBeTruthy())
    expect(document.querySelectorAll('[data-testid=settings-general] button:disabled')).toHaveLength(0)
    for (const id of ['settings-review-skipped', 'settings-review-notices', 'settings-review-layout'])
      expect(screen.getByTestId(id).querySelector('button')).toBeNull()
  })

  it('fonte: cada opção escrita na sua fonte, troca na hora e grava web_font', async () => {
    const { call } = await import('../bridge')
    renderSettings()
    await waitFor(() => expect(document.querySelector('[data-setting=web_font]')).toBeTruthy())
    const options = Array.from(document.querySelectorAll('[data-setting=web_font] [role=radio]')) as HTMLElement[]
    expect(options.map((option) => option.dataset.value)).toEqual(['system', 'plex', 'inter', 'geist'])
    expect(options[2].querySelector('.gf-font-preview-inter')).toBeTruthy()
    fireEvent.click(options[3])
    expect(document.documentElement.dataset.font).toBe('geist')
    expect(call).toHaveBeenCalledWith('ui_set_font', 'geist')
    await waitFor(() => expect(options[3].getAttribute('aria-checked')).toBe('true'))
    fireEvent.click(options[0])
    expect(document.documentElement.dataset.font).toBeUndefined() // Sistema: os valores padrão de @theme
  })

  it('pasta do jogo: escolher e voltar à padrão', async () => {
    fake.pickGameDir.mockResolvedValue('D:\\GF')
    renderSettings('publish')
    await waitFor(() => expect(screen.getByText('C:\\Jogo')).toBeTruthy())
    fireEvent.click(screen.getByText('Escolher…'))
    await waitFor(() => expect(fake.set).toHaveBeenCalledWith('game_dir', 'D:\\GF'))
    await waitFor(() => expect(screen.getByText('Usar a padrão')).toBeTruthy())
    fireEvent.click(screen.getByText('Usar a padrão'))
    await waitFor(() => expect(fake.set).toHaveBeenCalledWith('game_dir', ''))
  })

  it('Esc fecha a tela', async () => {
    renderSettings()
    await waitFor(() => expect(screen.getByTestId('settings')).toBeTruthy())
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(useSettings.getState().open).toBe(false)
  })
})

const offer: UpdateCheck = {
  status: 'offer',
  current: '0.8.0',
  include_betas: false,
  error: '',
  offer: {
    version: '0.9.0',
    current: '0.8.0',
    page_url: 'https://github.com/x',
    fallback_text: '',
    verified: true,
    can_install: false,
    grouped: true,
    releases: [
      { version: '0.9.0', date: '2026-11-20', sections: { new: [['Configurações.', 'Tela nova.']], improved: [], fixed: [] } },
      { version: '0.8.5', date: '2026-11-01', sections: { new: [], improved: [], fixed: [['Atlas.', 'Corrigido.']] } },
    ],
  },
}

describe('atualizador', () => {
  it('oferta mostra as notas das versões puladas; Pular grava a versão', async () => {
    fake.updateCheck.mockResolvedValue(offer)
    render(<DialogHost />)
    const done = checkForUpdates(true)
    await waitFor(() => expect(screen.getByTestId('update-dialog')).toBeTruthy())
    expect(screen.getByText('O que chegou desde a 0.8.0')).toBeTruthy()
    expect(screen.getByText('Configurações.')).toBeTruthy()
    expect(screen.getByText('Atlas.')).toBeTruthy()
    expect(screen.getByText('Abrir página da release')).toBeTruthy() // rodando pelo código
    fireEvent.click(screen.getByText('Pular esta versão'))
    await done
    expect(fake.updateSkip).toHaveBeenCalledWith('0.9.0')
    expect(fake.updateInstall).not.toHaveBeenCalled()
  })

  it('Atualizar chama a instalação da versão oferecida', async () => {
    fake.updateCheck.mockResolvedValue(offer)
    fake.updateInstall.mockResolvedValue({ opened_page: true })
    render(<DialogHost />)
    const done = checkForUpdates(true)
    await waitFor(() => expect(screen.getByText('Abrir página da release')).toBeTruthy())
    fireEvent.click(screen.getByText('Abrir página da release'))
    await done
    expect(fake.updateInstall).toHaveBeenCalledWith('0.9.0')
  })

  it('manual sem novidade avisa; automática fica quieta', async () => {
    fake.updateCheck.mockResolvedValue({ status: 'latest', current: '0.9.0', include_betas: true, error: '' })
    render(<DialogHost />)
    void checkForUpdates(true)
    await waitFor(() => expect(screen.getByText('Você já está na versão mais recente (0.9.0), contando as betas.')).toBeTruthy())
    fireEvent.click(screen.getByText('OK'))
    fake.updateCheck.mockResolvedValue({ status: 'error', current: '', include_betas: false, error: 'offline' })
    await checkForUpdates(false)
    expect(screen.queryByText(/offline/)).toBeNull()
  })

  it('erro na verificação manual mostra o motivo', async () => {
    fake.updateCheck.mockResolvedValue({ status: 'error', current: '', include_betas: false, error: 'offline' })
    render(<DialogHost />)
    void checkForUpdates(true)
    await waitFor(() => expect(screen.getByText(/Não foi possível verificar atualizações\.[\s\S]*offline/)).toBeTruthy())
  })
})

describe('manifesto remoto', () => {
  const notices: ManifestNotices = {
    needs_update: false,
    version: '0.9.0',
    min_version: null,
    messages: [
      { id: 'a', level: 'warning', text: 'Servidor em manutenção.', url: 'https://stzlabs.com/x' },
      { id: 'b', level: 'info', text: 'Novo tutorial.', url: null },
    ],
    disabled: [],
  }

  it('mostra cada aviso uma vez e marca como visto', async () => {
    fake.manifestNotices.mockResolvedValue(notices)
    render(<DialogHost />)
    const done = showManifestNotices()
    await waitFor(() => expect(screen.getByText('Servidor em manutenção.')).toBeTruthy())
    expect(screen.getByText('Aviso do STZ GF UI')).toBeTruthy()
    fireEvent.click(screen.getByText('Abrir link'))
    await waitFor(() => expect(screen.getByText('Novo tutorial.')).toBeTruthy())
    expect(screen.queryByText('Abrir link')).toBeNull()
    fireEvent.click(screen.getByText('OK'))
    await done
    expect(shellApi.openUrl).toHaveBeenCalledWith('https://stzlabs.com/x')
    expect(fake.manifestMarkSeen.mock.calls).toEqual([['a'], ['b']])
  })

  it('versão mínima pergunta e procura a atualização', async () => {
    fake.manifestNotices.mockResolvedValue({ ...notices, needs_update: true, min_version: '1.0.0', messages: [] })
    fake.updateCheck.mockResolvedValue({ status: 'latest', current: '0.9.0', include_betas: false, error: '' })
    render(<DialogHost />)
    const done = showManifestNotices()
    await waitFor(() => expect(screen.getByText(/mínima: 1\.0\.0/)).toBeTruthy())
    fireEvent.click(screen.getByText('Sim'))
    await waitFor(() => expect(fake.updateCheck).toHaveBeenCalledWith(true))
    await waitFor(() => expect(screen.getByText('OK')).toBeTruthy())
    fireEvent.click(screen.getByText('OK'))
    await done
  })

  it('sem manifesto não mostra nada', async () => {
    fake.manifestNotices.mockResolvedValue(null)
    render(<DialogHost />)
    await showManifestNotices()
    expect(document.querySelector('[role=dialog]')).toBeNull()
  })
})
