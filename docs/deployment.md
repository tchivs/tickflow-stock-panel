# AthenaQuant 部署指南

本项目的几种运行方式，按推荐程度排序。配置项详解见 [configuration.md](./configuration.md)。部署验证清单（真实交易日确认项 D1..D8）见 [deploy-verification.md](./deploy-verification.md)。

> 📌 前置依赖:Python ≥ 3.11 · Node ≥ 20 · [`uv`](https://docs.astral.sh/uv/) · `pnpm`（`npm i -g pnpm`）

---

## 方式 A:Dev 模式(二次开发推荐)

开发环境适合二次开发与调试。生产运行优先使用下方的 Docker Compose 单容器方式。

```bash
git clone https://github.com/tchivs/AthenaQuant.git
cd AthenaQuant
cp .env.example .env       # 按需填 TICKFLOW_API_KEY(留空 = None 模式)
./dev.sh                   # Windows: .\dev.ps1
```

`dev.sh` 自动检查 / 下载依赖、释放端口、同时起前后端,Ctrl-C 一并关闭。默认:

- 后端 → <http://localhost:3018> · 前端 → <http://localhost:3011>
- 自定义端口:`BACKEND_PORT=8000 FRONTEND_PORT=5173 ./dev.sh`

### 手动分别启动(不想用 dev.sh)

```bash
# 后端
cd backend && uv sync --extra backtest   # 含回测依赖
uv run uvicorn app.main:app --reload --port 3018

# 前端
cd frontend && pnpm install && pnpm dev   # http://localhost:3011
```

---

## 方式 B:Docker(部署最省心)

```bash
cp .env.example .env
docker compose up --build
# 打开 http://localhost:3018
```

Docker 采用两阶段构建,前端 dist 拷进后端镜像,**单容器**运行,数据完全在自己手里。

### 可选模块

`BACKEND_EXTRAS` 控制镜像构建时安装的可选依赖，多个值以空格分隔：

```ini
BACKEND_EXTRAS=backtest shadow forecast
```

- `backtest`：安装 vectorbt 兼容层。
- `shadow`：启用 Shadow Account 研究依赖。
- `forecast`：安装本地 Forecast 推理依赖。它不会在应用启动时下载模型。
- `legacy-cpu`：为不支持 AVX2/FMA 的旧主机安装 Polars 兼容运行时。

#### 启用本地 Kronos Forecast

当前生产批准配置为 CPU 可运行的 `kronos-mini`。先在 `.env` 中设置：

```ini
BACKEND_EXTRAS=forecast
FORECAST_ENABLED=true
FORECAST_DEVICE=cpu
FORECAST_CHECKPOINT_ROOT=/app/data/forecast-checkpoints
```

显式构建、下载固定 revision、校验 SHA-256，并生成版本化 XSHG 交易日历：

```bash
docker compose build app
docker compose run --rm app /app/.venv/bin/python -m app.forecast.provision \
  --root /app/data/forecast-checkpoints
docker compose up -d
```

Provisioning 命令可重复执行；摘要一致的现有文件不会重复下载。应用启动时只接受固定 revision、`safetensors`、`local_files_only=true`、`trust_remote_code=false` 且摘要完全匹配的本地资产。任一校验失败都会保持 Forecast 不可用，不影响核心应用。

2027 覆盖采用[全国银行间同业拆借中心于 2025-12-19 发布的本币交易系统预设节假日](https://www.chinamoney.com.cn/chinese/bbjjr/20251219/3254570.html)，并与 `exchange-calendars` 的 XSHG 2010–2026 正式日历合并。该公告明确说明国务院正式通知发布后仍会调整；上交所发布 2027 年正式休市安排后，必须更新闭市日期并重新 provision。日历 revision 以 `xshg-cfets-preset-2027-` 标识，避免把预设日期误当成最终公告。

> 💡 镜像已内置 Node.js 运行时并预装 **stock-sdk** 插件依赖,Docker 部署下开箱即用,无需手动 `npm install`。

更新到新版本:

```bash
git pull
docker compose up --build -d
```

---

## 方式 C:GitHub Actions 自行构建

Fork 本仓库后，手动触发 [Release 打包工作流](https://github.com/tchivs/AthenaQuant/actions/workflows/release.yml) 自行构建桌面客户端安装包。

> ⚠️ 目前官方 Release 的安装包存在已知问题(修复中),如需桌面客户端请优先用此方式自行构建,或用上面的 Dev / Docker 方式运行。

---

## 老 CPU 兼容(avx2/fma 缺失)

如果运行时报 `avx2`/`fma` 缺失,或进程 `exit 132`,说明 CPU 不支持 AVX2 指令集(常见于老 VPS)。解决:

- **桌面客户端**:安装包已内置兼容内核,新老 CPU 通吃
- **Docker / 源码**:在 `.env` 打开 `BACKEND_EXTRAS=legacy-cpu` 后重建,会给 Polars 切到 `rtcompat` 运行时

```ini
BACKEND_EXTRAS=legacy-cpu          # 兼容老 CPU
BACKEND_EXTRAS=legacy-cpu backtest # 兼容老 CPU + 回测依赖
```

### 回测依赖说明

vectorbt → numba 体积较大,作为可选 extras(`uv sync --extra backtest`)。macOS / Intel 无预构建 wheel 时需 `brew install cmake` 现场编译。

---

## 更新、备份与恢复

升级前先备份本地数据；升级容器时保留项目根目录的 `data/` 挂载目录。完成后再拉取代码并重建镜像：

```bash
git pull
docker compose up --build -d
```

**整个 `data/` 目录都不纳入 git** —— 行情、财务、自选、回测、监控、研究工件与 operational SQLite 都是本地运行数据，`git pull` 不会覆盖它们。建议停服后归档该目录：

```bash
docker compose down
tar -czf athenaquant-data-$(date +%F).tar.gz data
```

恢复时解压回项目根目录的 `data/`，然后重新执行 `docker compose up -d`。

> ⚠️ **切勿使用以下命令"解决冲突"或"清理",它们会一次性删光 `data/` 下所有未被 git 跟踪的数据:**
> - `git clean -fdx`(最危险,会删掉所有 `.gitignore` 忽略的文件)
> - `git reset --hard`
> - 直接删除整个项目文件夹重新 `git clone`
>
> 若 `git pull` 报冲突,通常是本地误改了被跟踪的文件,请先 `git stash` 暂存再 pull,或单独联系作者,不要直接执行上面的命令。

---

## 访问密码设置(公网部署必读)

面板部署在公网服务器时,首次设置访问密码有限制 —— **必须从本机或内网访问**,以防公网上陌生人抢先设置密码锁死你的面板。

如果你在公网浏览器直接打开页面,会看到提示:

> 首次设置密码仅允许本机或内网访问,请通过 SSH/本地浏览器操作

有两种方式解决,任选其一。

### 方式一:环境变量预置密码(最简单,推荐)

在 `.env` 文件(或 Docker / 系统环境变量)里设置 `AUTH_PASSWORD`:

```bash
AUTH_PASSWORD=你的密码
```

然后重启服务。启动时会自动:

1. 读取 `AUTH_PASSWORD`
2. 用 PBKDF2 哈希后写入 `auth.json`(`chmod 600`,只存哈希不存明文)
3. **之后这个环境变量就不再被读取** —— 是一次性的初始化

设完后即可用公网地址 + 这个密码正常登录。后续改密码请用页面 UI(`设置 → 修改密码`),不受环境变量影响。

**注意事项:**

- **密码至少 6 位**,否则会被跳过并记一条 warning 日志
- **仅在未设过密码时生效**。已设过密码后,改这里不会覆盖(避免重启时重置你在 UI 改的密码)
- `.env` 文件权限保持 `600`,**不要提交到 Git**
- 明文密码只存在于 `.env` / 环境变量中,落盘的是哈希,安全性等同 `auth.json`

**重置密码(忘密码时):** 删除或清空 `data/user_data/auth.json`,重启服务,会回到"未设密码"状态,此时 `AUTH_PASSWORD` 会重新生效。

```bash
rm data/user_data/auth.json   # 停服后执行,清空后重启
```

### 方式二:SSH 端口转发

不用改配置,在你**自己电脑**的终端执行(不是服务器上):

```bash
ssh -L 3018:127.0.0.1:3018 用户名@服务器IP
```

例如服务器是 `123.45.67.89`、用户名 `root`、面板端口 `3018`:

```bash
ssh -L 3018:127.0.0.1:3018 root@123.45.67.89
```

保持这个 SSH 连接**不要关**,然后在**自己电脑的浏览器**打开 `http://127.0.0.1:3018`。此时后端看到的客户端 IP 是 `127.0.0.1`(本机),能通过校验,正常显示设置密码界面。

**设完密码后**,SSH 连接可以断开 —— 密码已存进服务器,之后直接用公网地址 + 刚设的密码访问即可。

> 如果用 `PORT` 改过端口(比如 `PORT=8080`),两处都要替换:`ssh -L 8080:127.0.0.1:8080 root@IP`。

### 两种方式怎么选

| | 环境变量 | SSH 转发 |
|---|---|---|
| 操作 | 改一行配置 + 重启 | 一条 ssh 命令 |
| 需要改配置 | 是 | 否 |
| 适合 | Docker / 自动化部署 / 不熟 SSH | 临时设密码 / 能 SSH 到服务器 |
| 后续改密码 | UI(`设置 → 修改密码`) | 同左 |

推荐**方式一(环境变量)**,一次配置即可,Docker 部署尤其方便。

### 原理说明

- **为什么限制本机/内网?** 面板部署到公网后,任何人都能访问 URL。如果不限制,攻击者可以在你之前打开页面、设置一个密码,把你的面板锁死。
- **本机/内网如何判断?** 后端检查客户端 IP 是否属于 `127.0.0.1 / ::1 / 10.x / 192.168.x / 172.16-31.x`。
- **SSH 转发为什么有效?** `-L` 把本机端口通过 SSH 隧道转发到服务器的 `127.0.0.1`,等同于在服务器本地访问,客户端 IP 变成 `127.0.0.1`,通过校验。
- **反向代理注意:** 若面板在 Nginx 等反代之后,需正确配置 `X-Forwarded-For` 头,后端据此取真实客户端 IP。
