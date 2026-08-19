import { cn } from '@/lib/cn'

interface Props {
  title: string
  subtitle?: React.ReactNode
  /** 标题右侧、subtitle 之前的额外节点(如状态徽标) */
  titleExtra?: React.ReactNode
  right?: React.ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, titleExtra, right, className }: Props) {
  return (
    <header
      className={cn(
        'flex flex-col items-stretch gap-2 border-b border-border px-3 pt-2.5 pb-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-5 sm:pt-3 sm:pb-2',
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        <h1 data-phase5-typography className="shrink-0 whitespace-nowrap text-2xl font-semibold leading-[1.25] tracking-tight text-foreground">{title}</h1>
        {titleExtra && <div className="shrink-0">{titleExtra}</div>}
        {subtitle && <span className="min-w-0 truncate text-xs text-muted">{subtitle}</span>}
      </div>
      {right && (
        <div className="min-w-0 max-w-full overflow-x-auto whitespace-nowrap [scrollbar-width:none] [&::-webkit-scrollbar]:hidden max-md:[&_button]:min-h-11 max-md:[&_button]:min-w-11 sm:shrink-0">
          <div className="w-full sm:w-max">{right}</div>
        </div>
      )}
    </header>
  )
}
