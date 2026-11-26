// Lista suspensa no tema do app (Radix Select). A lista do <select> nativo é desenhada pelo
// Windows e não segue o tema; esta segue, com teclado, digitar para achar e animação.
//
// Um <select> nativo escondido espelha o valor (name, value, options): scripts, testes e o
// leitor de tela continuam enxergando um select de verdade, e mudar o valor dele por script
// (evento "change") também troca a escolha aqui.
import * as RadixSelect from '@radix-ui/react-select'
import { useRef, useState } from 'react'
import { Icon } from './Icon'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

// O Radix reserva "" (limpar a escolha); valores vazios viajam com este marcador.
const EMPTY = '\u0000empty'
const toRadix = (value: string) => (value === '' ? EMPTY : value)
const fromRadix = (value: string) => (value === EMPTY ? '' : value)

export function Select({
  value,
  options,
  onChange,
  name,
  disabled,
  title,
  className = '',
  size = 'md',
  testId,
  label,
  active,
  display,
}: {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  name?: string
  disabled?: boolean
  title?: string
  className?: string
  size?: 'sm' | 'md'
  testId?: string
  /** Nome acessível (também no <select> escondido, que scripts procuram por aria-label). */
  label?: string
  /** Destaque de "ligado" (barra do canvas). */
  active?: boolean
  /** Texto do botão no lugar do item escolhido (ex.: "Tela 1024 × 768 · jogo"). */
  display?: string
}) {
  const current = options.find((option) => option.value === value)
  const wrapper = useRef<HTMLDivElement>(null)
  // Dentro de um <dialog> modal (camada do topo), a lista abre dentro dele; no body ficaria atrás.
  const [host, setHost] = useState<HTMLElement | null>(null)
  return (
    <div ref={wrapper} className={`relative min-w-0 ${className}`} title={title}>
      <RadixSelect.Root value={toRadix(value)} onValueChange={(next) => onChange(fromRadix(next))} disabled={disabled}
        onOpenChange={(open) => { if (open) setHost(wrapper.current?.closest('dialog') ?? null) }}>
        <RadixSelect.Trigger
          className={`gf-select-trigger field flex w-full items-center justify-between gap-2 text-left ${size === 'sm' ? 'h-7' : 'h-8'}`}
          data-testid={testId}
          data-active={active}
          aria-label={label ?? title}
        >
          <span className="min-w-0 truncate">
            <RadixSelect.Value placeholder="—">{display ?? current?.label ?? value}</RadixSelect.Value>
          </span>
          <RadixSelect.Icon className="gf-select-chevron shrink-0 text-muted">
            <Icon name="chevron-down" size={14} />
          </RadixSelect.Icon>
        </RadixSelect.Trigger>
        <RadixSelect.Portal container={host ?? undefined}>
          <RadixSelect.Content className="gf-select-content" position="popper" sideOffset={4} collisionPadding={8}>
            <RadixSelect.ScrollUpButton className="gf-select-scroll">
              <Icon name="chevron-down" size={13} className="rotate-180" />
            </RadixSelect.ScrollUpButton>
            <RadixSelect.Viewport className="gf-select-viewport">
              {options.map((option) => (
                <RadixSelect.Item key={option.value || EMPTY} value={toRadix(option.value)} disabled={option.disabled} className="gf-select-item">
                  <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                  <RadixSelect.ItemIndicator className="gf-select-check">
                    <Icon name="check" size={13} />
                  </RadixSelect.ItemIndicator>
                </RadixSelect.Item>
              ))}
            </RadixSelect.Viewport>
            <RadixSelect.ScrollDownButton className="gf-select-scroll">
              <Icon name="chevron-down" size={13} />
            </RadixSelect.ScrollDownButton>
          </RadixSelect.Content>
        </RadixSelect.Portal>
      </RadixSelect.Root>
      <select
        aria-hidden
        aria-label={label}
        data-active={active}
        tabIndex={-1}
        name={name}
        className="gf-select-native"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value || EMPTY} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
