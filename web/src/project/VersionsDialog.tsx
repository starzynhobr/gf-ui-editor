// Versões do projeto (VersionsDialog da clássica): salvar agora, restaurar (a atual é salva
// antes), criar projeto a partir de uma versão, excluir e abrir a pasta.
import { useEffect, useState } from 'react'
import { api } from '../api'
import { t, useT } from '../i18n'
import { confirm } from '../ui/dialogs'
import { Modal, openDialog } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { toolsApi, type VersionInfo } from './toolsApi'
import { projectFromVersion, restoreProjectVersion, saveProjectVersion } from './flows'
import { useListAnimation } from '../ui/animate'

function Versions({ root, name, onClose }: { root: string; name: string; onClose: () => void }) {
  useT()
  const animate = useListAnimation()
  const [list, setList] = useState<VersionInfo[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  const fill = async () => {
    const versions = await toolsApi.versions(root)
    setList(versions)
    setSelected((current) => (versions.some((version) => version.path === current) ? current : (versions[0]?.path ?? null)))
  }
  useEffect(() => {
    void fill()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root])

  const chosen = list?.find((version) => version.path === selected) ?? null
  return (
    <Modal
      title={t('Versões de {name}', { name })}
      width={660}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={async () => void api.openFolder(await toolsApi.versionsFolder(root))}>
            <Icon name="folder-open" size={15} />
            {t('Abrir pasta')}
          </button>
          <div className="flex-1" />
          <button className="btn" onClick={onClose}>
            {t('Fechar')}
          </button>
        </>
      }
    >
      <div className="space-y-3" data-testid="versions-dialog">
        <p className="text-[12.5px] leading-snug text-muted">
          {t('Cada versão guarda só o que difere da UI oficial (poucos MB). Restaurar deixa o projeto como estava; antes, a versão atual é salva sozinha, então dá para voltar.')}
        </p>
        {list && list.length === 0 ? (
          <div className="rounded-md border border-dashed border-border-strong px-3 py-4 text-muted">
            {t('Nenhuma versão ainda. Salve uma antes de testar uma ideia nova.')}
          </div>
        ) : (
          <div ref={animate} className="max-h-[300px] overflow-y-auto rounded-md border border-border bg-input">
            <div className="section-label sticky top-0 grid grid-cols-[minmax(0,1fr)_80px_80px] gap-2 bg-input px-3 py-1.5">
              <span>{t('Versão')}</span>
              <span>{t('Arquivos')}</span>
              <span>{t('Tamanho')}</span>
            </div>
            {list?.map((version) => (
              <div
                key={version.path}
                role="option"
                aria-selected={version.path === selected}
                data-testid="version-row"
                className={`grid grid-cols-[minmax(0,1fr)_80px_80px] gap-2 px-3 py-1.5 ${version.path === selected ? 'bg-selected text-bright' : 'hover:bg-hover'}`}
                onClick={() => setSelected(version.path)}
                onDoubleClick={async () => (await restoreProjectVersion(root, name, version.path)) && void fill()}
              >
                <span className="truncate">{version.title}</span>
                <span className="font-mono text-[12px] text-muted">{version.files}</span>
                <span className="font-mono text-[12px] text-muted">{version.size}</span>
              </div>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn" onClick={async () => (await saveProjectVersion(root)) && void fill()}>
            <Icon name="save" size={15} />
            {t('Salvar versão agora…')}
          </button>
          <div className="flex-1" />
          <button className="btn" disabled={!chosen} onClick={async () => chosen && (await restoreProjectVersion(root, name, chosen.path)) && void fill()}>
            {t('Restaurar')}
          </button>
          <button className="btn" disabled={!chosen} onClick={() => chosen && void projectFromVersion(root, name, chosen.path)}>
            {t('Criar projeto a partir desta…')}
          </button>
          <button
            className="btn btn-danger"
            disabled={!chosen}
            onClick={async () => {
              if (!chosen || !(await confirm(t('Excluir versão'), t('Excluir a versão {name}?', { name: chosen.title })))) return
              await toolsApi.deleteVersion(chosen.path)
              await fill()
            }}
          >
            <Icon name="trash" size={15} />
            {t('Excluir')}
          </button>
        </div>
      </div>
    </Modal>
  )
}

export function openVersionsDialog(root: string, name: string): Promise<void> {
  return new Promise((resolve) => {
    openDialog((close) => (
      <Versions
        root={root}
        name={name}
        onClose={() => {
          close()
          resolve()
        }}
      />
    ))
  })
}
