// Diff unificado antes de gravar (salvar XML, restaurar versão), com cores por linha.
import { t, useT } from '../i18n'
import { Modal, openDialog } from './dialogs'

function lineClass(line: string): string {
  if (line.startsWith('+++') || line.startsWith('---')) return 'text-muted'
  if (line.startsWith('@@')) return 'text-accent-text'
  if (line.startsWith('+')) return 'bg-success/10 text-success'
  if (line.startsWith('-')) return 'bg-danger/10 text-danger'
  return 'text-text'
}

function Diff({
  title,
  explanation,
  diff,
  confirm,
  onDone,
}: {
  title: string
  explanation: string
  diff: string
  confirm: string
  onDone: (accepted: boolean) => void
}) {
  useT()
  return (
    <Modal
      title={title}
      width={980}
      onClose={() => onDone(false)}
      footer={
        <>
          <button className="btn" onClick={() => onDone(false)}>
            {t('Cancelar')}
          </button>
          <button className="btn btn-primary" autoFocus onClick={() => onDone(true)} data-testid="diff-confirm">
            {confirm}
          </button>
        </>
      }
    >
      <div className="space-y-2.5">
        <div className="text-muted">{explanation}</div>
        <pre
          className="selectable max-h-[56vh] overflow-auto rounded-md border border-border bg-input py-2 font-mono text-[12px] leading-[1.45]"
          data-testid="diff"
        >
          {diff.split('\n').map((line, index) => (
            <div key={index} className={`px-3 whitespace-pre ${lineClass(line)}`}>
              {line || ' '}
            </div>
          ))}
        </pre>
      </div>
    </Modal>
  )
}

export function openDiffDialog(options: { title: string; explanation: string; diff: string; confirm: string }): Promise<boolean> {
  return new Promise((resolve) => {
    openDialog((close) => (
      <Diff
        {...options}
        onDone={(accepted) => {
          close()
          resolve(accepted)
        }}
      />
    ))
  })
}
