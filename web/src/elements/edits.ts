// Edições feitas pela casca (painel): um lote = um passo de desfazer, pelo doc/store.
import { api, errorText } from '../api'
import type { CanvasElement } from '../bridge'
import type { Edit } from '../doc/store'
import { t } from '../i18n'
import { showStatus, useShell } from '../store'
import { applyEdits, docState, StoreUnavailable } from '../shell/doc'
import { confirm, message, prompt } from '../ui/dialogs'
import { openMenuAt } from '../ui/Menu'
import { chooseFromList } from '../ui/ChooseDialog'

export async function editElement(edits: Edit[], label: string): Promise<boolean> {
  try {
    await applyEdits(edits, label)
    return true
  } catch (error) {
    if (error instanceof StoreUnavailable) {
      showStatus(t('Edição indisponível: o canvas editável ainda não chegou nesta versão.'), 6)
      return false
    }
    await message('error', t('Não foi possível editar'), errorText(error))
    return false
  }
}

/** "Trocar .dds…": outro .dds da UI, uma cópia para editar ou um de outra pasta (como a clássica). */
export async function changeTexture(anchor: HTMLElement, element: CanvasElement): Promise<void> {
  const path = docState().path
  const current = element.texture ?? ''
  if (!path) return
  const info = await api.textureCopyInfo(path, current)
  const choice = await new Promise<'other' | 'copy' | 'bring' | null>((resolve) => {
    let chosen: 'other' | 'copy' | 'bring' | null = null
    openMenuAt(
      anchor,
      [
        { label: t('Usar outro .dds desta UI…'), onClick: () => (chosen = 'other') },
        { label: t('Criar cópia de {name} para editar…', { name: current }), disabled: !current || !info.exists, onClick: () => (chosen = 'copy') },
        { label: t('Trazer .dds de outra pasta…'), onClick: () => (chosen = 'bring') },
      ],
      false,
      () => resolve(chosen),
    )
  })
  if (!choice) return
  let name: string | null = null
  try {
    if (choice === 'other') {
      const names = await api.textureNames(path)
      if (!names.length) return
      name = await chooseFromList(t('Trocar .dds'), t('Textura para este controle:'), names, current)
    } else if (choice === 'copy') {
      const typed = (await prompt(t('Criar cópia do .dds'), t('Nome do novo arquivo (fica na pasta da UI):'), info.suggestion))?.trim()
      if (!typed) return
      const result = await api.copyTexture(path, current, typed)
      if (result.error === 'exists') {
        await message('warning', t('Criar cópia do .dds'), t('Já existe {name} nesta pasta.', { name: result.name }))
        return
      }
      name = result.name
    } else {
      const picked = await api.pickTexture(path)
      if (!picked) return
      if (picked.replacing && !(await confirm(t('Trazer .dds'), t('Já existe {name} nesta UI. Substituir?', { name: picked.name })))) return
      name = (await api.bringTexture(path, picked.path)).name
    }
  } catch (error) {
    await message('error', t('Trocar .dds'), errorText(error))
    return
  }
  useShell.setState((state) => ({ revision: state.revision + 1 })) // a lista de texturas mudou
  if (!name || name === current) return
  const state = docState()
  const changes: Edit[] = [{ index: element.index, field: 'texture', before: current, after: name }]
  const others = (state.doc?.elements ?? []).filter(
    (other) => other.index !== element.index && other.texture === current && !state.locked.includes(other.index),
  )
  if (
    others.length &&
    (await confirm(t('Trocar .dds'), t('Trocar também nos outros {count} controle(s) deste XML que usam {old}?', { count: others.length, old: current })))
  ) {
    changes.push(...others.map((other): Edit => ({ index: other.index, field: 'texture', before: current, after: name })))
  }
  if (await editElement(changes, t('Trocar textura de {count} controle(s)', { count: changes.length }))) {
    showStatus(t('{count} controle(s) agora usam {name}. Salve para gravar.', { count: changes.length, name }), 8)
  }
}
