#!/usr/bin/env bash
# deploy_check_connectivity.sh — DEP-01 部署日凭证/连通性前置预检 (只读)
#
# 模式:
#   probe          容器内探测 stockdb 网关连通性 — 三态裁决: reachable / auth_error / unreachable
#   md5            4 运行时文件 (main/engine/daily_pipeline/preferences) 容器内 md5 vs HEAD 对齐表
#   gate           401 门快速检查 (/health 200 ∧ 受保护端点无 cookie 401)
#   detect-gateway 动态解析 athenaquant_default 网桥网关 IP (Pitfall 7: 网关 IP 非契约, 网络删建后可能漂移)
#   help | -h      本帮助
#
# 退出码:
#   0  检查完成且通过 (probe: reachable; gate: 双通过; md5: 检查完成, 对齐与否读 JSON 裁决;
#      detect-gateway: 网关解析成功)
#   1  probe: auth_error (401 凭证错, 不重试 — StockDBAuthError 语义, 40 期契约)
#      gate: 任一不符 (health≠200 或 gate_401≠401)   md5: 无法完成 (容器/镜像不可用)
#   2  probe: unreachable (refused/timeout/网络不可达 — 检查网络形态与网关, 非凭证问题)
#   3  参数或前置错误 (docker 不可用 / 容器或镜像不存在 / 缺 LOCAL_STOCKDB_API_KEY / 参数冲突)
#
# 凭证纪律: LOCAL_STOCKDB_API_KEY 只从环境读 (缺省报错退出 3), 绝不硬编码, 输出不回显 key。
# 只读纪律: 全部探测只读 — docker exec 仅 md5/probe GET; docker run --rm 临时容器 (退出即删);
#           3018 陈旧容器为哨兵, 无写无重启无 rm; 真实替换 (compose up -d) 不在本脚本。
#
# 部署日步骤 (operator 在部署机执行; 本脚本不触碰真实 .env):
#   1) .env 追加两键 (key 值从 stockdb 容器 env STOCKDB_API_KEYS 取成员):
#        printf 'LOCAL_STOCKDB_URL=http://172.18.0.1:8000\n' >> .env
#        printf 'LOCAL_STOCKDB_API_KEY=<STOCKDB_API_KEYS 成员>\n' >> .env
#        chmod 600 .env
#   2) 加载 .env 并探测:
#        set -a; . ./.env; set +a
#        ./deploy_check_connectivity.sh probe
#   3) 三态裁决读法:
#        verdict=reachable  (code 200 + body 含 SH600519) → 连通, 继续 md5 对齐
#        verdict=auth_error (401) → key 错, 核对 STOCKDB_API_KEYS 成员后重跑, 单次不重试
#        verdict=unreachable → 检查网络形态: detect-gateway / --auto-gateway 探网关漂移;
#          备选 1 域名 http://host.docker.internal:8000 (需 compose extra_hosts:
#          ["host.docker.internal:host-gateway"] — compose 变更, operator 决策);
#          备选 2 host 网络降级评估 (改端口面/隔离, RESEARCH Alternatives 已否决为主案 — 仅记录)。
#        --base-url 覆盖已支持任一路径直测。
#
# 用法:
#   probe:   deploy_check_connectivity.sh probe [--base-url http://172.18.0.1:8000]
#            [--image <镜像>] [--network athenaquant_default] [--container <容器>]
#            [--timeout 10] [--auto-gateway]
#            LOCAL_STOCKDB_API_KEY=<key> ./deploy_check_connectivity.sh probe
#            --container 优先 (docker exec 既有运行容器); 否则 --image + --network
#            (docker run --rm 临时容器, 退出自动清理; 探测内容与镜像无关, 本地既有镜像即可)。
#            --auto-gateway: 动态探测网关拼 http://<gw>:8000 后探测 (不假设 172.18.0.1)。
#   md5:     deploy_check_connectivity.sh md5 [--image <镜像>] [--container <容器>]
#   gate:    deploy_check_connectivity.sh gate [--app-url http://127.0.0.1:3020] [--timeout 10]
#   detect-gateway: deploy_check_connectivity.sh detect-gateway [--network athenaquant_default]
#
# 判据 = 真实 200 + body 可解析 JSON + 含 SH600519 键 (非 TCP 通, Pitfall 1)。
# 401/refused/timeout 三态分类, 绝不把 401 当「连通」。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"

