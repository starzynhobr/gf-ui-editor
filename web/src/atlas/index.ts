import { useSyncExternalStore } from 'react'
import { useDoc } from '../doc/store'

type Request = { kind: 'edit'; index: number; path: string } | { kind: 'preview'; path: string }

let current: Request | null = null
const listeners = new Set<() => void>()

function setRequest(request: Request | null) {
  current = request
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function openAtlas(index: number) {
  const { path } = useDoc.getState()
  if (path) setRequest({ kind: 'edit', index, path })
}

/** Full path from the Textures list, including when no XML is open. */
export function previewTexture(path: string) {
  if (path) setRequest({ kind: 'preview', path })
}

export function useAtlasRequest() {
  return useSyncExternalStore(subscribe, () => current)
}

export function closeAtlas() {
  setRequest(null)
}
