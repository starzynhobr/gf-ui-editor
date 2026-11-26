// "Exportar para várias resoluções…": escolha das resoluções, prévias, ampliar e arrastar
// (ajuste só daquela resolução), arquivos só de uma resolução e a exportação, sem janela.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MotionGlobalConfig } from 'motion/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Plan, PieceInfo, Size, TargetPlan, WindowInfo } from './resolutionsApi'

const bridge = vi.hoisted(() => ({ call: vi.fn() }))
const shellApi = vi.hoisted(() => ({ openFolder: vi.fn() }))
vi.mock('../bridge', async (original) => ({ ...(await original<typeof import('../bridge')>()), call: bridge.call }))
vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return { ...actual, api: { ...actual.api, ...shellApi } }
})
vi.mock('../actions', () => ({ withProgress: (_label: string, work: () => Promise<unknown>) => work() }))
vi.mock('../shell/saving', () => ({ saveBeforeProjectAction: async () => true }))
vi.mock('../canvas/dds/cache', () => ({
  TextureCache: class {
    load() {
      return Promise.resolve(null)
    }
    dispose() {}
  },
}))

const { openResolutionsDialog } = await import('./ResolutionsDialog')
const { ruleText } = await import('./rules')
const { pieceAt } = await import('./ResolutionPreview')
const { DialogHost, resetDialogs } = await import('../ui/dialogs')
const { setLanguage } = await import('../i18n')

MotionGlobalConfig.skipAnimations = true
// jsdom não desenha: a prévia só pula o desenho (o resto da tela é o que se testa aqui).
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext']
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver

const COMMON: Size[] = [[1366, 768], [1600, 900], [1920, 1080], [2560, 1440]]
const piece = (rect: [number, number, number, number], adjusted = false, rule: PieceInfo['rule'] = ['middle', 'middle']): PieceInfo => ({
  key: 'id:10000', indexes: [1, 2], rule, base: [631, 455, 295, 46], rect, adjusted,
})
const elf = (rect: [number, number, number, number], adjusted = false): WindowInfo => ({
  file: 'ElfAttack.xml', kind: 'game', changed: true, hud: false, moves: true, pieces: [piece(rect, adjusted)],
})
const menu: WindowInfo = {
  file: 'Menu.xml', kind: 'game', changed: false, hud: true, moves: false, pieces: [{ ...piece([313, 650, 740, 118]), key: 'id:1', rule: ['game', 'game'] }],
}

let adjusted: Record<string, [number, number]> = {}
const calls: [string, unknown[]][] = []

function target(size: Size): TargetPlan {
  const key = `${size[0]}x${size[1]}`
  const same = size[0] === 1366
  const point = adjusted[key]
  const window = elf(point ? [...point, 295, 46] : [Math.round((size[0] - 295) * 0.59), Math.round((size[1] - 46) * 0.6), 295, 46], !!point)
  return {
    size, key,
    windows: same ? [{ ...window, changed: false }, menu] : [window, menu],
    files: same ? [] : ['ElfAttack.xml'],
    variants: key === '2560x1440' ? ['main.dds'] : [],
  }
}

function handler(method: string, ...args: unknown[]) {
  calls.push([method, args])
  switch (method) {
    case 'resolutions_info':
      return { project: 'Red', base: [1366, 768], previewBase: [1366, 768], common: COMMON, presets: COMMON, targets: COMMON, hud: ['Menu.xml'] }
    case 'resolutions_plan':
      return { base: args[0] as Size, targets: (args[1] as Size[]).map(target), windows: 300 } satisfies Plan
    case 'resolutions_scenes':
      return []
    case 'resolutions_adjust': {
      const [, , size, point] = args as [string, string, Size, [number, number] | null]
      const key = `${size[0]}x${size[1]}`
      if (point) adjusted[key] = point
      else delete adjusted[key]
      return null
    }
    case 'resolutions_pick_folder':
      return 'C:/Saida'
    case 'resolutions_export':
      return {
        folder: 'C:/Saida',
        zips: [
          { key: '1366x768', path: 'C:/Saida/Red 1366x768.zip', count: 0 },
          { key: '1920x1080', path: 'C:/Saida/Red 1920x1080.zip', count: 412 },
        ],
      }
    default:
      return null
  }
}

