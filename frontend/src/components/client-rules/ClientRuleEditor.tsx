/**
 * ClientRuleEditor — 客户端规则编辑器表单 (D-01, D-04, D-05)
 *
 * 参照 RuleEditor.tsx 的 draft 模式 + Card 表单布局, 但不复用其逻辑。
 * - 规则名称 + 标的代码 + 规则类型 (pct/price) + 操作符 + 阈值 + 启用开关
 * - pct 类型阈值: 用户输入百分数 (如 3.66), 存储为小数 (0.0366)
 * - 首次创建规则时请求 Notification 权限 (D-05)
 * - 弹窗模式: 固定底部 action 按钮区
 */

import { useState } from 'react'
import { X, Save, Smartphone } from 'lucide-react'
import { useClientRules } from '@/hooks/useClientRulesEngine'
import type { ClientRule } from '@/lib/clientRules'

interface Props {
  /** 编辑现有规则; null=新建 */
  rule: ClientRule | null
  onClose: () => void
  onSave: (rule: Omit<ClientRule, 'id' | 'createdAt'> | ClientRule) => void
}

const OP_OPTIONS: Array<{ value: ClientRule['op']; label: string }> = [
  { value: '>', label: '>' },
  { value: '<', label: '<' },
  { value: '>=', label: '≥' },
  { value: '<=', label: '≤' },
]

const TYPE_OPTIONS: Array<{ value: ClientRule['type']; label: string }> = [
  { value: 'pct', label: '涨跌幅 %' },
  { value: 'price', label: '绝对价格' },
]

const INPUT_CLS =
  'h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60'
const LABEL_CLS = 'block text-[11px] text-muted mb-1'

export function ClientRuleEditor({ rule, onClose, onSave }: Props) {
  const { requestPermission } = useClientRules()

  const [name, setName] = useState(rule?.name ?? '')
  const [symbol, setSymbol] = useState(rule?.symbol ?? '')
  const [type, setType] = useState<'pct' | 'price'>(rule?.type ?? 'pct')
  const [op, setOp] = useState<ClientRule['op']>(rule?.op ?? '>')
  const [value, setValue] = useState<string>(
    rule ? String(rule.type === 'pct' ? rule.value * 100 : rule.value) : '',
  )
  const [enabled, setEnabled] = useState(rule?.enabled ?? true)
  const [error, setError] = useState('')

  const handleSave = () => {
    const trimmedName = name.trim()
    const trimmedSymbol = symbol.trim()
    const numValue = parseFloat(value)

    if (!trimmedName) {
      setError('请输入规则名称')
      return
    }
    if (!trimmedSymbol) {
      setError('请输入标的代码')
      return
    }
    if (Number.isNaN(numValue) || !Number.isFinite(numValue)) {
      setError('阈值必须是有效数字')
      return
    }

    // pct 类型: 用户输入百分数 → 存储为小数
    const storedValue = type === 'pct' ? numValue / 100 : numValue

    // 首次创建规则时请求 Notification 权限 (D-05)
    // 权限被拒不阻断保存, 仅降级为 toast + 声效
    if (rule === null) {
      requestPermission()
    }

    onSave({
      ...(rule ?? {}),
      name: trimmedName,
      symbol: trimmedSymbol,
      type,
      op,
      value: storedValue,
      enabled,
    })
  }

  return (
    <div className="flex flex-col rounded-card border border-border bg-surface shadow-lg max-w-md w-full">
      {/* 标题栏 */}
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Smartphone className="h-4 w-4 text-purple-500" />
          <h2 className="text-sm font-semibold text-foreground">
            {rule ? '编辑客户端规则' : '新建客户端规则'}
          </h2>
          <span className="rounded bg-purple-500/10 px-1 py-px text-[9px] font-medium text-purple-500">客户端</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md text-muted hover:bg-elevated hover:text-foreground cursor-pointer max-md:min-h-11 max-md:min-w-11"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 表单 */}
      <div className="space-y-3 p-4">
        <div>
          <label className={LABEL_CLS}>规则名称</label>
          <input
            value={name}
            onChange={e => { setName(e.target.value); setError('') }}
            placeholder="如: 茅台涨超3%"
            className={INPUT_CLS}
          />
        </div>

        <div>
          <label className={LABEL_CLS}>标的代码</label>
          <input
            value={symbol}
            onChange={e => { setSymbol(e.target.value); setError('') }}
            placeholder="如: 600519.SH"
            className={INPUT_CLS + ' font-mono'}
          />
        </div>

        <div className="flex gap-2">
          <div className="flex-1">
            <label className={LABEL_CLS}>规则类型</label>
            <select
              value={type}
              onChange={e => { setType(e.target.value as 'pct' | 'price'); setError('') }}
              className={INPUT_CLS}
            >
              {TYPE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="w-20">
            <label className={LABEL_CLS}>操作符</label>
            <select
              value={op}
              onChange={e => setOp(e.target.value as ClientRule['op'])}
              className={INPUT_CLS}
            >
              {OP_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className={LABEL_CLS}>
            阈值{type === 'pct' ? ' (百分数)' : ''}
          </label>
          <div className="relative">
            <input
              type="number"
              value={value}
              onChange={e => { setValue(e.target.value); setError('') }}
              placeholder={type === 'pct' ? '3.66 表示 3.66%' : '100.00'}
              step={type === 'pct' ? '0.01' : '0.01'}
              className={INPUT_CLS + ' pr-8'}
            />
            {type === 'pct' && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">%</span>
            )}
          </div>
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={e => setEnabled(e.target.checked)}
            className="h-3.5 w-3.5 accent-accent cursor-pointer"
          />
          <span className="text-xs text-foreground">启用此规则</span>
        </label>

        {error && (
          <div className="text-[11px] text-danger">{error}</div>
        )}
      </div>

      {/* 底部操作区 */}
      <div className="flex items-center justify-end gap-2 border-t border-border/60 px-4 py-3">
        <button
          onClick={onClose}
          className="px-3 py-1.5 rounded-btn text-xs font-medium text-secondary hover:bg-elevated hover:text-foreground transition-colors cursor-pointer max-md:min-h-11 max-md:min-w-11"
        >
          取消
        </button>
        <button
          onClick={handleSave}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-btn bg-accent text-base text-xs font-medium hover:bg-accent/90 transition-colors cursor-pointer max-md:min-h-11 max-md:min-w-11"
        >
          <Save className="h-3.5 w-3.5" />
          保存
        </button>
      </div>
    </div>
  )
}
