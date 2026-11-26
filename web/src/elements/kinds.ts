// Rótulo traduzido do tipo do controle (o mesmo de i18n.kind_label da clássica).
import { t } from '../i18n'

export function kindLabel(kind: string, ctrlType: string | null): string {
  switch (kind) {
    case 'multiline_text':
      return t('Texto multilinha')
    case 'text_field':
      return t('Campo de texto')
    case 'button':
      return t('Botão')
    case 'text':
      return t('Texto')
    case 'slot':
      return t('Slot')
    case 'progress':
      return t('Progresso')
    case 'slider':
      return t('Controle deslizante')
    case 'image':
      return t('Imagem')
    case 'panel':
      return t('Painel')
    case 'window':
      return t('Janela')
    case 'control':
      return t('Controle {number}', { number: ctrlType ?? '?' })
    default:
      return kind
  }
}

/** FontColor do XML é um inteiro BGR do Windows (65535 = amarelo). */
export function gameColorToHex(value: string | undefined): string {
  const parsed = Number.parseInt(value ?? '', 10)
  const number = Number.isFinite(parsed) ? parsed : 0xffffff
  const [r, g, b] = [number & 0xff, (number >> 8) & 0xff, (number >> 16) & 0xff]
  return `#${[r, g, b].map((part) => part.toString(16).padStart(2, '0')).join('')}`
}

export function hexToGameColor(hex: string): string {
  const value = Number.parseInt(hex.replace('#', ''), 16)
  const [r, g, b] = [(value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff]
  return String(r | (g << 8) | (b << 16))
}

/** Campos de fonte editáveis: FONT_FIELDS do xml_document que o controle tem no XML. */
export const FONT_FIELDS = ['FontColor', 'FontStyle', 'TextAlign', 'FontSize'] as const
