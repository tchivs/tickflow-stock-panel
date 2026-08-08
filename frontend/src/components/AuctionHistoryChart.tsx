import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts'
import type { ECharts, EChartsOption, TooltipComponentFormatterCallbackParams } from 'echarts'
import { BarChart3 } from 'lucide-react'
import type { AuctionHistoryRow } from '@/lib/api'
import { useChartTheme, type ChartTheme } from '@/lib/theme'
import { useAuctionHistory } from '@/lib/useSharedQueries'
import { EmptyState } from '@/components/EmptyState'

interface Props {
  symbol: string
  height?: number
  className?: string
}

// 柱(量) / 线(额) 双序列颜色 —— 仅画真实列, 绝不混排派生列 (Phase 23 分组纪律)
const THEME = {
  volumeBar: 'rgba(59,130,246,0.55)',
  amountLine: '#F59E0B',
}

function fmtAxisVol(v: number): string {
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}亿股`
  if (v >= 10_000) return `${(v / 10_000).toFixed(0)}万股`
  return `${Math.round(v)}股`
}

function fmtAxisAmt(v: number): string {
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}亿元`
  if (v >= 10_000) return `${(v / 10_000).toFixed(0)}万元`
  return `${Math.round(v)}元`
}

/** 单 grid 双 yAxis: 左轴柱 = auction_volume(股), 右轴线 = auction_amount(元), x = date。 */
function buildOption(rows: AuctionHistoryRow[], ct: ChartTheme): EChartsOption {
  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: ct.crosshair, type: 'dashed', width: 1 } },
      backgroundColor: ct.tooltipBg,
      borderColor: ct.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: ct.tooltipText, fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
      // 窗口标注 (与 tooltip 数据同现)
      formatter: (params: TooltipComponentFormatterCallbackParams) => {
        const arr = Array.isArray(params) ? params : [params]
        if (arr.length === 0) return ''
        const date = String(arr[0].name ?? '')
        const lines = arr.map((p) => {
          const raw = p.value
          const v = typeof raw === 'number' ? raw : null
          const formatted = v == null ? '-' : (p.seriesName === '竞价量' ? fmtAxisVol(v) : fmtAxisAmt(v))
          return `${p.marker ?? ''}${p.seriesName ?? ''}: ${formatted}`
        })
        return [`窗口 09:15-09:25`, date, ...lines].join('<br/>')
      },
    },
    legend: {
      top: 0,
      right: 4,
      textStyle: { color: ct.text, fontSize: 10 },
      itemWidth: 14,
      itemHeight: 8,
    },
    grid: { left: 58, right: 58, top: 28, bottom: 24 },
    xAxis: {
      type: 'category',
      data: rows.map(r => r.date),
      boundaryGap: true,
      axisLine: { lineStyle: { color: ct.border } },
      axisTick: { show: false },
      axisLabel: {
        color: ct.text,
        fontSize: 9,
        fontFamily: 'JetBrains Mono, monospace',
        formatter: (v: string) => (v.length >= 10 ? v.slice(5) : v),
      },
    },
    yAxis: [
      {
        name: '竞价量',
        type: 'value',
        scale: true,
        nameTextStyle: { color: ct.text, fontSize: 10 },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: ct.text,
          fontSize: 9,
          fontFamily: 'JetBrains Mono, monospace',
          formatter: (v: number) => fmtAxisVol(Number(v)),
        },
        splitLine: { lineStyle: { color: ct.grid } },
      },
      {
        name: '竞价金额',
        type: 'value',
        scale: true,
        nameTextStyle: { color: ct.text, fontSize: 10 },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: ct.text,
          fontSize: 9,
          fontFamily: 'JetBrains Mono, monospace',
          formatter: (v: number) => fmtAxisAmt(Number(v)),
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '竞价量',
        type: 'bar',
        yAxisIndex: 0,
        data: rows.map(r => r.auction_volume),
        barMaxWidth: 24,
        itemStyle: { color: THEME.volumeBar, borderRadius: [2, 2, 0, 0] },
      },
      {
        name: '竞价金额',
        type: 'line',
        yAxisIndex: 1,
        data: rows.map(r => r.auction_amount),
        smooth: false,
        symbol: 'circle',
        symbolSize: 5,
        connectNulls: true,
        lineStyle: { width: 1.5, color: THEME.amountLine },
        itemStyle: { color: THEME.amountLine },
      },
    ],
  }
}

export function AuctionHistoryChart({ symbol, height = 320, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ECharts | null>(null)
  const roRef = useRef<ResizeObserver | null>(null)
  const ct = useChartTheme()

  // days=120 显式: 更多历史 = 更完整趋势 (服务端上限 120, 历史不可变 → 5min stale)
  const { data, isPending, isError } = useAuctionHistory(symbol, 120)

  const rows = useMemo(() => data?.rows ?? [], [data])
  // 诚实空态 D6: probe 非 available / available:false / rows 空 → 一律不画零值柱
  const showChart = !!data && data.available && data.probe.status === 'available' && rows.length > 0

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    let chart = chartRef.current
    if (!chart) {
      chart = echarts.init(el, undefined, { renderer: 'canvas' })
      chartRef.current = chart
      roRef.current = new ResizeObserver(() => chart!.resize())
      roRef.current.observe(el)
    }
    if (showChart) {
      chart.setOption(buildOption(rows, ct), true)
    } else {
      // 绝不渲染零值柱冒充真实 (D6): 空 → 清空画布
      chart.clear()
    }
  }, [showChart, rows, ct, height])

  useEffect(() => {
    return () => {
      roRef.current?.disconnect()
      chartRef.current?.dispose()
      chartRef.current = null
      roRef.current = null
    }
  }, [])

  const probeNotAvailable = data?.probe.status !== 'available'

  return (
    <div
      className={className}
      style={{ height }}
      role="img"
      aria-label="历史竞价量/金额趋势图"
    >
      {isPending && (
        <div className="text-sm text-muted py-4">加载中…</div>
      )}
      {!isPending && isError && (
        <div className="text-sm text-danger py-2">竞价历史加载失败</div>
      )}
      {!isPending && !isError && !showChart && (
        <EmptyState
          icon={BarChart3}
          title="无历史竞价数据"
          hint={probeNotAvailable
            ? '需配置集合竞价数据源 · 窗口 09:15-09:25（数据源未配置）'
            : '需配置集合竞价数据源并开启 EOD 竞价同步 · 窗口 09:15-09:25'}
        />
      )}
      {!isPending && !isError && showChart && (
        <>
          <div className="flex items-center justify-between px-1 pb-1">
            <span className="text-[10px] font-mono text-muted">柱·竞价量(股) / 线·竞价金额(元)</span>
            <span className="text-[10px] font-mono text-accent/80">窗口 09:15-09:25</span>
          </div>
          <div ref={containerRef} className="w-full" style={{ height: height - 28 }} />
        </>
      )}
    </div>
  )
}