# 4 个运行时文件 (容器路径 /app/app/<f>; engine 在 strategy/ 下, 无 app/engine.py)
FILES=(main.py strategy/engine.py jobs/daily_pipeline.py services/preferences.py)

info() { echo "[deploy-check] $*" >&2; }
err()  { echo "[deploy-check] ERROR: $*" >&2; }

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# 前置错误 (退出码 3): 打印 JSON 后退出
die3() {
  local detail="$1"
  jq -n --arg mode "${MODE:-?}" --arg detail "$detail" --arg ts "$(ts)" \
    '{mode:$mode, verdict:"prereq_error", code:null, detail:$detail, ts:$ts}'
  exit 3
}

# ---------- probe ----------

# 容器内单行 python3 urllib 探测 (无单引号, 可直接 -c 注入; 凭证经 env 传入, 输出不回显 key)
PROBE_PY='import json,os,urllib.request,urllib.error,sys
url=os.environ["URL"];key=os.environ["LOCAL_STOCKDB_API_KEY"];timeout=int(os.environ.get("PROBE_TIMEOUT","10"))
req=urllib.request.Request(url,headers={"X-API-Key":key})
try:
 r=urllib.request.urlopen(req,timeout=timeout);body=r.read().decode("utf-8","replace");code=r.status
except urllib.error.HTTPError as e:
 body=e.read().decode("utf-8","replace");code=e.code
except Exception as e:
 print(json.dumps({"verdict":"unreachable","code":None,"has_symbol":False,"detail":type(e).__name__+": "+str(e)}));sys.exit(0)
has=False
try:
 parsed=json.loads(body);has="SH600519" in parsed
except Exception:
 parsed=None
v="unreachable"
if code==200 and has:v="reachable"
if code==401:v="auth_error"
print(json.dumps({"verdict":v,"code":code,"has_symbol":has,"detail":("ok" if v=="reachable" else body[:160])}))'

# detect-gateway 原始输出 (stdout 一行网关 IP, 失败空)
detect_gateway_raw() {
  docker network inspect "$1" --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null || true
}

