// Cartão acima do canvas quando o XML aberto é avulso (de fora do projeto): diz o que é e as três
// saídas — Salvar no lugar (com backup), Importar para o projeto e Comparar — com uma linha do que
// cada uma faz. Na primeira vez, um destaque curto (coachmark) que não volta (flag na ponte).
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useRef, useState } from 'react'
import { errorText } from '../api'
import { t, useT } from '../i18n'
import { useDocState } from '../shell/doc'
import { saveDocument } from '../shell/saving'
import { setFlag, useFlag, useUi } from '../shell/uiState'
import { useShell } from '../store'
import { message } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { fileName, folderOf, useStandaloneOpen } from './standalone'
import { compareStandaloneFile, importStandaloneFile } from './standaloneActions'

export const COACH_FLAG = 'standalone_coach_seen'

export default function StandaloneBar() {
  useT()
  const path = useStandaloneOpen()
  const hasProject = useShell((state) => !!state.shell?.project)
  const docPath = useDocState((state) => (state.doc ? state.path : null))
  const coachSeen = useFlag(COACH_FLAG, false)
  const flagsLoaded = useUi((state) => state.loaded)
  const reduced = useReducedMotion()
  const [busy, setBusy] = useState(false)
  const importButton = useRef<HTMLButtonElement>(null)

  const invoke = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await action()
    } catch (error) {
      await message('error', t('Arquivo avulso'), errorText(error))
    } finally {
      setBusy(false)
    }
  }

  const disabled = busy || !path || docPath !== path
  const coach = !!path && flagsLoaded && !coachSeen
  const dismissCoach = () => setFlag(COACH_FLAG, true)
  const actions = [
    {
      id: 'save',
      icon: 'save',
      label: t('Salvar no lugar'),
      text: t('Grava no próprio arquivo e deixa uma cópia de antes ao lado dele.'),
      run: () => saveDocument(),
    },
    {
      id: 'import',
      icon: 'file-import',
      label: t('Importar para o projeto'),
      text: hasProject
        ? t('Copia para o projeto, com as texturas que faltarem. O original fica como está.')
        : t('Escolhe um projeto e copia para ele. O original fica como está.'),
      run: () => importStandaloneFile(path!, importButton.current?.getBoundingClientRect()),
    },
    {
      id: 'compare',
      icon: 'search',
      label: t('Comparar'),
      text: t('Mostra o que muda em relação ao do projeto ou ao oficial.'),
      run: () => compareStandaloneFile(path!),
    },
  ]

  return (
    <AnimatePresence initial={false}>
      {path && (
        <motion.section
          key="standalone"
          className="gf-standalone-card"
          data-testid="standalone-bar"
          aria-label={t('Arquivo avulso')}
          initial={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
          transition={{ duration: reduced ? 0.01 : 0.22, ease: 'easeOut' }}
        >
          <div className="gf-standalone-inner">
            <div className="gf-standalone-head">
              <span className="gf-standalone-icon"><Icon name="file" size={16} /></span>
              <div className="min-w-0">
                <div className="font-semibold text-bright">{t('Você está vendo um arquivo de fora do projeto')}</div>
                <div className="truncate text-[12px] text-muted" title={path}>
                  {t('{name} em {folder} · nada muda no projeto até você importar.', { name: fileName(path), folder: folderOf(path) })}
                </div>
              </div>
            </div>
            <div className={`gf-standalone-actions ${coach ? 'gf-standalone-actions-coach' : ''}`}>
              {actions.map((action) => (
                <button
                  key={action.id}
                  ref={action.id === 'import' ? importButton : undefined}
                  className="gf-standalone-action"
                  disabled={disabled}
                  data-testid={`standalone-${action.id}`}
                  onClick={() => {
                    if (coach) dismissCoach()
                    void invoke(action.run)
                  }}
                >
                  <span className="gf-standalone-action-label">
                    <Icon name={action.icon} size={14} />
                    {action.label}
                  </span>
                  <span className="gf-standalone-action-text">{action.text}</span>
                </button>
              ))}
            </div>
          </div>
          <AnimatePresence>
            {coach && (
              <motion.div
                className="gf-coachmark"
                role="note"
                data-testid="standalone-coach"
                initial={reduced ? { opacity: 0 } : { opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, delay: reduced ? 0 : 0.25 }}
              >
                <Icon name="sparkles" size={15} className="shrink-0 text-accent-text" />
                <div className="min-w-0 flex-1">
                  <span className="font-semibold text-bright">{t('Dá para editar à vontade.')}</span>{' '}
                  {t('Quando terminar, salve no próprio arquivo, traga para o projeto (para enviar com F5) ou compare antes de decidir.')}
                </div>
                <button className="btn h-7" onClick={dismissCoach} data-testid="standalone-coach-ok">{t('Entendi')}</button>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.section>
      )}
    </AnimatePresence>
  )
}
