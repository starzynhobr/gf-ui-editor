// "Como usar" (F1), a janela show_how_to da clássica: "Do projeto ao jogo em cinco passos",
// com o vídeo e os atalhos da tela inicial. Abre pelo F1, pela engrenagem e pelo Ctrl+K.
import { motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { call } from '../bridge'
import { api } from '../api'
import { t, useT } from '../i18n'
import { Modal, openDialog } from '../ui/dialogs'
import { Icon } from '../ui/Icon'

export function howToSteps(): [string, string][] {
  return [
    [
      t('Crie um projeto'),
      t(
        'Arquivo → Novo projeto. Dê um nome e escolha de onde partir: a UI em uso, uma UI da lista (UICustom/…) ou "Outra pasta…" se os seus arquivos estão em outro lugar. O editor copia os arquivos para o projeto; a pasta original não é alterada.',
      ),
    ],
    [
      t('Edite e salve'),
      t(
        'Abra um XML na aba Arquivos, mova e ajuste os elementos e salve com Ctrl+S. Cada salvamento guarda um backup: clique com o botão direito no arquivo para restaurar uma versão anterior.',
      ),
    ],
    [
      t('Envie para o jogo com F5'),
      t(
        'Salvar grava só no projeto. Enviar para o jogo (F5) copia a sua UI para a pasta do jogo e a seleciona no launcher; depois inicie o jogo pelo launcher. Se o launcher já estiver aberto, escolha a sua UI na lista dele antes de clicar em Jogar.',
      ),
    ],
    [
      t('Entenda o preview'),
      t(
        'A moldura mostra a tela do jogo na sua resolução. Algumas janelas o jogo fixa (no centro ou num canto): nelas, arraste a janela para onde o conteúdo deve aparecer e o editor ajusta o X/Y que o jogo espera.',
      ),
    ],
    [
      t('Compartilhe'),
      t('Projeto → Exportar UI (.zip) gera o pacote que outras pessoas adicionam no launcher em "Adicionar UI Customizada".'),
    ],
  ]
}

/** Os atalhos da tela inicial da clássica ("{a} novo projeto · {b} abrir projeto · {c} testar no jogo"). */
export function howToShortcuts(): [string, string][] {
  const keys: Record<string, string> = { a: 'Ctrl+Shift+N', b: 'Ctrl+Shift+O', c: 'F5' }
  const line = t('{a} novo projeto &nbsp;&nbsp;&nbsp; {b} abrir projeto &nbsp;&nbsp;&nbsp; {c} testar no jogo')
  return line
    .split(/\s*(?:&nbsp;)+\s*/)
    .map((part) => part.match(/^\{(\w)\}\s*(.*)$/))
    .filter((match): match is RegExpMatchArray => match !== null && match[1] in keys)
    .map((match) => [keys[match[1]], match[2].trim()])
}

function HowTo({ onClose }: { onClose: () => void }) {
  useT()
  const [video, setVideo] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    call<{ how_to_url?: string }>('about_info').then(
      (info) => active && setVideo(info?.how_to_url ?? null),
      () => undefined,
    )
    return () => {
      active = false
    }
  }, [])
  return (
    <Modal
      title={t('Como usar')}
      width={620}
      onClose={onClose}
      footer={
        <>
          {video && (
            <button className="btn btn-ghost mr-auto text-accent-text" data-testid="how-to-video" onClick={() => void api.openUrl(video)}>
              <Icon name="player-play" size={15} />
              {t('Ver o vídeo')}
              <Icon name="external-link" size={13} />
            </button>
          )}
          <button className="btn btn-primary" autoFocus onClick={onClose}>
            {t('Fechar')}
          </button>
        </>
      }
    >
      <div className="space-y-4 px-1 pt-1 pb-1" data-testid="how-to">
        <h2 className="text-[19px] font-semibold text-bright">{t('Do projeto ao jogo em cinco passos')}</h2>
        <ol className="space-y-3.5">
          {howToSteps().map(([heading, text], index) => (
            <motion.li
              key={index}
              className="flex gap-3.5"
              data-testid="how-to-step"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, delay: 0.06 + index * 0.05, ease: 'easeOut' }}
            >
              <span className="gf-step-badge">{index + 1}</span>
              <div className="min-w-0 flex-1 leading-relaxed">
                <div className="font-semibold text-bright">{heading}</div>
                <div className="text-text selectable">{text}</div>
              </div>
            </motion.li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3.5 text-[12.5px] text-muted" data-testid="how-to-shortcuts">
          {howToShortcuts().map(([key, label]) => (
            <span key={key} className="inline-flex items-center gap-1.5">
              <kbd className="gf-kbd">{key}</kbd>
              {label}
            </span>
          ))}
        </div>
      </div>
    </Modal>
  )
}

/** Abre o "Como usar"; se já está aberto, não abre outro. */
export function openHowTo(): void {
  if (document.querySelector('[data-testid="how-to"]')) return
  openDialog((close) => <HowTo onClose={close} />)
}