run_probe() {
  local base_url="${BASE_URL:-http://172.18.0.1:8000}"
  local image="${IMAGE:-athenaquant-app:latest}"
  local network="${NETWORK:-athenaquant_default}"
  local container="${CONTAINER:-}"
  local timeout="${TIMEOUT:-10}"
  local auto_gw="${AUTO_GATEWAY:-0}"

  if [ "$auto_gw" = "1" ]; then
    [ -n "$BASE_URL" ] && die3 "--auto-gateway 与 --base-url 互斥, 请只给其一"
    local gw
    gw="$(detect_gateway_raw "$network")"
    [ -z "$gw" ] && die3 "detect-gateway 未能解析网络 $network 的网关 IP"
    base_url="http://${gw}:8000"
  fi

  local key="${LOCAL_STOCKDB_API_KEY:-}"
  if [ -z "$key" ]; then
    err "LOCAL_STOCKDB_API_KEY 未设置 — key 只从环境读 (部署日: .env 追加后 set -a; . ./.env; set +a)"
    die3 "LOCAL_STOCKDB_API_KEY 未设置"
  fi
  command -v docker >/dev/null 2>&1 || die3 "docker 不可用 (command not found)"

  local tmp_out tmp_err rc
  tmp_out="$(mktemp)"; tmp_err="$(mktemp)"
  trap 'rm -f "$tmp_out" "$tmp_err"' EXIT
  rc=0
  if [ -n "$container" ]; then
    docker exec \
      -e "URL=${base_url}/v1/quotes?symbols=SH600519" \
      -e "LOCAL_STOCKDB_API_KEY=$key" \
      -e "PROBE_TIMEOUT=$timeout" \
      "$container" python3 -c "$PROBE_PY" >"$tmp_out" 2>"$tmp_err" || rc=$?
  else
    docker run --rm --network "$network" \
      -e "URL=${base_url}/v1/quotes?symbols=SH600519" \
      -e "LOCAL_STOCKDB_API_KEY=$key" \
      -e "PROBE_TIMEOUT=$timeout" \
      "$image" python3 -c "$PROBE_PY" >"$tmp_out" 2>"$tmp_err" || rc=$?
  fi

  if [ "$rc" -ne 0 ]; then
    local detail
    detail="$(tr '\n' ' ' <"$tmp_err" | cut -c1-200)"
    jq -n --arg mode probe --arg base "$base_url" --arg detail "$detail" --arg ts "$(ts)" \
      '{mode:"probe", base_url:$base, verdict:"prereq_error", code:null, detail:$detail, ts:$ts}'
    exit 3
  fi

  local verdict code detail
  verdict="$(jq -r '.verdict' "$tmp_out")"
  code="$(jq -r '.code // null' "$tmp_out")"
  detail="$(jq -r '.detail' "$tmp_out")"
  jq -n --arg mode probe --arg base "$base_url" --arg verdict "$verdict" \
    --argjson code "$code" --arg detail "$detail" --arg ts "$(ts)" \
    '{mode:"probe", base_url:$base, verdict:$verdict, code:$code, detail:$detail, ts:$ts}'

  case "$verdict" in
    reachable)   exit 0 ;;
    auth_error)  exit 1 ;;
    unreachable) exit 2 ;;
    *)           exit 3 ;;
  esac
}

# ---------- md5 ----------

# 从 md5sum 输出文本中取指定后缀文件的 hash (行尾匹配, 防 main.py 误配 engine.py)
md5_of() { # $1 = md5sum 输出文本, $2 = 文件后缀 (如 jobs/daily_pipeline.py)
  printf '%s\n' "$1" | awk -v suf="$2" '$NF ~ ("/" suf "$") {print $1; exit}'
}

run_md5() {
  local image="${IMAGE:-athenaquant-app:preflight}"
  local container="${CONTAINER:-}"
  command -v docker >/dev/null 2>&1 || die3 "docker 不可用 (command not found)"

  local container_out rc host_md5s i f
  rc=0
  if [ -n "$container" ]; then
    container_out="$(docker exec "$container" sh -c 'md5sum /app/app/main.py /app/app/strategy/engine.py /app/app/jobs/daily_pipeline.py /app/app/services/preferences.py' 2>/dev/null)" || rc=$?
  else
    container_out="$(docker run --rm "$image" sh -c 'md5sum /app/app/main.py /app/app/strategy/engine.py /app/app/jobs/daily_pipeline.py /app/app/services/preferences.py' 2>/dev/null)" || rc=$?
  fi
  [ "$rc" -ne 0 ] && die3 "无法读取容器/镜像 $([ -n "$container" ] && echo "$container" || echo "$image") 的 md5 (检查容器是否运行 / 镜像是否存在)"

  local target
  target="$([ -n "$container" ] && echo "$container" || echo "$image")"
  local rows=""
  for f in "${FILES[@]}"; do
    local h c
    h="$(md5sum "$REPO_ROOT/backend/app/$f" 2>/dev/null | awk '{print $1}')"
    c="$(md5_of "$container_out" "$f")"
    [ -z "$c" ] && c="MISSING"
    [ -n "$rows" ] && rows+=","
    rows+="$(jq -cn --arg f "$f" --arg c "$c" --arg h "$h" '{file:$f, container_md5:$c, head_md5:$h}')"
  done

  jq -n --arg mode md5 --arg target "$target" --arg ts "$(ts)" \
    --argjson rows "[$rows]" \
    '{mode:$mode, target:$target,
      files:($rows | map(. + {match: (.container_md5 != "MISSING" and .container_md5 == .head_md5)})),
      aligned:($rows | map(.container_md5 != "MISSING" and .container_md5 == .head_md5) | all),
      match_count:($rows | map(select(.container_md5 != "MISSING" and .container_md5 == .head_md5)) | length),
      total:($rows | length), ts:$ts}'
  # 退出码 0 = 检查完成 (对齐与否读 JSON 裁决)
}

