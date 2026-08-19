import { lazy } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Onboarding } from './pages/Onboarding'
import { Auth } from './pages/Auth'
import { useSettings } from './lib/useSharedQueries'
import { Logo } from './components/Logo'
import { ExtensionBoundary } from './extensions/ExtensionBoundary'
import {
  finalizeFrontendExtensions,
  getFrontendExtensionLoadErrors,
  getFrontendExtensionRoutes,
} from './extensions/registry'
import { NotFound } from './pages/NotFound'
// 部署重启窗口 (docker compose up -d --build) 或网络瞬断会导致路由 chunk
// 动态 import 失败, React Router 错误边界会把整页卡死在
// "Failed to fetch dynamically imported module" 且无法恢复。
// 策略: 原位重试一次; 仍失败则整页刷新一次拿最新 index.html,
// sessionStorage 标记防止刷新循环, 任一页面加载成功后清除标记。
const CHUNK_RELOAD_KEY = 'tf:chunk-reloaded'

function lazyPage<T extends { default: React.ComponentType }>(load: () => Promise<T>) {
  return lazy(async () => {
    try {
      const mod = await load()
      sessionStorage.removeItem(CHUNK_RELOAD_KEY)
      return mod
    } catch (err) {
      if (!sessionStorage.getItem(CHUNK_RELOAD_KEY)) {
        sessionStorage.setItem(CHUNK_RELOAD_KEY, '1')
        window.location.reload()
        // 刷新前的短暂间隙: 挂起 Promise, 避免错误边界闪现
        await new Promise<never>(() => {})
      }
      throw err
    }
  })
}

// 代码分割: 页面全部 lazy 加载, 避免首屏打包所有页面 (ECharts / framer-motion /
// 等重库) → 大幅减小首屏 bundle。命名导出用 .then 映射为 default。
// Layout / Onboarding / Auth 为应用外壳与入口, 保持同步加载。
const Watchlist = lazyPage(() => import('./pages/Watchlist').then(m => ({ default: m.Watchlist })))
const Screener = lazyPage(() => import('./pages/Screener').then(m => ({ default: m.Screener })))
const Backtest = lazyPage(() => import('./pages/Backtest').then(m => ({ default: m.Backtest })))
const Mining = lazyPage(() => import('./pages/Mining').then(m => ({ default: m.Mining })))
const Financials = lazyPage(() => import('./pages/Financials').then(m => ({ default: m.Financials })))
const Data = lazyPage(() => import('./pages/Data').then(m => ({ default: m.Data })))
const Portfolio = lazyPage(() => import('./pages/Portfolio').then(m => ({ default: m.Portfolio })))
const Optimization = lazyPage(() => import('./pages/portfolio/Optimization').then(m => ({ default: m.Optimization })))
const RiskAttribution = lazyPage(() => import('./pages/portfolio/RiskAttribution').then(m => ({ default: m.RiskAttribution })))
const RebalancePlan = lazyPage(() => import('./pages/portfolio/RebalancePlan').then(m => ({ default: m.RebalancePlan })))
const ModelLibrary = lazyPage(() => import('./pages/backtest/ModelLibrary').then(m => ({ default: m.ModelLibrary })))
const WalkForward = lazyPage(() => import('./pages/backtest/WalkForward').then(m => ({ default: m.WalkForward })))
const AlphaWorkbench = lazyPage(() => import('./pages/backtest/AlphaWorkbench').then(m => ({ default: m.AlphaWorkbench })))
const Monitor = lazyPage(() => import('./pages/Monitor').then(m => ({ default: m.Monitor })))
const Dashboard = lazyPage(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })))
const AnalysisDetail = lazyPage(() => import('./pages/AnalysisDetail').then(m => ({ default: m.AnalysisDetail })))
const ConceptAnalysis = lazyPage(() => import('./pages/ConceptAnalysis').then(m => ({ default: m.ConceptAnalysis })))
const PoolHubPage = lazyPage(() => import('./pages/PoolHubPage').then(m => ({ default: m.PoolHubPage })))
const IndustryAnalysis = lazyPage(() => import('./pages/IndustryAnalysis').then(m => ({ default: m.IndustryAnalysis })))
const StockAnalysis = lazyPage(() => import('./pages/StockAnalysis').then(m => ({ default: m.StockAnalysis })))
const Review = lazyPage(() => import('./pages/Review').then(m => ({ default: m.Review })))
const LimitUpLadder = lazyPage(() => import('./pages/LimitUpLadder').then(m => ({ default: m.LimitUpLadder })))
const Branding = lazyPage(() => import('./pages/Branding').then(m => ({ default: m.Branding })))
const Settings = lazyPage(() => import('./pages/Settings').then(m => ({ default: m.Settings })))
const Indices = lazyPage(() => import('./pages/Indices').then(m => ({ default: m.Indices })))
const Regime = lazyPage(() => import('./pages/Regime').then(m => ({ default: m.Regime })))
const Dev = lazyPage(() => import('./pages/Dev').then(m => ({ default: m.Dev })))

