// Limpar projeto (CleanupDialog da clássica): histórico antigo ou todo, ícones, mapas e sobras
// da cópia no jogo, com tamanhos; confirma antes de apagar.
import { useState } from 'react'
import { t, useT } from '../i18n'
import { confirm, Modal, openDialog } from '../ui/dialogs'
import { Icon } from '../ui/Icon'
import { AnimatedSize, withNodes } from '../ui/AnimatedSize'
import { humanSize, type CleanupScan } from './toolsApi'

export interface CleanupChoice {
  history: 'old' | 'all' | null
  icons: boolean
  maps: boolean
  custom: boolean
}

/** Quanto o projeto ocupa depois de limpar (a cópia no jogo não conta no total do projeto). */
export function sizeAfter(plan: CleanupScan, choice: CleanupChoice): number | null {
  if (typeof plan.total_bytes !== 'number') return null
  return Math.max(0, plan.total_bytes - chosenSize(plan, { ...choice, custom: false }))
}

export function chosenSize(plan: CleanupScan, choice: CleanupChoice): number {
  let total = choice.history === 'all' ? plan.history_all.size : choice.history === 'old' ? plan.history_old.size : 0
  if (choice.icons) total += plan.icons.size
  if (choice.maps) total += plan.maps.size
  if (choice.custom) total += plan.custom.size
  return total
}

function Cleanup({ plan, onDone }: { plan: CleanupScan; onDone: (choice: CleanupChoice | null) => void }) {
  useT()
  const [choice, setChoice] = useState<CleanupChoice>({ history: null, icons: false, maps: false, custom: false })
  const size = chosenSize(plan, choice)
  const after = sizeAfter(plan, choice)
  const anything = Boolean(choice.history || choice.icons || choice.maps || choice.custom)
  const nothing = !(plan.history_all.count || plan.icons.count || plan.maps.count || plan.custom.count)
  const set = (patch: Partial<CleanupChoice>) => setChoice((current) => ({ ...current, ...patch }))

  const clean = async () => {
    if (await confirm(t('Limpar {name}', { name: plan.name }), t('Apagar {size} de {name}? Não dá para desfazer.', { size: humanSize(size), name: plan.name }))) {
      onDone(choice)
    }
  }

  const radio = (value: 'old' | 'all' | null, label: string, disabled = false) => (
    <label className={`flex items-start gap-2 ${disabled ? 'opacity-45' : ''}`}>
      <input type="radio" name="cleanup-history" className="mt-0.5" disabled={disabled} checked={choice.history === value} onChange={() => set({ history: value })} />
      <span>{label}</span>
    </label>
  )

  return (
    <Modal
      title={t('Limpar {name}', { name: plan.name })}
      width={580}
      onClose={() => onDone(null)}
      footer={
        <>
          <button className="btn btn-danger" disabled={!anything} onClick={() => void clean()} data-testid="cleanup-confirm">
            <Icon name="trash" size={15} />
            <span>{withNodes(t('Limpar ({size})'), { size: <AnimatedSize value={size} testId="cleanup-size" /> })}</span>
          </button>
          <button className="btn" onClick={() => onDone(null)}>
            {t('Fechar')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12.5px]" data-testid="cleanup-dialog">
        <p className="text-text">
          {withNodes(
            t('O projeto ocupa {total}: arquivos da UI {ui} · histórico {history} · versões {versions}.', {
              ui: plan.ui,
              history: plan.history,
              versions: plan.versions,
            }),
            { total: <AnimatedSize value={plan.total} countUp className="font-semibold text-bright" testId="cleanup-total" /> },
          )}
        </p>
        {after !== null && (
          <p className={`text-[12px] transition-opacity duration-200 ${anything ? 'text-accent-text' : 'opacity-0'}`} aria-hidden={!anything} data-testid="cleanup-after">
            {withNodes(t('Depois de limpar, o projeto fica com {size}.'), { size: <AnimatedSize value={after} className="font-semibold" testId="cleanup-after-size" /> })}
          </p>
        )}
        {choice.custom && (
          <p className="text-[12px] text-muted" data-testid="cleanup-custom-note">
            {t('A cópia no jogo libera mais {size}; ela fica na pasta do jogo e não entra no tamanho do projeto.', { size: humanSize(plan.custom.size) })}
          </p>
        )}
        <p className="text-muted">{t('Os XMLs e as texturas que o editor desenha ficam. O que é apagado aqui não dá para desfazer.')}</p>
        <div className="space-y-1.5 pt-1">
          <div className="text-text">{t('Histórico (cópias de antes de cada salvamento)')}</div>
          {radio(null, t('Manter o histórico'))}
          {radio(
            'old',
            t('Apagar backups do histórico com mais de {days} dias ({size}, {count} arquivos)', {
              days: plan.days,
              size: humanSize(plan.history_old.size),
              count: plan.history_old.count,
            }),
            !plan.history_old.count,
          )}
          {radio(
            'all',
            t('Apagar todos os backups do histórico ({size}, {count} arquivos); os originais ficam', {
              size: humanSize(plan.history_all.size),
              count: plan.history_all.count,
            }),
            !plan.history_all.count,
          )}
        </div>
        {plan.icons.count > 0 && (
          <label className="flex items-start gap-2" title={plan.icons.left ? t('{count} ícone(s) editados ficam no projeto.', { count: plan.icons.left }) : undefined}>
            <input type="checkbox" className="mt-0.5" checked={choice.icons} onChange={(event) => set({ icons: event.target.checked })} />
            {t('Ícones do jogo iguais ao oficial (itemicon, skillicon…): {size}, {count} arquivos', { size: humanSize(plan.icons.size), count: plan.icons.count })}
          </label>
        )}
        {plan.maps.count > 0 && (
          <label className="flex items-start gap-2" title={t('Nenhum XML usa estes mapas e o jogo já tem os oficiais na pasta UI. Mapas editados ficam no projeto.')}>
            <input type="checkbox" name="cleanup-maps" className="mt-0.5" checked={choice.maps} onChange={(event) => set({ maps: event.target.checked })} />
            {t('Mapas do jogo iguais ao oficial (pasta map): {size}, {count} arquivos', { size: humanSize(plan.maps.size), count: plan.maps.count })}
          </label>
        )}
        {plan.custom.count > 0 && (
          <label className="flex items-start gap-2" title={t('Os iguais ao oficial e os que o projeto não tem mais; o próximo F5 faria o mesmo.')}>
            <input type="checkbox" className="mt-0.5" checked={choice.custom} onChange={(event) => set({ custom: event.target.checked })} />
            {t('Cópia no jogo (UICustom/{folder}): arquivos que a UI não precisa levar, {size}, {count} arquivos', {
              folder: plan.custom.folder,
              size: humanSize(plan.custom.size),
              count: plan.custom.count,
            })}
          </label>
        )}
        {nothing && <p className="text-muted">{t('Nada para limpar: o projeto já está enxuto.')}</p>}
      </div>
    </Modal>
  )
}

export function openCleanupDialog(plan: CleanupScan): Promise<CleanupChoice | null> {
  return new Promise((resolve) => {
    openDialog((close) => (
      <Cleanup
        plan={plan}
        onDone={(choice) => {
          close()
          resolve(choice)
        }}
      />
    ))
  })
}
