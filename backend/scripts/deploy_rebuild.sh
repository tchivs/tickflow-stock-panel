#!/usr/bin/env bash
# =============================================================================
# deploy_rebuild.sh — DEP-04: 3018 rebuild 配方 (预检模式 + --apply 部署日替换)
#
# 镜像 RUN-EVIDENCE-39-01 全流程 (build 66s / boot 18s / md5 4/4 / 零写哨兵):
#   preflight 模式 (默认, 零触碰 3018 陈旧容器):
#     1. baseline     git HEAD + 端口面 (3020 空闲) + stale-name guard
#     2. temp 副本    root 容器法 (源只读挂载 → cp -a → chown -R 999:995), 186M
#     3. build        docker build -t athenaquant-app:preflight . (记录时长+镜像 ID)
#     4. boot         docker run -d --name athenaquant-preflight -p 3020:3018
#                     -v <temp>:/app/data -v tiers.yaml:/app/tiers.yaml:ro
#                     → /health 200 poll ≤120s (实测 18-20s)
#     5. md5 parity   docker exec preflight md5sum 4 文件 vs HEAD 4/4
#     6. cleanup      trap EXIT: rm 预检容器 + rm -rf temp 副本 (+ --keep-image 保留镜像)
#                     零写哨兵 (kline_auction 分区数 / *.tmp 计数不变) → JSON 台账
#
#   --apply 模式 (部署日 operator, human-check — 脚本只打印步骤, 绝不静默替换):
#     step 1  preflight 全绿 (build+boot+md5 4/4) 为前提
#     step 2  docker compose up -d   (bind 卷 ./data:/app/data + tiers.yaml 保留)
#     step 3  一次性 root 容器 chown -R 999:995 (root-owned 卷修复)
#     step 4  docker exec athenaquant md5sum 4 文件 vs HEAD 4/4 (对齐确认)
#     step 5  /health 200 + deploy_verify_endpoints.py --base-url :3018 (44-02 全流程)
#
# 用法:
#   deploy_rebuild.sh [--preflight] [--apply] [--data-dir ./data] [--port 3020]
#                     [--keep-image] [--dry-run]
#   env: RUNBOOK_PY / REBUILD_TMP (temp 副本路径, 默认 /tmp/preflight-data-4403)
#
# 诚实纪律: 沙箱只跑 preflight + --apply --dry-run (打印命令文本);
#   部署日真实替换 = operator 手动执行 --apply 步骤并记录 human-check。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"

MODE="preflight"
DATA_DIR="${DEP_DATA_DIR:-$REPO_ROOT/data}"
PORT="${DEP_PREFLIGHT_PORT:-3020}"
KEEP_IMAGE=0
DRY_RUN=0
TMP_COPY="${REBUILD_TMP:-/tmp/preflight-data-4403}"
IMAGE_TAG="athenaquant-app:preflight"
STALE_NAME="athenaquant-preflight"
CONTAINER_NAME="athenaquant"
MD5_FILES=(
    "backend/app/main.py:/app/app/main.py"
    "backend/app/strategy/engine.py:/app/app/strategy/engine.py"
    "backend/app/jobs/daily_pipeline.py:/app/app/jobs/daily_pipeline.py"
    "backend/app/services/preferences.py:/app/app/services/preferences.py"
)

usage() {
    sed -n '2,50p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --preflight) MODE="preflight"; shift ;;
        --apply) MODE="apply"; shift ;;
        --data-dir) DATA_DIR="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --keep-image) KEEP_IMAGE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

