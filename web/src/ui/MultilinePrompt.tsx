// Texto de várias linhas (QInputDialog.getMultiLineText da clássica). null = cancelou.
import { useState } from 'react'
import { t, useT } from '../i18n'
import { Modal, openDialog } from './dialogs'

function Multiline({ title, label, onDone }: { title: string; label: string; onDone: (value: string | null) => void }) {
  useT()
  const [value, setValue] = useState('')
  return (
    <Modal
      title={title}
      width={560}
      onClose={() => onDone(null)}
      footer={
        <>
          <button className="btn" onClick={() => onDone(null)}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" onClick={() => onDone(value)} data-testid="multiline-ok">
            {t('OK')}
          </button>
        </>
      }
    >
      <label className="block space-y-1.5">
        <span className="text-muted">{label}</span>
        <textarea
          autoFocus
          name="multiline"
          className="field block h-40 w-full resize-y py-1.5 font-mono text-[12px]"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
    </Modal>
  )
}

export function promptMultiline(title: string, label: string): Promise<string | null> {
  return new Promise((resolve) =>
    openDialog((close) => (
      <Multiline
        title={title}
        label={label}
        onDone={(value) => {
          close()
          resolve(value)
        }}
      />
    )),
  )
}
