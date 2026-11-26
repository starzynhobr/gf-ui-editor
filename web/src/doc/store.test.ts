import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CanvasDocument } from '../bridge'
import {
  applyEdits, checkExternalChange, compareExternal, ExternalSaveConflict, insertControls, keepExternal,
  openDoc, redo, reloadExternal, save, select, undo, useDoc,
} from './store'

const { call } = vi.hoisted(() => ({ call: vi.fn() }))
vi.mock('../bridge', () => ({ call }))

function scene(ids: string[], dirty = false): CanvasDocument {
  return { dirty, elements: ids.map((id, index) => ({ id, index })) } as CanvasDocument
}

const path = 'C:/UI/WorldMap2.xml'
const original = scene(['1', '2'])
const local = scene(['1', '2'], true)
const inserted = scene(['1', '3', '2'], true)
const external = scene(['1', '3', '2'])
const token = 'changed'
const revision = { token, error: null }
const change = { path, token }
const move = { index: 1, field: 'texture', before: null, after: 'a.dds' } as const

describe('document store', () => {
  beforeEach(async () => {
    call.mockReset().mockResolvedValueOnce(original)
    await openDoc(path)
    call.mockClear()
  })

  it('inserts controls in one undo step and remaps the selected ID', async () => {
    select([1])
    call.mockResolvedValueOnce({ changed: true, doc: inserted })
      .mockResolvedValueOnce({ changed: false }).mockResolvedValueOnce(original).mockResolvedValueOnce(inserted)
    await insertControls(['3'], 'Adicionar 1')
    await insertControls(['3'], 'Duplicado')
    expect(call).toHaveBeenCalledWith('doc_insert_controls', path, ['3'])
    expect(useDoc.getState()).toMatchObject({ dirty: true, selection: [2], undoLabel: 'Adicionar 1' })
    await undo()
    expect(call).toHaveBeenLastCalledWith('doc_source_history', false)
    expect(useDoc.getState()).toMatchObject({ canUndo: false, redoLabel: 'Adicionar 1', selection: [1] })
    await redo()
    expect(call).toHaveBeenLastCalledWith('doc_source_history', true)
    expect(useDoc.getState().selection).toEqual([2])
  })

  it('reloads a clean document and resets prior undo and redo history', async () => {
    select([1])
    call.mockResolvedValueOnce(local).mockResolvedValueOnce(original)
      .mockResolvedValueOnce(revision).mockResolvedValueOnce(external)
    await applyEdits([move], 'Editar')
    await undo()
    expect(useDoc.getState().canRedo).toBe(true)
    expect(await checkExternalChange(path, () => false)).toEqual({ reloaded: true })
    expect(useDoc.getState()).toMatchObject({ doc: external, selection: [2], canUndo: false, canRedo: false })
  })

  it('keeps dirty edits, compares, and confirms the specific overwrite', async () => {
    call.mockResolvedValueOnce(local).mockResolvedValueOnce(revision).mockResolvedValueOnce('diff')
      .mockResolvedValueOnce(revision).mockResolvedValueOnce({ conflict: token }).mockResolvedValueOnce({ doc: original })
    await applyEdits([move], 'Editar')
    await checkExternalChange(path, () => false)
    expect(useDoc.getState()).toMatchObject({ externalChange: change, doc: local })
    expect(await compareExternal(change, null)).toBe('diff')
    await keepExternal(change)
    await checkExternalChange(path, () => false)
    expect(useDoc.getState()).toMatchObject({ externalChange: null, doc: local })
    await expect(save()).rejects.toBeInstanceOf(ExternalSaveConflict)
    await save(change)
    expect(call).toHaveBeenLastCalledWith('doc_save_checked', path, token)
    expect(useDoc.getState()).toMatchObject({ dirty: false, canUndo: false })
  })

  it('reports invalid XML once and waits for a decision when a source draft exists', async () => {
    const invalid = { token: 'invalid', error: 'XML inválido' }
    call.mockResolvedValueOnce(invalid).mockResolvedValueOnce(invalid)
      .mockResolvedValueOnce(revision).mockResolvedValueOnce(external)
    expect(await checkExternalChange(path, () => false)).toEqual({ error: 'XML inválido' })
    expect(await checkExternalChange(path, () => false)).toBeUndefined()
    await checkExternalChange(path, () => true)
    expect(useDoc.getState()).toMatchObject({ externalChange: change, doc: original })
    expect(await reloadExternal(change)).toBe(true)
    expect(useDoc.getState()).toMatchObject({ externalChange: null, doc: external })
  })
})
