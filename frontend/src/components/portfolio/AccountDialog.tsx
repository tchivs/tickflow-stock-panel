import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, Save } from 'lucide-react'
import { api, type PortfolioAccount, type PortfolioAccountInput } from '@/lib/api'
import { Modal } from '@/components/Modal'
import { toast } from '@/components/Toast'

interface AccountDialogProps {
  account?: PortfolioAccount | null
  onClose: () => void
}

type Field = 'name' | 'availableFunds'

function apiError(error: unknown) {
  const message = error instanceof Error ? error.message : '保存账户失败'
  return message.includes('account') ? '账户名称已存在或不可用。' : message
}

export function AccountDialog({ account, onClose }: AccountDialogProps) {
  const qc = useQueryClient()
  const nameRef = useRef<HTMLInputElement>(null)
  const availableFundsRef = useRef<HTMLInputElement>(null)
  const [name, setName] = useState(account?.name ?? '')
  const [availableFunds, setAvailableFunds] = useState(String(account?.available_funds ?? 0))
  const [notes, setNotes] = useState('')
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [submitError, setSubmitError] = useState('')
  const [confirmArchive, setConfirmArchive] = useState(false)

  useEffect(() => {
    setName(account?.name ?? '')
    setAvailableFunds(String(account?.available_funds ?? 0))
    setNotes('')
    setErrors({})
    setSubmitError('')
  }, [account])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['portfolio-accounts'] })
    qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
    qc.invalidateQueries({ queryKey: ['portfolio-holdings'] })
  }

  const save = useMutation({
    mutationFn: () => {
      const payload: PortfolioAccountInput = {
        name: name.trim(),
        available_funds: Number(availableFunds),
        ...(account ? { enabled: account.enabled } : {}),
      }
      return account
        ? api.portfolioUpdateAccount(account.id, payload)
        : api.portfolioCreateAccount(payload)
    },
    onSuccess: () => {
      invalidate()
      toast(account ? '账户已保存' : '账户已创建', 'success')
      onClose()
    },
    onError: error => setSubmitError(apiError(error)),
  })

  const archive = useMutation({
    mutationFn: () => api.portfolioArchiveAccount(account!.id),
    onSuccess: () => {
      invalidate()
      toast('账户已归档', 'success')
      onClose()
    },
    onError: error => setSubmitError(apiError(error)),
  })

  function validate() {
    const next: Partial<Record<Field, string>> = {}
    if (!name.trim()) next.name = '请输入账户名称。'
    const funds = Number(availableFunds)
    if (!Number.isFinite(funds) || funds < 0) next.availableFunds = '可用资金必须为非负数。'
    setErrors(next)
    const first = Object.keys(next)[0] as Field | undefined
    if (first) {
      requestAnimationFrame(() => (first === 'name' ? nameRef : availableFundsRef).current?.focus())
      return false
    }
    return true
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitError('')
    if (validate()) save.mutate()
  }

  const titleId = 'account-dialog-title'
  const fieldClass = 'h-8 w-full rounded-btn border border-border bg-base px-3 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/30'
  const mobileControl = 'max-md:min-h-11'

  return (
    <Modal
      onClose={onClose}
      labelledBy={titleId}
      panelClassName="w-[calc(100vw-2rem)] max-w-[560px] max-h-[90vh] overflow-hidden rounded-card border border-border bg-surface shadow-xl"
    >
      <form onSubmit={submit} className="flex max-h-[90vh] flex-col">
        <div className="border-b border-border px-6 py-4 max-md:px-4">
          <h2 id={titleId} className="text-base font-semibold text-foreground">{account ? '编辑账户' : '新建账户'}</h2>
        </div>
        <div className="min-h-0 space-y-4 overflow-y-auto px-6 py-5 max-md:px-4">
          <label className="block space-y-1.5" htmlFor="account-name">
            <span className="text-sm text-secondary">账户名称</span>
            <input
              ref={nameRef}
              id="account-name"
              value={name}
              onChange={event => setName(event.target.value)}
              aria-required="true"
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? 'account-name-error' : undefined}
              className={`${fieldClass} ${mobileControl}`}
            />
            {errors.name && <p id="account-name-error" className="text-xs text-danger">{errors.name}</p>}
          </label>
          <label className="block space-y-1.5" htmlFor="account-funds">
            <span className="text-sm text-secondary">可用资金</span>
            <input
              ref={availableFundsRef}
              id="account-funds"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={availableFunds}
              onChange={event => setAvailableFunds(event.target.value)}
              aria-required="true"
              aria-invalid={!!errors.availableFunds}
              aria-describedby={errors.availableFunds ? 'account-funds-error' : undefined}
              className={`${fieldClass} num ${mobileControl}`}
            />
            {errors.availableFunds && <p id="account-funds-error" className="text-xs text-danger">{errors.availableFunds}</p>}
          </label>
          <label className="block space-y-1.5" htmlFor="account-notes">
            <span className="text-sm text-secondary">备注（可选）</span>
            <textarea
              id="account-notes"
              value={notes}
              onChange={event => setNotes(event.target.value)}
              rows={3}
              className="w-full rounded-btn border border-border bg-base px-3 py-2 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
            />
          </label>
          {account && (
            <div className="flex items-center justify-between gap-3 rounded-btn border border-border bg-base px-3 py-2">
              <div>
                <p className="text-sm text-secondary">账户状态</p>
                <p className="mt-1 text-xs text-muted">{account.archived_at ? '已归档' : '默认参与汇总'}</p>
              </div>
              {!account.archived_at && (
                <button
                  type="button"
                  onClick={() => setConfirmArchive(true)}
                  className="inline-flex min-h-8 items-center gap-1.5 rounded-btn px-2 text-sm text-danger hover:bg-danger/10 max-md:min-h-11"
                >
                  <Archive className="h-4 w-4" />归档
                </button>
              )}
            </div>
          )}
          {submitError && <p role="alert" className="rounded-btn border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{submitError}</p>}
        </div>
        <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-border bg-surface px-6 py-4 max-md:px-4">
          <button type="button" onClick={onClose} className="min-h-8 rounded-btn bg-elevated px-3 text-sm text-secondary hover:text-foreground max-md:min-h-11">返回投资组合</button>
          <button type="submit" disabled={save.isPending} className="inline-flex min-h-10 items-center gap-1.5 rounded-btn bg-accent px-4 text-sm font-semibold text-white disabled:opacity-60 max-md:min-h-11">
            <Save className="h-4 w-4" />{save.isPending ? '正在保存…' : '保存账户'}
          </button>
        </div>
      </form>
      {confirmArchive && account && (
        <ArchiveConfirmation
          name={account.name}
          pending={archive.isPending}
          onCancel={() => setConfirmArchive(false)}
          onConfirm={() => archive.mutate()}
        />
      )}
    </Modal>
  )
}

function ArchiveConfirmation({ name, pending, onCancel, onConfirm }: { name: string; pending: boolean; onCancel: () => void; onConfirm: () => void }) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  return (
    <Modal onClose={onCancel} ariaLabel="确认归档账户" initialFocusRef={cancelRef} panelClassName="w-[calc(100vw-2rem)] max-w-md rounded-card border border-border bg-surface shadow-xl">
      <div className="p-6 max-md:p-4">
        <h2 className="text-base font-semibold">归档账户「{name}」？</h2>
        <p className="mt-3 text-sm leading-6 text-secondary">归档后将不再计入默认汇总；持仓、规则和告警历史会保留。</p>
        <div className="mt-5 flex justify-end gap-2">
          <button ref={cancelRef} type="button" onClick={onCancel} className="min-h-8 rounded-btn bg-elevated px-3 text-sm text-secondary max-md:min-h-11">返回投资组合</button>
          <button type="button" disabled={pending} onClick={onConfirm} className="min-h-8 rounded-btn bg-danger px-3 text-sm font-semibold text-white disabled:opacity-60 max-md:min-h-11">{pending ? '正在归档…' : '确认归档'}</button>
        </div>
      </div>
    </Modal>
  )
}