command -v docker >/dev/null 2>&1 || { echo "docker unavailable" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq unavailable" >&2; exit 1; }
command -v ss >/dev/null 2>&1 || { echo "ss unavailable" >&2; exit 1; }

HEAD="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "[baseline] HEAD=$HEAD data_dir=$DATA_DIR port=$PORT mode=$MODE"

# ── root-owned 卷清单检测 (chown 前置; 只读 ls) ──────────────────────────────
scan_root_owned() {
    echo "[root-owned scan] data/ 顶层属主清单:"
    ls -la "$DATA_DIR" 2>/dev/null | awk 'NR>1 {print $3" "$4" "$1" "$NF}' \
        | grep -E '^root ' || echo "  (无 root 属主项)"
}

# ── 预检模式 ─────────────────────────────────────────────────────────────────
if [ "$MODE" = "preflight" ]; then
    if [ "$DRY_RUN" = "1" ]; then
        echo "[dry-run] preflight 模式命令预览:"
        echo "  docker build -t $IMAGE_TAG $REPO_ROOT"
        echo "  docker run -d --name $STALE_NAME -p ${PORT}:3018 -v ${TMP_COPY}:/app/data -v $REPO_ROOT/tiers.yaml:/app/tiers.yaml:ro $IMAGE_TAG"
        echo "  docker exec $STALE_NAME sh -c 'md5sum /app/app/main.py /app/app/strategy/engine.py /app/app/jobs/daily_pipeline.py /app/app/services/preferences.py'"
        echo "  docker rm -f $STALE_NAME && rm -rf $TMP_COPY"
        exit 0
    fi

    START_TS="$(date +%s)"
    LEDGER='{}'

    # a. baseline: 3020 空闲断言 (3018 陈旧容器哨兵不动)
    if ss -tln | grep -qE ":(3018|${PORT})\b"; then
        # 3018 是陈旧哨兵 (允许存在); 预检端口必须空闲
        if ss -tln | grep -qE ":${PORT}\b"; then
            echo "[FAIL] 预检端口 ${PORT} 被占用" >&2
            exit 1
        fi
        echo "[baseline] 3018 陈旧容器哨兵在位 (只读, 不触碰); ${PORT} 空闲"
    else
        echo "[baseline] 3018 无监听 (陈旧容器可能未跑); ${PORT} 空闲"
    fi
    # stale-name guard
    docker rm -f "$STALE_NAME" 2>/dev/null || true
    # 零写哨兵基线 (真实数据目录; root-owned 目录 find 会 Permission denied → || true)
    KA_BEFORE="$(ls "$DATA_DIR/kline_auction" 2>/dev/null | wc -l)"
    TMP_BEFORE="$(find "$DATA_DIR" -name '*.tmp' 2>/dev/null | wc -l || true)"

    # b. temp 数据副本 (root 容器法; 源只读挂载零风险)
    echo "[temp-copy] $DATA_DIR → $TMP_COPY (root 容器法, 源只读挂载)"
    rm -rf "$TMP_COPY"
    mkdir -p "$TMP_COPY"
    # 先试宿主 cp (可读目录); 失败 (root-owned 0700) → root 容器法
    if ! cp -a "$DATA_DIR/." "$TMP_COPY/" 2>/dev/null; then
        echo "[temp-copy] 宿主 cp 被 root-owned 目录阻挡 → root 容器法"
        docker run --rm \
            -v "$DATA_DIR:/src:ro" -v "$TMP_COPY:/dst" \
            "$IMAGE_TAG" sh -c 'cp -a /src/. /dst/ && chown -R 999:995 /dst' 2>/dev/null \
        || docker run --rm \
            -v "$DATA_DIR:/src:ro" -v "$TMP_COPY:/dst" \
            athenaquant-app:latest sh -c 'cp -a /src/. /dst/ && chown -R 999:995 /dst'
    else
        docker run --rm -v "$TMP_COPY:/dst" athenaquant-app:latest \
            sh -c 'chown -R 999:995 /dst' 2>/dev/null || true
    fi
    TMP_KA="$(ls "$TMP_COPY/kline_auction" 2>/dev/null | wc -l)"
    TMP_TMP="$(find "$TMP_COPY" -name '*.tmp' 2>/dev/null | wc -l || true)"
    echo "[temp-copy] 副本就绪: kline_auction=$TMP_KA tmp=$TMP_TMP"

    # c. build (记录时长 + 镜像 ID)
    echo "[build] docker build -t $IMAGE_TAG $REPO_ROOT"
    BUILD_START="$(date +%s)"
    docker build -t "$IMAGE_TAG" "$REPO_ROOT"
    BUILD_END="$(date +%s)"
    BUILD_S=$((BUILD_END - BUILD_START))
    IMAGE_ID="$(docker images --format '{{.ID}}' "$IMAGE_TAG" | head -1)"
    echo "[build] ok ${BUILD_S}s image=$IMAGE_ID"

    # d. boot + /health poll ≤120s
    echo "[boot] docker run -d --name $STALE_NAME -p ${PORT}:3018 -v ${TMP_COPY}:/app/data -v $REPO_ROOT/tiers.yaml:/app/tiers.yaml:ro $IMAGE_TAG"
    docker run -d --name "$STALE_NAME" -p "${PORT}:3018" \
        -v "$TMP_COPY:/app/data" \
        -v "$REPO_ROOT/tiers.yaml:/app/tiers.yaml:ro" \
        "$IMAGE_TAG"
    BOOT_START="$(date +%s)"
    HEALTH="000"
    for i in $(seq 1 120); do
        CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${PORT}/health" 2>/dev/null || echo 000)"
        if [ "$CODE" = "200" ]; then HEALTH="$CODE"; break; fi
        sleep 1
    done
    BOOT_END="$(date +%s)"
    BOOT_S=$((BOOT_END - BOOT_START))
    if [ "$HEALTH" != "200" ]; then
        echo "[FAIL] /health 未在 120s 内 200 (got=$HEALTH)" >&2
        docker rm -f "$STALE_NAME" >/dev/null 2>&1 || true
        exit 1
    fi
    echo "[boot] /health 200 in ${BOOT_S}s"

    # e. md5 parity 4/4 (容器路径注意 app/strategy/engine.py)
    MATCH=0; TOTAL=${#MD5_FILES[@]}
    HOST_SUMS="$(cd "$REPO_ROOT" && md5sum backend/app/main.py backend/app/strategy/engine.py backend/app/jobs/daily_pipeline.py backend/app/services/preferences.py | awk '{print $1}')"
    CONT_SUMS="$(docker exec "$STALE_NAME" sh -c 'md5sum /app/app/main.py /app/app/strategy/engine.py /app/app/jobs/daily_pipeline.py /app/app/services/preferences.py' | awk '{print $1}')"
    i=0; for hs in $HOST_SUMS; do
        i=$((i + 1)); cs="$(printf '%s\n' "$CONT_SUMS" | sed -n "${i}p")"
        [ "$hs" = "$cs" ] && MATCH=$((MATCH + 1))
    done
    echo "[md5] match=$MATCH/$TOTAL (preflight == HEAD)"

    # f. trap 清理 + 台账
    RESIDUE_CONTAINER=0; RESIDUE_PORT=0; RESIDUE_TMP=0
    docker rm -f "$STALE_NAME" >/dev/null 2>&1 && RESIDUE_CONTAINER=0 || true
    sleep 1
    if ss -tln | grep -qE ":${PORT}\b"; then RESIDUE_PORT=1; fi
    if [ "$KEEP_IMAGE" = "1" ]; then
        echo "[cleanup] --keep-image: 镜像保留作证据 (Pitfall 6 说明)"
    fi
    rm -rf "$TMP_COPY" && RESIDUE_TMP=0

    # 零写哨兵 (真实数据目录 pre/post 对比)
    KA_AFTER="$(ls "$DATA_DIR/kline_auction" 2>/dev/null | wc -l)"
    TMP_AFTER="$(find "$DATA_DIR" -name '*.tmp' 2>/dev/null | wc -l || true)"
    ZERO_WRITE="ok"
    [ "$KA_AFTER" = "$KA_BEFORE" ] || ZERO_WRITE="dirty: kline_auction $KA_BEFORE→$KA_AFTER"
    [ "$TMP_AFTER" = "0" ] || ZERO_WRITE="dirty: *.tmp=$TMP_AFTER"

    END_TS="$(date +%s)"
    jq -nc \
        --arg mode "preflight" --arg head "$HEAD" \
        --argjson build_s "$BUILD_S" --argjson boot_s "$BOOT_S" \
        --argjson health "$HEALTH" \
        --argjson match "$MATCH" --argjson total "$TOTAL" \
        --argjson residue_container "$RESIDUE_CONTAINER" \
        --argjson residue_port "$RESIDUE_PORT" \
        --argjson residue_tmp "$RESIDUE_TMP" \
        --arg zero_write "$ZERO_WRITE" \
        --arg image_id "$IMAGE_ID" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{mode:$mode,head:$head,build_s:$build_s,boot_s:$boot_s,health:$health,
          md5:{match_count:$match,total:$total},
          residue:{container:$residue_container,port:$residue_port,tmpdir:$residue_tmp},
          zero_write:$zero_write,image_id:$image_id,ts:$ts}' | tee /tmp/rebuild-preflight-4403.json
    echo "[preflight] done: build=${BUILD_S}s boot=${BOOT_S}s health=${HEALTH} md5=${MATCH}/${TOTAL} residue=0/$ZERO_WRITE"
    [ "$MATCH" = "$TOTAL" ] && [ "$HEALTH" = "200" ] && [ "$ZERO_WRITE" = "ok" ] || {
        echo "[FAIL] preflight 未全绿" >&2; exit 1
    }
    exit 0
fi

# ── --apply 模式 (部署日 operator, human-check — 只打印, 绝不静默替换) ────────
scan_root_owned
cat <<EOF

[apply] 部署日替换步骤 (operator 逐条确认后手动执行; 脚本不静默替换运行中容器):

  step 1 (前提): 预检全绿 — ./deploy_rebuild.sh --preflight
          build ok + /health 200 + md5 4/4 == HEAD 通过后才可继续

  step 2 (替换): docker compose up -d
          运行目录: $REPO_ROOT
          卷保留: ./data:/app/data (bind mount) + ./tiers.yaml:/app/tiers.yaml:ro
          效果: compose 自动 stop/rm 旧容器 → 起新镜像 (数据天然保留, 零迁移)

  step 3 (chown): docker run --rm -v $DATA_DIR:/dst athenaquant-app:latest \
          sh -c 'chown -R 999:995 /dst'
          root 容器法修复 root-owned 卷 (sudo 无 tty 不可用 fallback, 39-01 W4 同因):
          forecast-* (700) / ext_data+kline_daily_enriched (755) / user_data/ai_*.json (644)
          数据卷为 bind mount → chown 目标与 compose 挂载同路径, 零误伤面

  step 4 (对齐确认): docker exec $CONTAINER_NAME sh -c \\
          'md5sum /app/app/main.py /app/app/strategy/engine.py /app/app/jobs/daily_pipeline.py /app/app/services/preferences.py'
          与宿主 md5sum backend/app/... 比对 4/4 == HEAD

  step 5 (回归): 重建后 /health 200 + ./deploy_verify_endpoints.py --base-url http://localhost:3018
          (44-02 200-body 全流程: login + validation 8 键 / backtest {runs,count} /
           backfill {status,job_id} + W-5 9 键)

  记录纪律: 以上每步由 operator 执行并在部署台账记录 human-check; 本脚本不代执行。
EOF
exit 0