# ---------- gate ----------

run_gate() {
  local app_url="${APP_URL:-http://127.0.0.1:3020}"
  local timeout="${TIMEOUT:-10}"
  command -v curl >/dev/null 2>&1 || die3 "curl 不可用 (部署机标配)"

  local health gate401 detail
  health="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$timeout" "$app_url/health" || echo 000)"
  gate401="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$timeout" "$app_url/api/research/auction/validation" || echo 000)"

  if [ "$health" = "200" ] && [ "$gate401" = "401" ]; then
    detail="双通过: /health 200 + validation 无 cookie 401 (auth 中间件活 + 端点注册)"
  else
    detail="health=$health (期望 200) / gate_401=$gate401 (期望 401)"
  fi
  jq -n --arg mode gate --arg app_url "$app_url" --arg health "$health" \
    --arg gate401 "$gate401" --arg detail "$detail" --arg ts "$(ts)" \
    '{mode:"gate", app_url:$app_url, health:$health, gate_401:$gate401,
      verdict: (if $health == "200" and $gate401 == "401" then "pass" else "fail" end),
      detail:$detail, ts:$ts}'
  [ "$health" = "200" ] && [ "$gate401" = "401" ]
}

# ---------- detect-gateway ----------

run_detect_gateway() {
  local network="${NETWORK:-athenaquant_default}"
  local gw
  gw="$(detect_gateway_raw "$network")"
  if [ -z "$gw" ]; then
    jq -n --arg mode detect-gateway --arg network "$network" --arg ts "$(ts)" \
      '{mode:"detect-gateway", network:$network, gateway:null, ts:$ts}'
    exit 1
  fi
  jq -n --arg mode detect-gateway --arg network "$network" --arg gw "$gw" --arg ts "$(ts)" \
    '{mode:"detect-gateway", network:$network, gateway:$gw, ts:$ts}'
}

# ---------- main ----------

MODE="${1:-help}"
shift || true

BASE_URL="" IMAGE="" NETWORK="" CONTAINER="" TIMEOUT="" APP_URL="" AUTO_GATEWAY="0"
while [ $# -gt 0 ]; do
  case "$1" in
    --base-url) BASE_URL="${2:?--base-url 缺值}"; shift 2 ;;
    --image)    IMAGE="${2:?--image 缺值}"; shift 2 ;;
    --network)  NETWORK="${2:?--network 缺值}"; shift 2 ;;
    --container) CONTAINER="${2:?--container 缺值}"; shift 2 ;;
    --timeout)  TIMEOUT="${2:?--timeout 缺值}"; shift 2 ;;
    --app-url)  APP_URL="${2:?--app-url 缺值}"; shift 2 ;;
    --auto-gateway) AUTO_GATEWAY="1"; shift ;;
    *) err "未知参数: $1"; exit 3 ;;
  esac
done

case "$MODE" in
  probe)          run_probe ;;
  md5)            run_md5 ;;
  gate)           run_gate ;;
  detect-gateway) run_detect_gateway ;;
  help|-h|--help) sed -n '2,60p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) err "未知模式: $MODE (probe | md5 | gate | detect-gateway | help)"; exit 3 ;;
esac