// 内置路由全集 — 前端扩展注册时据此拒绝冲突路径
const CORE_ROUTE_PATHS = new Set([
  '/',
  '/onboarding',
  '/login',
  '/overview',
  '/analysis',
  '/analysis/:menuId',
  '/concept-analysis',
  '/pool-hub',
  '/industry-analysis',
  '/stock-analysis',
  '/review',
  '/watchlist',
  '/screener',
  '/backtest',
  '/backtest/model-library',
  '/backtest/walk-forward',
  '/backtest/alpha-workbench',
  '/mining',
  '/financials',
  '/data',
  '/portfolio',
  '/portfolio/optimization',
  '/portfolio/risk-attribution',
  '/portfolio/rebalance-plan',
  '/monitor',
  '/limit-ladder',
  '/indices',
  '/regime',
  '/branding',
  '/settings',
  '/dev',
  '/settings/keys',
  '/settings/ai',
  '/settings/queries',
])

finalizeFrontendExtensions(CORE_ROUTE_PATHS)
const frontendExtensionRoutes = getFrontendExtensionRoutes()
const frontendExtensionErrors = getFrontendExtensionLoadErrors()
if (frontendExtensionErrors.length > 0) {
  console.error('部分前端扩展加载失败', frontendExtensionErrors)
}

// 首次使用守卫 —— 未完成向导则重定向到 /onboarding
// 只挂在根路由上;/onboarding 本身不被守卫,避免循环重定向。
// settings 由 Layout 预取,守卫判定不产生额外请求。
function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const settings = useSettings()

  // 仅首次加载(本地无缓存)时显示占位。
  // 后台重取 (isFetching) 时本地已有上一份缓存可用, 直接放行, 避免切页时整屏 logo 闪烁。
  // 防误重定向已由 Onboarding/AI 等处 invalidate 前的 setQueryData 同步缓存兜底。
  if (settings.isLoading) {
    return (
      <div className="min-h-screen bg-base grid place-items-center">
        <div className="flex flex-col items-center gap-3 text-muted">
          <Logo size={28} className="text-foreground" />
          <div className="text-xs">加载中…</div>
        </div>
      </div>
    )
  }

  // 查询出错或字段缺失时不拦截 —— 宁可放行,也不把用户卡在空白页
  if (settings.data && settings.data.onboarding_completed === false) {
    return <Navigate to="/onboarding" replace />
  }

  return <>{children}</>
}

export const router = createBrowserRouter([
  { path: '/onboarding', element: <Onboarding /> },
  { path: '/login', element: <Auth /> },
  {
    path: '/',
    element: (
      <OnboardingGuard>
        <Layout />
      </OnboardingGuard>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'overview', element: <Navigate to="/" replace /> },
      { path: 'analysis', element: <Navigate to="/settings?tab=ext-pages" replace /> },
      { path: 'analysis/:menuId', element: <AnalysisDetail /> },
      { path: 'concept-analysis', element: <ConceptAnalysis /> },
      { path: 'pool-hub', element: <PoolHubPage /> },
      { path: 'industry-analysis', element: <IndustryAnalysis /> },
      { path: 'stock-analysis', element: <StockAnalysis /> },
      { path: 'review', element: <Review /> },
      { path: 'watchlist', element: <Watchlist /> },
      { path: 'screener', element: <Screener /> },
      { path: 'backtest', element: <Backtest /> },
      { path: 'mining', element: <Mining /> },
      { path: 'backtest/model-library', element: <ModelLibrary /> },
      { path: 'backtest/walk-forward', element: <WalkForward /> },
      { path: 'backtest/alpha-workbench', element: <AlphaWorkbench /> },
      { path: 'financials', element: <Financials /> },
      { path: 'data', element: <Data /> },
      { path: 'portfolio', element: <Portfolio /> },
      { path: 'portfolio/optimization', element: <Optimization /> },
      { path: 'portfolio/risk-attribution', element: <RiskAttribution /> },
      { path: 'portfolio/rebalance-plan', element: <RebalancePlan /> },
      { path: 'monitor', element: <Monitor /> },
      { path: 'limit-ladder', element: <LimitUpLadder /> },
      { path: 'indices', element: <Indices /> },
      { path: 'regime', element: <Regime /> },
      { path: 'branding', element: <Branding /> },
      { path: 'settings', element: <Settings /> },
      // 隐藏路由：开发者工具（不暴露在菜单，仅供调试）
      { path: 'dev', element: <Dev /> },
      // 旧路由兼容重定向
      { path: 'settings/keys', element: <Navigate to="/settings?tab=account" replace /> },
      { path: 'settings/ai', element: <Navigate to="/settings?tab=ai" replace /> },
      { path: 'settings/queries', element: <Navigate to="/settings?tab=queries" replace /> },
      ...frontendExtensionRoutes.map(route => {
        const ExtensionPage = route.component
        return {
          path: route.path.slice(1),
          element: (
            <ExtensionBoundary extensionId={route.extensionId}>
              <ExtensionPage />
            </ExtensionBoundary>
          ),
        }
      }),
      // 未匹配路径: 友好 404 页(否则 React Router 抛出 Unexpected Application Error)
      { path: '*', element: <NotFound /> },
    ],
  },
])
