// "Novo projeto de UI": nome, pasta do jogo, origem (UI do jogo, UICustom, outra pasta ou
// .zip), pasta de envio, ícones e XMLs soltos. Mesmas regras do NewProjectDialog da clássica
// (calculadas no Python: new_project.py).
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, errorText, type NewProjectForm, type PublishTarget, type ShellState } from '../api'
import { t, useT } from '../i18n'
import { useShell } from '../store'
import { message, Modal, openDialog } from '../ui/dialogs'

type Created = { count: number; state: ShellState }

const PICK_FOLDER = '?folder'
const PICK_ZIP = '?zip'

interface SourceOption {
  label: string // "UI", "UICustom/x" ou o caminho escolhido
  path: string
}

function NewProjectDialog({
  looseDir,
  focus,
  onDone,
}: {
  looseDir: string | null
  focus: string | null
  onDone: (created: Created | null) => void
}) {
  useT()
  const [form, setForm] = useState<NewProjectForm | null>(null)
  const [name, setName] = useState('')
  const [nameMissing, setNameMissing] = useState(false)
  const [gameDir, setGameDir] = useState<string | null>(null)
  const [picked, setPicked] = useState<SourceOption[]>([])
  const [source, setSource] = useState('')
  const [targets, setTargets] = useState<PublishTarget[]>([])
  const [target, setTarget] = useState('')
  const [includeAssets, setIncludeAssets] = useState(false)
  const [includeLoose, setIncludeLoose] = useState(true)
  const [busy, setBusy] = useState(false)
  const nameInput = useRef<HTMLInputElement>(null)

  const load = async (dir?: string | null) => {
    const data = await api.newProjectForm(dir, looseDir)
    setForm(data)
    setGameDir(data.game_dir)
    setSource((current) => (current && !data.sources.length ? current : (data.default_source ?? '')))
  }
  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const options: SourceOption[] = useMemo(() => [...(form?.sources ?? []), ...picked], [form, picked])
  const sourceLabel = options.find((option) => option.path === source)?.label ?? ''

  useEffect(() => {
    let alive = true
    void api.newProjectTargets(name, sourceLabel, gameDir).then((list) => {
      if (!alive) return
      setTargets(list)
      setTarget((current) => (list.some((item) => item.value === current) ? current : ''))
    })
    return () => {
      alive = false
    }
  }, [name, sourceLabel, gameDir])

  const chooseSource = async (value: string) => {
    if (value !== PICK_FOLDER && value !== PICK_ZIP) {
      setSource(value)
      const label = options.find((option) => option.path === value)?.label ?? ''
      if (label.startsWith('UICustom/') && !name.trim()) setName(label.slice('UICustom/'.length))
      return
    }
    const chosen = await api.pickSource(value === PICK_FOLDER ? 'folder' : 'zip')
    if (!chosen) return
    setPicked((current) => (current.some((item) => item.path === chosen.path) ? current : [...current, { label: chosen.path, path: chosen.path }]))
    setSource(chosen.path)
    if (!name.trim()) setName(chosen.suggested_name)
  }

  const changeGameDir = async () => {
    const chosen = await api.pickGameDir(gameDir)
    if (chosen) await load(chosen)
  }

  const submit = async () => {
    if (!source) {
      await chooseSource(PICK_FOLDER)
      return
    }
    if (!name.trim()) {
      setNameMissing(true)
      nameInput.current?.focus()
      return
    }
    setBusy(true)
    useShell.setState({ progress: { label: t('Copiando a UI para o projeto (para o jogo só vai o que você alterar)…'), done: 0, total: 0 } })
    try {
      const result = await api.createProject({
        name: name.trim(),
        source,
        game_dir: gameDir,
        include_assets: includeAssets,
        publish_folder: target,
        loose_dir: form?.loose_files.length ? looseDir : null,
        include_loose: includeLoose,
        focus,
      })
      if ('error' in result) {
        await message('warning', t('Projeto já existe'), t('Já existe um projeto em {path}.', { path: result.path }))
        return
      }
      onDone(result)
    } catch (error) {
      await message('error', t('Não foi possível criar o projeto'), errorText(error))
    } finally {
      useShell.setState({ progress: null })
      setBusy(false)
    }
  }

  const selectedTarget = targets.find((item) => item.value === target)
  const warning = selectedTarget?.warning
  const warningText = !warning
    ? ''
    : warning[0] === 'shared'
      ? t('O projeto {projects} também envia para UICustom/{folder}: um vai sobrescrever o outro no jogo.', warning[1])
      : t('UICustom/{folder} já existe: Enviar para o jogo vai atualizar os arquivos dela.', warning[1])

  const row = 'grid grid-cols-[150px_1fr] items-center gap-3'
  return (
    <Modal
      title={t('Novo projeto de UI')}
      width={600}
      onClose={() => !busy && onDone(null)}
      footer={
        <>
          <button className="btn" disabled={busy} onClick={() => onDone(null)}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" disabled={busy || !form} onClick={() => void submit()} data-testid="create-project">
            {t('Criar projeto')}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div className={row}>
          <span className="text-muted">{t('Nome')}</span>
          <input
            ref={nameInput}
            autoFocus
            name="project-name"
            className={`field ${nameMissing && !name.trim() ? 'border-warning-border' : ''}`}
            placeholder={nameMissing ? t('Dê um nome ao projeto') : t('Ex.: UI-Hero ajustada')}
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && void submit()}
          />
        </div>
        <div className={row}>
          <span className="text-muted">{t('Pasta do jogo')}</span>
          <div className="flex gap-2">
            <input readOnly className="field min-w-0 flex-1" placeholder={t('Não definida')} value={gameDir ?? ''} title={gameDir ?? ''} />
            <button className="btn" onClick={() => void changeGameDir()}>
              {t('Alterar…')}
            </button>
          </div>
        </div>
        {form?.game_dir_warning && (
          <div className="ml-[162px] hint-warning">
            {t('Esta pasta não parece ser a do jogo: escolha a pasta que tem o client.ini e as pastas UI e UICustom.')}
          </div>
        )}
        <div className={row}>
          <span className="text-muted">{t('Começar a partir de')}</span>
          <select
            name="project-source"
            className="field"
            value={source || PICK_FOLDER}
            onChange={(event) => void chooseSource(event.target.value)}
          >
            {!source && <option value="">—</option>}
            {options.map((option) => (
              <option key={option.path} value={option.path}>
                {option.label === 'UI' ? t('UI em uso no jogo (pasta UI)') : option.label}
              </option>
            ))}
            <option value={PICK_FOLDER}>{t('Outra pasta…')}</option>
            <option value={PICK_ZIP}>{t('Arquivo .zip…')}</option>
          </select>
        </div>
        <div className={row}>
          <span className="text-muted">{t('Enviar para')}</span>
          <select
            className="field"
            value={target}
            title={t('Pasta de UICustom que Enviar para o jogo atualiza; é a UI que você escolhe no launcher.')}
            onChange={(event) => setTarget(event.target.value)}
          >
            {targets.map((item) => (
              <option key={item.value || '-own'} value={item.value}>
                {item.value
                  ? t('UICustom/{name} (atualiza a UI de origem)', { name: item.folder })
                  : t('UICustom/{name} (pasta própria do projeto)', { name: item.folder || t('nome do projeto') })}
              </option>
            ))}
          </select>
        </div>
        {warningText && <div className="ml-[162px] hint-warning">{warningText}</div>}
        <label
          className="flex items-center gap-2 pt-1"
          title={t('Pastas itemicon, skillicon, uiicon e loadingframe. Marque só se for editar esses ícones; deixa a cópia e o teste mais lentos.')}
        >
          <input type="checkbox" checked={includeAssets} onChange={(event) => setIncludeAssets(event.target.checked)} />
          {t('Incluir ícones de itens, skills e telas de carregamento (~18 mil arquivos)')}
        </label>
        {form && form.loose_files.length > 0 && (
          <label className="flex items-center gap-2" title={form.loose_files.join('\n')}>
            <input type="checkbox" checked={includeLoose} onChange={(event) => setIncludeLoose(event.target.checked)} />
            {t('Trazer os {count} XML de {folder} (substituem os de mesmo nome)', {
              count: form.loose_files.length,
              folder: form.loose_dir ?? '',
            })}
          </label>
        )}
        <p className="pt-1 text-[12px] leading-relaxed text-muted">
          {t(
            'Os arquivos serão copiados para {root}. Backups e cópias antigas ficam de fora; a pasta do jogo não é alterada até você usar Enviar para o jogo.',
            { root: form?.projects_root ?? '' },
          )}
        </p>
      </div>
    </Modal>
  )
}

/** Abre o diálogo; resolve com o projeto criado (já aberto no Python) ou null. */
export function openNewProjectDialog(looseDir: string | null, focus: string | null): Promise<Created | null> {
  return new Promise((resolve) => {
    openDialog((close) => (
      <NewProjectDialog
        looseDir={looseDir}
        focus={focus}
        onDone={(created) => {
          close()
          resolve(created)
        }}
      />
    ))
  })
}
