// Escolher um item de uma lista (QInputDialog.getItem da clássica), com filtro.
import { useMemo, useState } from 'react'
import { t, useT } from '../i18n'
import { Modal, openDialog } from './dialogs'

function Choose({
  title,
  label,
  items,
  current,
  onDone,
}: {
  title: string
  label: string
  items: string[]
  current: string
  onDone: (value: string | null) => void
}) {
  useT()
  const [filter, setFilter] = useState('')
  const [value, setValue] = useState(items.includes(current) ? current : items[0])
  const shown = useMemo(() => items.filter((item) => item.toLowerCase().includes(filter.trim().toLowerCase())), [items, filter])
  return (
    <Modal
      title={title}
      onClose={() => onDone(null)}
      footer={
        <>
          <button className="btn" onClick={() => onDone(null)}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" disabled={!value} onClick={() => onDone(value)}>
            {t('OK')}
          </button>
        </>
      }
    >
      <div className="space-y-2">
        <div className="text-muted">{label}</div>
        <input autoFocus className="field w-full" placeholder={t('Filtrar texturas…')} value={filter} onChange={(event) => setFilter(event.target.value)} />
        <div className="max-h-[320px] overflow-y-auto rounded-md border border-border bg-input py-1" role="listbox">
          {shown.map((item) => (
            <div
              key={item}
              role="option"
              aria-selected={item === value}
              className={`px-2.5 py-1 font-mono text-[12px] ${item === value ? 'bg-selected text-bright' : 'hover:bg-hover'}`}
              onClick={() => setValue(item)}
              onDoubleClick={() => onDone(item)}
            >
              {item}
            </div>
          ))}
        </div>
      </div>
    </Modal>
  )
}

export function chooseFromList(title: string, label: string, items: string[], current = ''): Promise<string | null> {
  return new Promise((resolve) => {
    openDialog((close) => (
      <Choose
        title={title}
        label={label}
        items={items}
        current={current}
        onDone={(value) => {
          close()
          resolve(value)
        }}
      />
    ))
  })
}