const methods = (name: string) => calls.filter(([method]) => method === name).map(([, args]) => args)

beforeEach(() => {
  setLanguage('pt_BR')
  resetDialogs()
  adjusted = {}
  calls.length = 0
  bridge.call.mockReset()
  bridge.call.mockImplementation(async (method: string, ...args: unknown[]) => handler(method, ...args))
  shellApi.openFolder.mockReset()
})
afterEach(cleanup)

async function open() {
  render(<DialogHost />)
  act(() => void openResolutionsDialog())
  await screen.findByTestId('resolutions-dialog')
  await screen.findByTestId('resolution-card-2560x1440')
}

describe('exportar para várias resoluções', () => {
  it('as 4 comuns marcadas, uma prévia por resolução e o que muda em cada uma', async () => {
    await open()
    for (const size of ['1366x768', '1600x900', '1920x1080', '2560x1440']) {
      expect(screen.getByTestId(`resolution-chip-${size}`).getAttribute('aria-pressed')).toBe('true')
    }
    expect(within(screen.getByTestId('resolution-card-1366x768')).getByText('1 janela(s) mudam de lugar')).toBeTruthy()
    expect(within(screen.getByTestId('resolution-card-2560x1440')).getByText('1 arquivo(s) só desta')).toBeTruthy()
    expect((screen.getByTestId('resolution-base') as HTMLSelectElement).value).toBe('1366x768')
    expect(screen.getByTestId('resolutions-export').textContent).toContain('Exportar 4 zip(s)')
    // As cenas das miniaturas pedem o HUD junto (contexto).
    await waitFor(() => expect(methods('resolutions_scenes').length).toBeGreaterThanOrEqual(4))
    expect(methods('resolutions_scenes')[0][2]).toEqual(['ElfAttack.xml', 'Menu.xml'])
  })

  it('desmarcar e "+ personalizada" mudam as resoluções (e a escolha fica guardada)', async () => {
    await open()
    fireEvent.click(screen.getByTestId('resolution-chip-1600x900'))
    await waitFor(() => expect(screen.queryByTestId('resolution-card-1600x900')).toBeNull())
    fireEvent.click(screen.getByTestId('resolution-custom'))
    const field = await screen.findByDisplayValue('1680x1050')
    fireEvent.change(field, { target: { value: '1440 x 900' } })
    fireEvent.click(screen.getByText('OK'))
    await screen.findByTestId('resolution-card-1440x900')
    const choice = methods('resolutions_set_choice').at(-1)!
    expect(choice[1]).toEqual([[1366, 768], [1920, 1080], [2560, 1440], [1440, 900]])
  })

  it('ampliar, arrastar a janela: grava só naquela resolução e marca "você ajustou"', async () => {
    await open()
    fireEvent.click(screen.getByTestId('resolution-card-1920x1080'))
    await screen.findByTestId('resolution-focus-1920x1080')
    const list = screen.getByTestId('resolution-windows')
    expect(within(list).getByText('ElfAttack.xml')).toBeTruthy()
    expect(within(list).getByText('fica no meio')).toBeTruthy()
    expect(within(list).queryByText('Menu.xml')).toBeNull() // o jogo cuida: não está na lista

    const stage = await screen.findByTestId('resolution-stage')
    // Na tela de teste, 1 px do canvas = 1 px da resolução.
    stage.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1920, height: 1080, right: 1920, bottom: 1080, x: 0, y: 0, toJSON() {} })
    const [x, y] = target([1920, 1080]).windows[0].pieces[0].rect
    fireEvent.pointerDown(stage, { clientX: x + 10, clientY: y + 10, pointerId: 1 })
    fireEvent.pointerMove(stage, { clientX: x + 110, clientY: y + 60, pointerId: 1 })
    fireEvent.pointerUp(stage, { clientX: x + 110, clientY: y + 60, pointerId: 1 })
    await waitFor(() => expect(methods('resolutions_adjust')).toEqual([['ElfAttack.xml', 'id:10000', [1920, 1080], [x + 100, y + 50]]]))
    await within(screen.getByTestId('resolution-windows')).findByText('você ajustou')

    fireEvent.click(screen.getByLabelText('Desfazer o ajuste'))
    await waitFor(() => expect(methods('resolutions_adjust').at(-1)).toEqual(['ElfAttack.xml', 'id:10000', [1920, 1080], null]))
    await within(screen.getByTestId('resolution-windows')).findByText('fica no meio')

    fireEvent.click(screen.getByTestId('resolution-back'))
    await screen.findByTestId('resolution-grid')
  })

  it('o ajuste aparece na prévia de fora como "você ajustou"', async () => {
    adjusted['2560x1440'] = [10, 10]
    await open()
    expect(within(screen.getByTestId('resolution-card-2560x1440')).getByTestId('adjusted-chip').textContent).toBe('você ajustou 1')
    expect(within(screen.getByTestId('resolution-card-1920x1080')).queryByTestId('adjusted-chip')).toBeNull()
  })

  it('arquivos só de uma resolução: lista, tirar e usar outro', async () => {
    await open()
    fireEvent.click(screen.getByTestId('resolution-card-2560x1440'))
    const variants = await screen.findByTestId('resolution-variants')
    expect(within(variants).getByText('main.dds')).toBeTruthy()
    fireEvent.click(within(variants).getByLabelText('Tirar'))
    await waitFor(() => expect(methods('resolutions_remove_variant')).toEqual([[[2560, 1440], 'main.dds']]))
    fireEvent.click(within(variants).getByText('Usar outro arquivo nesta resolução…'))
    await waitFor(() => expect(methods('resolutions_add_variant')).toEqual([[[2560, 1440]]]))
  })

  it('exporta um zip por resolução e avisa o que ficou igual', async () => {
    await open()
    fireEvent.click(screen.getByTestId('zip-changed'))
    fireEvent.click(screen.getByTestId('zip-all'))
    expect(screen.getByTestId('resolutions-export').textContent).toContain('Exportar 5 zip(s)')
    fireEvent.click(screen.getByTestId('resolutions-export'))
    await waitFor(() => expect(methods('resolutions_export')).toEqual([['C:/Saida', [1366, 768], COMMON, false, true]]))
    const done = await screen.findByText(/1 zip\(s\) em C:\/Saida/)
    expect(done.textContent).toContain('Red 1920x1080.zip')
    expect(screen.getByText(/Iguais à sua UI, sem zip: 1366 × 768/)).toBeTruthy()
    expect(screen.queryByTestId('resolutions-dialog')).toBeNull()
    fireEvent.click(screen.getByText('Abrir pasta'))
    await waitFor(() => expect(shellApi.openFolder).toHaveBeenCalledWith('C:/Saida'))
  })

  it('frases sem jargão para cada regra, e o clique acha o pedaço por cima', () => {
    expect(ruleText(piece([0, 0, 1, 1], false, ['start', 'start']), 'fixed')).toBe('fica no canto de cima, à esquerda')
    expect(ruleText(piece([0, 0, 1, 1], false, ['end', 'end']), 'fixed')).toBe('fica no canto de baixo, à direita')
    expect(ruleText(piece([0, 0, 1, 1], false, ['middle', 'end']), 'fixed')).toBe('fica embaixo, no meio')
    expect(ruleText(piece([0, 0, 1, 1], false, ['game', 'game']), 'game')).toBe('fica onde o jogo põe')
    expect(ruleText(piece([0, 0, 1, 1], true), 'game')).toBe('você ajustou')
    setLanguage('en_US')
    expect(ruleText(piece([0, 0, 1, 1], false, ['middle', 'middle']), 'fixed')).toBe('stays in the middle')
    const windows = [elf([100, 100, 50, 50]), menu]
    expect(pieceAt(windows, [120, 120])?.file).toBe('ElfAttack.xml')
    expect(pieceAt(windows, [400, 700])?.file).toBe('Menu.xml') // HUD também se arrasta
    expect(pieceAt(windows, [5, 5])).toBeNull()
  })
})
