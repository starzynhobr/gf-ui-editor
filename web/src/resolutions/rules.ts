// Onde cada pedaço fica, em frase curta e sem jargão (lista da tela e testes).
import { t } from '../i18n'
import type { PieceInfo, WindowInfo } from './resolutionsApi'

/** Frase curta para onde o pedaço fica (sem jargão). */
export function ruleText(piece: PieceInfo, kind: WindowInfo['kind']): string {
  if (piece.adjusted) return t('você ajustou')
  const [h, v] = piece.rule
  if (h === 'game' || kind === 'unknown') return t('fica onde o jogo põe')
  if (h === 'middle' && v === 'middle') return t('fica no meio')
  if (h === 'start' && v === 'start') return t('fica no canto de cima, à esquerda')
  if (h === 'end' && v === 'start') return t('fica no canto de cima, à direita')
  if (h === 'start' && v === 'end') return t('fica no canto de baixo, à esquerda')
  if (h === 'end' && v === 'end') return t('fica no canto de baixo, à direita')
  if (h === 'middle') return v === 'start' ? t('fica em cima, no meio') : t('fica embaixo, no meio')
  return h === 'start' ? t('fica na esquerda, na altura do meio') : t('fica na direita, na altura do meio')
}
