import { forwardRef, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Save, Search } from 'lucide-react'
import { api, type PortfolioAccount, type PortfolioPosition, type PortfolioPositionInput } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { Modal } from '@/components/Modal'
import { toast } from '@/components/Toast'

interface HoldingDialogProps {
  holding?: PortfolioPosition | null
  accounts: PortfolioAccount[]
  initialAccountId?: number
  onClose: () => void
}

type Field = 'accountId' | 'instrument' | 'costPrice' | 'quantity' | 'investedAmount'

const STYLE_OPTIONS: Array<{ value: PortfolioPositionInput['trading_style']; label: string }> = [
  { value: 'short', label: '短线' },
  { value: 'swing', label: '波段' },
  { value: 'long', label: '长线' },
]

function apiError(error: unknown) {
  const message = error instanceof Error ? error.message : '保存持仓失败'
  return message.includes('instrument already exists') ? '该账户已持有此标的。请编辑现有持仓。' : message
}

export function HoldingDialog({ holding, accounts, initialAccountId, onClose }: HoldingDialogProps) {
  const qc = useQueryClient()
  const accountRef = useRef<HTMLSelectElement>(null)
  const instrumentRef = useRef<HTMLInputElement>(null)
  const costPriceRef = useRef<HTMLInputElement>(null)
  const quantityRef = useRef<HTMLInputElement>(null)
  const investedAmountRef = useRef<HTMLInputElement>(null)
  const [accountId, setAccountId] = useState(String(holding?.account_id ?? initialAccountId ?? accounts[0]?.id ?? ''))
  const [instrument, setInstrument] = useState(holding?.instrument_symbol ?? '')
  const [query, setQuery] = useState(holding?.instrument_symbol ?? '')
  const [isResultsOpen, setResultsOpen] = useState(false)
  const [activeResult, setActiveResult] = useState(-1)
  const [costPrice, setCostPrice] = useState(String(holding?.cost_price ?? ''))
  const [quantity, setQuantity] = useState(String(holding?.quantity ?? ''))
  const [investedAmount, setInvestedAmount] = useState(String(holding?.invested_amount ?? ''))
  const [tradingStyle, setTradingStyle] = useState<PortfolioPositionInput['trading_style']>(holding?.trading_style ?? 'swing')
  const [notes, setNotes] = useState(holding?.notes ?? '')
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [submitError, setSubmitError] = useState('')
  const [confirmArchive, setConfirmArchive] = useState(false)

  useEffect(() => {
    setAccountId(String(holding?.account_id ?? initialAccountId ?? accounts[0]?.id ?? ''))
    setInstrument(holding?.instrument_symbol ?? '')
    setQuery(holding?.instrument_symbol ?? '')
    setCostPrice(String(holding?.cost_price ?? ''))
    setQuantity(String(holding?.quantity ?? ''))
    setInvestedAmount(String(holding?.invested_amount ?? ''))
    setTradingStyle(holding?.trading_style ?? 'swing')
    setNotes(holding?.notes ?? '')
    setErrors({})
    setSubmitError('')
  }, [accounts, holding, initialAccountId])

  const instrumentSearch = useQuery({
    queryKey: QK.instrumentSearch(query, 'stock,etf'),
    queryFn: () => api.instrumentSearch(query, 12, 'stock,etf'),
    enabled: query.trim().length > 0 && isResultsOpen,
    staleTime: 30_000,
  })
  const results = instrumentSearch.data?.results ?? []

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['portfolio-accounts'] })
    qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
    qc.invalidateQueries({ queryKey: ['portfolio-holdings'] })
  }

  const save = useMutation({
    mutationFn: () => {
      const payload: PortfolioPositionInput = {
        account_id: Number(accountId),
        instrument_symbol: instrument,
        cost_price: Number(costPrice),
        quantity: Number(quantity),
        invested_amount: Number(investedAmount),
        trading_style: tradingStyle,
        notes,
      }
      return holding
        ? api.portfolioUpdateHolding(holding.id, {
            instrument_symbol: payload.instrument_symbol,
            cost_price: payload.cost_price,
            quantity: payload.quantity,
            invested_amount: payload.invested_amount,
            trading_style: payload.trading_style,
            notes: payload.notes,
          })
        : api.portfolioCreateHolding(payload)
    },
    onSuccess: () => {
      invalidate()
      toast(holding ? '持仓已保存' : '持仓已添加', 'success')
      onClose()
    },
    onError: error => setSubmitError(apiError(error)),
  })

  const archive = useMutation({
    mutationFn: () => api.portfolioArchiveHolding(holding!.id),
    onSuccess: () => {
      invalidate()
      toast('持仓已归档', 'success')
      onClose()
    },
    onError: error => setSubmitError(apiError(error)),
  })

  function validate() {
    const next: Partial<Record<Field, string>> = {}
    if (!accountId) next.accountId = '请选择账户。'
    if (!instrument.trim()) next.instrument = '请选择标的。'
    const price = Number(costPrice)
    if (!Number.isFinite(price) || price < 0) next.costPrice = '成本价必须为非负数。'
    const amount = Number(investedAmount)
    if (!Number.isFinite(amount) || amount < 0) next.investedAmount = '投入金额必须为非负数。'
    const units = Number(quantity)
    if (!Number.isFinite(units) || units <= 0) next.quantity = '数量必须大于 0。'
    setErrors(next)
    const first = Object.keys(next)[0] as Field | undefined
    const refs: Record<Field, RefObject<HTMLInputElement | HTMLSelectElement>> = {
      accountId: accountRef,
      instrument: instrumentRef,
      costPrice: costPriceRef,
      quantity: quantityRef,
      investedAmount: investedAmountRef,
    }
    if (first) {
      requestAnimationFrame(() => refs[first].current?.focus())
      return false
    }
    return true
  }

  function selectInstrument(symbol: string) {
    setInstrument(symbol)
    setQuery(symbol)
    setResultsOpen(false)
    setActiveResult(-1)
    setErrors(current => ({ ...current, instrument: undefined }))
  }

  function onInstrumentKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setResultsOpen(false)
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setResultsOpen(true)
      setActiveResult(current => Math.min(current + 1, results.length - 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveResult(current => Math.max(current - 1, 0))
      return
    }
    if (event.key === 'Enter' && results.length > 0) {
      event.preventDefault()
      selectInstrument(results[Math.max(activeResult, 0)].symbol)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitError('')
    if (validate()) save.mutate()
  }

  const titleId = 'holding-dialog-title'
  const inputClass = 'h-8 w-full rounded-btn border border-border bg-base px-3 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/30'
  const errorId = (field: Field) => `holding-${field}-error`
  const describe = (field: Field) => errors[field] ? errorId(field) : undefined

  return (
    <Modal
      onClose={onClose}
      labelledBy={titleId}
      panelClassName="w-[calc(100vw-2rem)] max-w-[680px] max-h-[90vh] overflow-hidden rounded-card border border-border bg-surface shadow-xl"
    >
      <form onSubmit={submit} className="flex max-h-[90vh] flex-col">
        <div className="border-b border-border px-6 py-4 max-md:px-4">
          <h2 id={titleId} className="text-base font-semibold">{holding ? '编辑持仓' : '添加持仓'}</h2>
        </div>
        <div className="min-h-0 space-y-4 overflow-y-auto px-6 py-5 max-md:px-4">
          <label className="block space-y-1.5" htmlFor="holding-account">
            <span className="text-sm text-secondary">账户</span>
            <select
              ref={accountRef}
              id="holding-account"
              value={accountId}
              onChange={event => setAccountId(event.target.value)}
              aria-required="true"
              aria-invalid={!!errors.accountId}
              aria-describedby={describe('accountId')}
              disabled={!!holding}
              className={`${inputClass} max-md:min-h-11 disabled:opacity-60`}
            >
              {!accountId && <option value="">请选择账户</option>}
              {accounts.filter(account => !account.archived_at).map(account => <option key={account.id} value={account.id}>{account.name}</option>)}
            </select>
            {errors.accountId && <p id={errorId('accountId')} className="text-xs text-danger">{errors.accountId}</p>}
          </label>
          <div className="relative space-y-1.5">
            <label htmlFor="holding-instrument" className="block text-sm text-secondary">标的搜索</label>
            <Search className="pointer-events-none absolute left-3 top-[38px] h-4 w-4 text-muted" />
            <input
              ref={instrumentRef}
              id="holding-instrument"
              role="combobox"
              aria-expanded={isResultsOpen && results.length > 0}
              aria-controls="holding-instrument-results"
              aria-activedescendant={activeResult >= 0 ? `holding-instrument-${activeResult}` : undefined}
              aria-autocomplete="list"
              value={query}
              onFocus={() => setResultsOpen(true)}
              onChange={event => {
                setQuery(event.target.value)
                setInstrument('')
                setResultsOpen(true)
                setActiveResult(-1)
              }}
              onKeyDown={onInstrumentKeyDown}
              placeholder="输入股票或 ETF 名称、代码"
              aria-required="true"
              aria-invalid={!!errors.instrument}
              aria-describedby={describe('instrument')}
              className={`${inputClass} pl-9 max-md:min-h-11`}
            />
            {isResultsOpen && results.length > 0 && (
              <ul id="holding-instrument-results" role="listbox" className="absolute z-10 mt-1 max-h-52 w-full overflow-y-auto rounded-btn border border-border bg-surface shadow-lg">
                {results.map((result, index) => (
                  <li key={result.symbol} id={`holding-instrument-${index}`} role="option" aria-selected={index === activeResult}>
                    <button
                      type="button"
                      onMouseDown={event => event.preventDefault()}
                      onClick={() => selectInstrument(result.symbol)}
                      className={`flex min-h-9 w-full items-center gap-2 px-3 text-left text-sm hover:bg-elevated max-md:min-h-11 ${index === activeResult ? 'bg-accent/10 text-accent' : 'text-foreground'}`}
                    >
                      <span className="num shrink-0">{result.symbol}</span><span className="truncate text-secondary">{result.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {instrument && <p className="text-xs text-muted">已选择：<span className="num text-secondary">{instrument}</span></p>}
            {errors.instrument && <p id={errorId('instrument')} className="text-xs text-danger">{errors.instrument}</p>}
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <NumberField ref={costPriceRef} id="holding-cost-price" label="成本价" value={costPrice} onChange={setCostPrice} error={errors.costPrice} errorId={errorId('costPrice')} min="0" />
            <NumberField ref={quantityRef} id="holding-quantity" label="数量" value={quantity} onChange={setQuantity} error={errors.quantity} errorId={errorId('quantity')} min="0" positive />
            <NumberField ref={investedAmountRef} id="holding-invested-amount" label="投入金额" value={investedAmount} onChange={setInvestedAmount} error={errors.investedAmount} errorId={errorId('investedAmount')} min="0" />
          </div>
          <label className="block space-y-1.5" htmlFor="holding-style">
            <span className="text-sm text-secondary">交易风格</span>
            <select id="holding-style" value={tradingStyle} onChange={event => setTradingStyle(event.target.value as PortfolioPositionInput['trading_style'])} className={`${inputClass} max-md:min-h-11`}>
              {STYLE_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="block space-y-1.5" htmlFor="holding-notes">
            <span className="text-sm text-secondary">备注（可选）</span>
            <textarea id="holding-notes" value={notes} onChange={event => setNotes(event.target.value)} rows={3} className="w-full rounded-btn border border-border bg-base px-3 py-2 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/30" />
          </label>
          {holding && !holding.archived_at && (
            <div className="flex items-center justify-between gap-3 rounded-btn border border-border bg-base px-3 py-2">
              <div><p className="text-sm text-secondary">持仓状态</p><p className="mt-1 text-xs text-muted">归档后保留规则和告警历史</p></div>
              <button type="button" onClick={() => setConfirmArchive(true)} className="inline-flex min-h-8 items-center gap-1.5 rounded-btn px-2 text-sm text-danger hover:bg-danger/10 max-md:min-h-11"><Archive className="h-4 w-4" />归档</button>
            </div>
          )}
          {submitError && <p role="alert" className="rounded-btn border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{submitError}</p>}
        </div>
        <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-border bg-surface px-6 py-4 max-md:px-4">
          <button type="button" onClick={onClose} className="min-h-8 rounded-btn bg-elevated px-3 text-sm text-secondary hover:text-foreground max-md:min-h-11">返回投资组合</button>
          <button type="submit" disabled={save.isPending} className="inline-flex min-h-10 items-center gap-1.5 rounded-btn bg-accent px-4 text-sm font-semibold text-white disabled:opacity-60 max-md:min-h-11"><Save className="h-4 w-4" />{save.isPending ? '正在保存…' : '保存持仓'}</button>
        </div>
      </form>
      {confirmArchive && holding && <ArchiveConfirmation pending={archive.isPending} onCancel={() => setConfirmArchive(false)} onConfirm={() => archive.mutate()} />}
    </Modal>
  )
}

const NumberField = forwardRef<HTMLInputElement, {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string
  errorId: string
  min: string
  positive?: boolean
}>(function NumberField({ id, label, value, onChange, error, errorId, min, positive }, ref) {
  return (
    <label className="block space-y-1.5" htmlFor={id}>
      <span className="text-sm text-secondary">{label}</span>
      <input ref={ref} id={id} type="number" min={min} step="any" inputMode="decimal" value={value} onChange={event => onChange(event.target.value)} aria-required="true" aria-invalid={!!error} aria-describedby={error ? errorId : undefined} className="h-8 w-full rounded-btn border border-border bg-base px-3 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/30 num max-md:min-h-11" />
      {positive && <span className="sr-only">必须大于零</span>}
      {error && <p id={errorId} className="text-xs text-danger">{error}</p>}
    </label>
  )
})

function ArchiveConfirmation({ pending, onCancel, onConfirm }: { pending: boolean; onCancel: () => void; onConfirm: () => void }) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  return (
    <Modal onClose={onCancel} ariaLabel="确认归档持仓" initialFocusRef={cancelRef} panelClassName="w-[calc(100vw-2rem)] max-w-md rounded-card border border-border bg-surface shadow-xl">
      <div className="p-6 max-md:p-4">
        <h2 className="text-base font-semibold">归档持仓？</h2>
        <p className="mt-3 text-sm leading-6 text-secondary">归档后将不再计入默认汇总；持仓、规则和告警历史会保留。</p>
        <div className="mt-5 flex justify-end gap-2">
          <button ref={cancelRef} type="button" onClick={onCancel} className="min-h-8 rounded-btn bg-elevated px-3 text-sm text-secondary max-md:min-h-11">返回投资组合</button>
          <button type="button" disabled={pending} onClick={onConfirm} className="min-h-8 rounded-btn bg-danger px-3 text-sm font-semibold text-white disabled:opacity-60 max-md:min-h-11">{pending ? '正在归档…' : '确认归档'}</button>
        </div>
      </div>
    </Modal>
  )
}
