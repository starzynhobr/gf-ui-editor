// Menu suspenso (botão ⋯, engrenagem, projeto, botão direito). Fecha ao clicar fora ou Esc.
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { create } from 'zustand'
import { Icon } from './Icon'

export interface MenuItem {
  label?: string
  icon?: string
  onClick?: () => void
  disabled?: boolean
  checked?: boolean
  danger?: boolean
  hint?: string
  separator?: boolean
  submenu?: MenuItem[]
  title?: string
}

interface OpenMenu {
  x: number
  y: number
  items: MenuItem[]
  /** Alinha pela direita do ponto (menus abertos de botões no canto direito). */
  alignRight?: boolean
}

const useMenu = create<{ menu: OpenMenu | null }>(() => ({ menu: null }))

export function openMenu(menu: OpenMenu): void {
  useMenu.setState({ menu })
}

/** Abre o menu logo abaixo do elemento clicado. */
export function openMenuAt(element: HTMLElement, items: MenuItem[], alignRight = false): void {
  const rect = element.getBoundingClientRect()
  openMenu({ x: alignRight ? rect.right : rect.left, y: rect.bottom + 4, items, alignRight })
}

export function closeMenu(): void {
  useMenu.setState({ menu: null })
}

function MenuList({ items, x, y, alignRight }: OpenMenu) {
  const ref = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ left: x, top: y })
  const [sub, setSub] = useState<{ index: number; x: number; y: number } | null>(null)
  useLayoutEffect(() => {
    const box = ref.current?.getBoundingClientRect()
    if (!box) return
    let left = alignRight ? x - box.width : x
    let top = y
    if (left + box.width > window.innerWidth - 8) left = window.innerWidth - box.width - 8
    if (top + box.height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - box.height - 8)
    setPosition({ left: Math.max(8, left), top })
  }, [x, y, alignRight])
  return (
    <div
      ref={ref}
      role="menu"
      className="fixed z-[60] min-w-[200px] rounded-lg border border-border-strong bg-menu py-1 shadow-xl shadow-black/40"
      style={position}
      onMouseDown={(event) => event.stopPropagation()}
    >
      {items.map((item, index) =>
        item.separator ? (
          <div key={index} className="my-1 h-px bg-border" />
        ) : item.title ? (
          <div key={index} className="px-3 pb-1 pt-2 text-[11px] font-semibold tracking-wide text-muted uppercase">
            {item.title}
          </div>
        ) : (
          <button
            key={index}
            role="menuitem"
            disabled={item.disabled}
            className={`flex w-full items-center gap-2.5 px-3 py-1.5 text-left disabled:opacity-40 enabled:hover:bg-hover ${
              item.danger ? 'text-danger' : 'text-text'
            } ${sub?.index === index ? 'bg-hover' : ''}`}
            onMouseEnter={(event) => {
              if (item.submenu) {
                const rect = event.currentTarget.getBoundingClientRect()
                setSub({ index, x: rect.right + 2, y: rect.top - 5 })
              } else setSub(null)
            }}
            onClick={(event) => {
              if (item.submenu) {
                const rect = event.currentTarget.getBoundingClientRect()
                setSub({ index, x: rect.right + 2, y: rect.top - 5 })
                return
              }
              closeMenu()
              item.onClick?.()
            }}
          >
            <span className="flex w-4 justify-center">
              {item.checked ? <Icon name="check" size={14} className="text-accent-text" /> : item.icon ? <Icon name={item.icon} size={15} /> : null}
            </span>
            <span className="flex-1">{item.label}</span>
            {item.hint && <span className="font-mono text-[11px] text-muted">{item.hint}</span>}
            {item.submenu && <Icon name="chevron-right" size={14} className="text-muted" />}
          </button>
        ),
      )}
      {sub && items[sub.index]?.submenu && <MenuList items={items[sub.index].submenu!} x={sub.x} y={sub.y} />}
    </div>
  )
}

export function MenuHost(): ReactNode {
  const menu = useMenu((state) => state.menu)
  useEffect(() => {
    if (!menu) return
    const close = () => closeMenu()
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && closeMenu()
    window.addEventListener('mousedown', close)
    window.addEventListener('blur', close)
    window.addEventListener('resize', close)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('blur', close)
      window.removeEventListener('resize', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [menu])
  return menu ? <MenuList {...menu} /> : null
}
