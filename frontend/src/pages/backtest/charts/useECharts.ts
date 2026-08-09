import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'

/**
 * ECharts 实例管理 Hook — 自动初始化/resize/销毁。
 * 返回 ref 绑定到容器 div，和 setOption 方法。
 * @param ariaDescription 可选的可访问摘要; 提供时给图表容器加 role="img" + aria-label (读屏),
 *                        不提供则不触碰 aria (回退到纯 canvas 现状)。
 */
export function useECharts(
  option: EChartsOption | null,
  deps: any[] = [],
  ariaDescription?: string,
) {
  const chartRef = useRef<HTMLDivElement>(null)
  const instanceRef = useRef<ECharts | null>(null)

  // 初始化 / 销毁
  useEffect(() => {
    if (!chartRef.current) return
    const element = chartRef.current
    instanceRef.current = echarts.init(element, undefined, { renderer: 'canvas' })
    const handleResize = () => instanceRef.current?.resize()
    window.addEventListener('resize', handleResize)
    const resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(element)
    requestAnimationFrame(handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      resizeObserver.disconnect()
      instanceRef.current?.dispose()
      instanceRef.current = null
    }
  }, [])

  // 更新 option
  useEffect(() => {
    if (!instanceRef.current || !option) return
    if (ariaDescription) {
      chartRef.current?.setAttribute('role', 'img')
      chartRef.current?.setAttribute('aria-label', ariaDescription)
    } else {
      chartRef.current?.removeAttribute('role')
      chartRef.current?.removeAttribute('aria-label')
    }
    const finalOption = ariaDescription
      ? {
          ...option,
          aria: {
            enabled: true,
            label: { enabled: true, description: ariaDescription },
          },
        }
      : option
    instanceRef.current.setOption(finalOption, { notMerge: true })
  // `deps` is a deliberate escape hatch for callers whose chart data changes
  // without changing the option object identity.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [option, ariaDescription, ...deps])

  return chartRef
}
