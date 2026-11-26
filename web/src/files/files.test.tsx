// Prévia flutuante da lista de Texturas: cabeçalho dds/tga, atraso de entrada, seguir a linha,
// sumir ao sair/rolar/clicar e o clique continuar abrindo a prévia completa.
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MotionGlobalConfig } from 'motion/react'
import { describeTexture } from './textureHeader'

// Sem animação de saída: o cartão sai do DOM na hora.
MotionGlobalConfig.skipAnimations = true

const previewTexture = vi.fn()
const loadTexturePeek = vi.fn(async (path: string) => ({
  thumb: null,
  width: path.endsWith('b.dds') ? 64 : 512,
  height: 256,
  format: 'DXT5',
}))

vi.mock('./peekCache', async (original) => ({
  ...(await original<typeof import('./peekCache')>()),
  loadTexturePeek: (path: string) => loadTexturePeek(path),
  cachedPeek: () => undefined,
}))
// jsdom não mede nada: a lista virtual ganha altura para desenhar as linhas.
Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 400 })
Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 300 })
HTMLElement.prototype.getBoundingClientRect = () => new DOMRect(0, 0, 300, 400)
vi.mock('../shell/atlas', () => ({ atlasModule: async () => ({ previewTexture }) }))
vi.mock('../api', async (original) => {
  const actual = await original<typeof import('../api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      fileList: vi.fn(async () => ({
        mode: 'textures',
        files: ['a.dds', 'b.dds', 'c.tga'],
        modified: [],
        layers: [],
        sections: [{ kind: 'all', items: [0, 1, 2] }],
        heights: {},
        has_textures: true,
        shared_publish: [],
        directory: 'C:\\p\\ui',
        in_project: true,
      })),
      textEditorName: vi.fn(async () => 'Notepad++'),
    },
  }
})

const { default: FilesPanel } = await import('./FilesPanel')
const { useShell } = await import('../store')

function dds({ fourcc, bits = 0, masks = [0, 0, 0, 0], flags }: { fourcc?: string; bits?: number; masks?: number[]; flags: number }) {
  const bytes = new Uint8Array(128)
  const view = new DataView(bytes.buffer)
  view.setUint32(0, 0x20534444, true)
  view.setUint32(4, 124, true)
  view.setUint32(12, 128, true) // altura
  view.setUint32(16, 256, true) // largura
  view.setUint32(76, 32, true)
  view.setUint32(80, flags, true)
  if (fourcc) bytes.set([...fourcc].map((char) => char.charCodeAt(0)), 84)
  view.setUint32(88, bits, true)
  masks.forEach((mask, index) => view.setUint32(92 + index * 4, mask, true))
  return bytes
}

describe('cabeçalho de textura', () => {
  it('lê dimensões e formato de dds e tga', () => {
    expect(describeTexture(dds({ flags: 0x4, fourcc: 'DXT1' }), 'a.dds')).toEqual({ width: 256, height: 128, format: 'DXT1' })
    expect(describeTexture(dds({ flags: 0x41, bits: 32, masks: [0xff0000, 0xff00, 0xff, 0xff000000] }), 'a.dds')?.format).toBe('ARGB 32')
    expect(describeTexture(dds({ flags: 0x40, bits: 32, masks: [0xff0000, 0xff00, 0xff, 0] }), 'a.dds')?.format).toBe('XRGB 32')
    expect(describeTexture(dds({ flags: 0x40, bits: 16, masks: [0xf800, 0x7e0, 0x1f, 0] }), 'a.dds')?.format).toBe('RGB 565')
    expect(describeTexture(dds({ flags: 0x41, bits: 16, masks: [0xf00, 0xf0, 0xf, 0xf000] }), 'a.dds')?.format).toBe('ARGB 4444')
    const tga = new Uint8Array(18)
    tga[2] = 10
    tga[12] = 64
    tga[14] = 32
    tga[16] = 32
    expect(describeTexture(tga, 'x.tga')).toEqual({ width: 64, height: 32, format: 'TGA ARGB 32 RLE' })
    expect(describeTexture(new Uint8Array(40), 'a.dds')).toBeNull()
  })
})

describe('prévia flutuante das texturas', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    loadTexturePeek.mockClear()
    previewTexture.mockClear()
    useShell.setState({ page: 'textures', shell: null, revision: 0 } as never)
  })
  afterEach(() => {
    vi.useRealTimers()
    cleanup()
  })

  const flush = () => act(async () => { for (let step = 0; step < 6; step++) await Promise.resolve() })
  const row = async (name: string) => {
    for (let attempt = 0; attempt < 20 && !document.querySelector(`[data-file="${name}"]`); attempt++) {
      await act(async () => { await Promise.resolve() })
    }
    return document.querySelector<HTMLElement>(`[data-file="${name}"]`)!
  }

  it('aparece depois do atraso, segue a linha e some ao sair, rolar e clicar', async () => {
    render(<FilesPanel />)
    const first = await row('a.dds')
    expect(first).toBeTruthy()
    expect(first.title).toBe('')

    fireEvent.mouseMove(first)
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(screen.queryByTestId('texture-peek')).toBeNull()
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(screen.getByTestId('texture-peek-name').textContent).toBe('a.dds')
    expect(loadTexturePeek).toHaveBeenCalledWith('C:\\p\\ui\\a.dds')
    await flush()
    expect(screen.getByTestId('texture-peek-size').textContent).toBe('512 × 256 px')
    expect(screen.getByTestId('texture-peek-format').textContent).toBe('DXT5')

    // Já visível: segue a próxima linha na hora.
    fireEvent.mouseMove(await row('b.dds'))
    expect(screen.getByTestId('texture-peek-name').textContent).toBe('b.dds')
    await flush()
    expect(screen.getByTestId('texture-peek-size').textContent).toBe('64 × 256 px')

    // Rolar esconde; parar de novo mostra depois do atraso.
    const list = first.parentElement!.parentElement!
    fireEvent.scroll(list)
    await act(async () => { vi.advanceTimersByTime(300) })
    expect(screen.queryByTestId('texture-peek-name')).toBeNull()
    fireEvent.mouseMove(await row('b.dds'))
    await act(async () => { vi.advanceTimersByTime(400) })
    expect(screen.getByTestId('texture-peek-name').textContent).toBe('b.dds')

    // Clicar esconde e abre a prévia completa; mexer na mesma linha não traz o cartão de volta.
    const second = await row('b.dds')
    fireEvent.mouseDown(second)
    fireEvent.click(second)
    await act(async () => { vi.advanceTimersByTime(300) })
    expect(previewTexture).toHaveBeenCalledWith('C:\\p\\ui\\b.dds')
    expect(screen.queryByTestId('texture-peek-name')).toBeNull()
    fireEvent.mouseMove(second)
    await act(async () => { vi.advanceTimersByTime(400) })
    expect(screen.queryByTestId('texture-peek-name')).toBeNull()

    // Sair da lista esconde e cancela o atraso.
    fireEvent.mouseMove(await row('c.tga'))
    fireEvent.mouseLeave(list)
    await act(async () => { vi.advanceTimersByTime(400) })
    expect(screen.queryByTestId('texture-peek-name')).toBeNull()
  })
})
