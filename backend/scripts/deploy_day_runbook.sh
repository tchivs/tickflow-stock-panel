#!/usr/bin/env bash
# =============================================================================
# deploy_day_runbook.sh — DEP-03: D1..D8 部署日观测窗三态判定 (只读, 零写入)
#
# 判定语义 (与 RESEARCH 判定路径表 / 39-03-OBSERVATION-WINDOW 逐项对齐):
#   pass           证据齐 (数据在场 + 键形状正确)
#   degraded       诚实 fail-closed (数据缺 / 键缺 / 条件未满足 — 如实记录, 非 BLOCKER)
#   BLOCKER        数据不可用但系统装作有数据 / 隔离破坏 / 断言冲突 → exit 2
#   (其余专用态: not_before_1530 / empty_lake_fail_closed / conditional_not_configured /
#    skipped / skipped_no_data / pending_human — 均为 exit 0 诚实态)
#
# 分钟点亮门硬先验: 墙钟 < 15:30 Asia/Shanghai → not_before_1530 拒绝态
#   (防盘中误判; kline_minute 分区只在 15:30 EOD/手动同步后写入)。
#   点亮判定用「引擎运行结果 auction_intraday_confirm 命中行非空」,
#   **绝不读取报告层 minute_confirm** (auction_validation.py:535 恒 not_applied)。
#
# 用法:
#   deploy_day_runbook.sh [--data-dir ./data] [--date YYYY-MM-DD] [--now <ISO>]
#                         [--out ledger.json] [--item D1|D2|…|ALL]
#   env: DEP_TRADE_DATE (优先于 --date; 部署日真实日期)
#        RUNBOOK_PY     (python3 解释器, 默认 backend/.venv/bin/python → python3)
#
# 只读纪律: 本脚本对 data 目录零 mkdir/写/删除; 唯一写面 = --out 台账 (原子写)。
# 诚实纪律: 沙箱证的是脚本逻辑与 DTO 形状; 部署日真实事件 (premarket 落盘 /
#   sidecar 点亮 / 分钟湖写入) 是真实交易日观测, 本脚本只做三态记录, 绝不冒充已证。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"

DATA_DIR="${DEP_DATA_DIR:-./data}"
TRADE_DATE="${DEP_TRADE_DATE:-}"
NOW_ISO=""
OUT_FILE=""
ITEMS="ALL"
PY_BIN="${RUNBOOK_PY:-}"

usage() {
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --data-dir) DATA_DIR="$2"; shift 2 ;;
        --date) TRADE_DATE="$2"; shift 2 ;;
        --now) NOW_ISO="$2"; shift 2 ;;
        --out) OUT_FILE="$2"; shift 2 ;;
        --item) ITEMS="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [ -z "$PY_BIN" ]; then
    for cand in "$REPO_ROOT/backend/.venv/bin/python" "$REPO_ROOT/.venv/bin/python" python3; do
        if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then PY_BIN="$cand"; break; fi
    done
fi
command -v "$PY_BIN" >/dev/null 2>&1 || { echo "python3 unavailable" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq unavailable" >&2; exit 1; }

# ---- 全局时钟 (--now 注入仅供测试; 部署日绝不使用) ----------------------------
CLOCK="$("$PY_BIN" - "$NOW_ISO" <<'PY'
from __future__ import annotations
import os, sys
from datetime import datetime
now_iso = sys.argv[1]
if now_iso:
    dt = datetime.fromisoformat(now_iso)
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    from zoneinfo import ZoneInfo
    dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
else:
    from zoneinfo import ZoneInfo
    dt = datetime.now(ZoneInfo("Asia/Shanghai"))
print(dt.isoformat(timespec="seconds"))
print(dt.date().isoformat())
print(dt.hour * 60 + dt.minute)
PY
)"
CLOCK_ISO="$(printf '%s\n' "$CLOCK" | sed -n '1p')"
CLOCK_DATE="$(printf '%s\n' "$CLOCK" | sed -n '2p')"
CLOCK_MIN="$(printf '%s\n' "$CLOCK" | sed -n '3p')"

if [ -z "$TRADE_DATE" ]; then
    TRADE_DATE="$CLOCK_DATE"
fi
case "$TRADE_DATE" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *) echo "invalid --date: $TRADE_DATE (expect YYYY-MM-DD)" >&2; exit 1 ;;
esac

T="$TRADE_DATE"
NOW_MIN="$CLOCK_MIN"
NOW_ISO_FINAL="$CLOCK_ISO"

# ---- 台账 -------------------------------------------------------------------
LEDGER="[]"
declare -a VERDICTS=()

log_item() { # item verdict evidence
    local item="$1" verdict="$2" evidence="$3"
    local entry
    entry="$(jq -nc --arg item "$item" --arg date "$T" --arg verdict "$verdict" \
                  --arg evidence "$evidence" --arg ts "$NOW_ISO_FINAL" \
                  '{item:$item,date:$date,verdict:$verdict,evidence:$evidence,ts:$ts}')"
    LEDGER="$(printf '%s' "$LEDGER" | jq --argjson e "$entry" '. + [$e]')"
    VERDICTS+=("$verdict")
    printf '  %-14s %-30s %s\n' "$item" "$verdict" "$(printf '%s' "$evidence" | head -c 120)" >&2
}

have_item() { # $1 = item id; ITEMS == ALL → true
    [ "$ITEMS" = "ALL" ] || [ "$ITEMS" = "$1" ]
}

BLOCKER_COUNT=0

# =============================================================================
# D1 — 盘前预览 (09:26): premarket_results/date={T}/part.json 键形状
# =============================================================================
if have_item "D1"; then
    part="$DATA_DIR/premarket_results/date=$T/part.json"
    d1_verdict=""; d1_evidence=""
    if [ ! -f "$part" ]; then
        d1_verdict="degraded"
        d1_evidence="premarket_results/date=$T/part.json 不存在 (部署日 09:26 job 首建; 沙箱 ABSENT 正常)"
    else
        keys_ok=$(jq -e '(.window == "pre_open") and (.provisional == true) and
                         has("computed_at") and has("probe") and has("degraded")' "$part" \
                  >/dev/null 2>&1 && echo yes || echo no)
        if [ "$keys_ok" = "yes" ]; then
            d1_verdict="pass"
            d1_evidence="part.json 键齐全 (window=pre_open provisional=true computed_at/probe/degraded 在场)"
        else
            d1_verdict="degraded"
            d1_evidence="part.json 存在但键形状缺: $(jq -c '{window,provisional,computed_at,probe,degraded}' "$part" 2>/dev/null | head -c 200)"
        fi
    fi
    # BLOCKER 判据: 09:26 盘前落盘进 strategy_cache / screener_results (隔离破坏)
    sc_mtime="$("$PY_BIN" - "$DATA_DIR/user_data/strategy_cache.json" <<'PY'
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
p = Path(sys.argv[1])
if not p.exists():
    print(""); sys.exit(0)
d = datetime.fromtimestamp(p.stat().st_mtime, tz=ZoneInfo("Asia/Shanghai"))
print(d.strftime("%Y-%m-%d %H:%M"))
PY
)"
    breach=""
    if [ -n "$sc_mtime" ]; then
        sc_date="${sc_mtime%% *}"; sc_time="${sc_mtime##* }"
        sc_min=$(( 10#${sc_time%%:*} * 60 + 10#${sc_time##*:} ))
        if [ "$sc_date" = "$T" ] && [ "$sc_min" -ge 540 ] && [ "$sc_min" -le 575 ]; then
            breach="strategy_cache.json 在 $T 09:00-09:35 写入 (mtime=$sc_mtime)"
        fi
    fi
    if [ -z "$breach" ] && [ -f "$DATA_DIR/screener_results/date=$T/part.json" ]; then
        sr_mtime="$("$PY_BIN" - "$DATA_DIR/screener_results/date=$T/part.json" <<'PY'
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
p = Path(sys.argv[1])
d = datetime.fromtimestamp(p.stat().st_mtime, tz=ZoneInfo("Asia/Shanghai"))
print(d.strftime("%Y-%m-%d %H:%M"))
PY
)"
        sr_date="${sr_mtime%% *}"; sr_time="${sr_mtime##* }"
        sr_min=$(( 10#${sr_time%%:*} * 60 + 10#${sr_time##*:} ))
        if [ "$sr_date" = "$T" ] && [ "$sr_min" -ge 540 ] && [ "$sr_min" -le 575 ]; then
            breach="screener_results/date=$T 在 09:00-09:35 写入 (mtime=$sr_mtime)"
        fi
    fi
    if [ -n "$breach" ]; then
        log_item "d1_premarket" "BLOCKER" "隔离破坏: $breach; $d1_evidence"
        BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
    else
        log_item "d1_premarket" "$d1_verdict" "$d1_evidence; 隔离检查通过 (strategy_cache/screener 无盘前写入)"
    fi
fi

# =============================================================================
# D4 — 盘前监控 (09:26 后): alert_events preopen 行 + 键形状
# =============================================================================
if have_item "D4"; then
    alert_out="$("$PY_BIN" - "$DATA_DIR/operational.db" "$T" <<'PY'
from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path
db, tdate = Path(sys.argv[1]), sys.argv[2]
if not db.exists():
    print("NO_DB"); sys.exit(0)
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT rule_id, occurred_at, event_json FROM alert_events "
        "WHERE substr(occurred_at,1,10)=? "
        "AND (event_json LIKE '%preopen%' OR event_json LIKE '%pre_open%' "
        "     OR rule_id LIKE '%preopen%')",
        (tdate,),
    ).fetchall()
    con.close()
    out = [{"rule_id": r[0], "occurred_at": r[1], "event_json": r[2]} for r in rows]
    print(json.dumps(out, ensure_ascii=False))
except Exception as e:
    print(f"ERR:{e}"); sys.exit(0)
PY
)"
    case "$alert_out" in
        NO_DB)
            log_item "d4_monitor" "degraded" "operational.db 不存在 (未初始化)"
            ;;
        ERR:*)
            log_item "d4_monitor" "degraded" "alert_events 查询失败: ${alert_out#ERR:}"
            ;;
        *)
            n_rows="$(printf '%s' "$alert_out" | jq 'length')"
            if [ "$n_rows" = "0" ]; then
                log_item "d4_monitor" "skipped" "当日无 preopen 告警事件 (fail-closed 通过态)"
            else
                has_keys="$(printf '%s' "$alert_out" | jq -e '[.[] | (.event_json | fromjson? // {} | has("provisional") and has("degraded"))] | all' >/dev/null 2>&1 && echo yes || echo no)"
                chg_bad="$(printf '%s' "$alert_out" | jq -e '[.[] | (.event_json | fromjson? // {} | .change_pct) | select(. != null)] | length == 0' >/dev/null 2>&1 && echo no || echo yes)"
                if [ "$chg_bad" = "yes" ]; then
                    log_item "d4_monitor" "BLOCKER" "preopen 事件 event_json 含非 None change_pct (EOD 列禁用被破坏)"
                    BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
                elif [ "$has_keys" = "yes" ]; then
                    log_item "d4_monitor" "pass" "$n_rows 条 preopen 事件, provisional/degraded 键齐全, change_pct 恒 None"
                else
                    log_item "d4_monitor" "degraded" "$n_rows 条 preopen 事件但 provisional/degraded 键缺失"
                fi
            fi
            ;;
    esac
fi

# =============================================================================
# D2 — EOD 池持久化 (15:30-15:35): enriched 分区 + screener eod 快照
# =============================================================================
if have_item "D2"; then
    enriched="$DATA_DIR/kline_daily_enriched/date=$T/part.parquet"
    screener="$DATA_DIR/screener_results/date=$T/part.json"
    if [ ! -f "$enriched" ]; then
        log_item "d2_eod" "degraded" "kline_daily_enriched/date=$T 分区缺失 (EOD 15:30 未跑 / 沙箱无当日)"
    else
        rows="$("$PY_BIN" - "$enriched" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    import polars as pl
    print(pl.read_parquet(p).height)
except Exception:
    print("TOOL_UNAVAILABLE")
PY
)"
        if [ "$rows" = "TOOL_UNAVAILABLE" ]; then
            log_item "d2_eod" "degraded" "enriched 分区存在但行数不可读 (polars/pyarrow/duckdb 均不可用)"
        elif [ "$rows" = "0" ]; then
            log_item "d2_eod" "BLOCKER" "enriched 分区在场但 0 行 (空断言)"
            BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
        else
            if [ ! -f "$screener" ]; then
                log_item "d2_eod" "degraded" "enriched ${rows} 行但 screener_results/date=$T 缺失"
            else
                origin="$(jq -r '.snapshot_origin // "unknown"' "$screener")"
                if [ "$origin" = "eod" ]; then
                    log_item "d2_eod" "pass" "enriched ${rows} 行 + screener snapshot_origin=eod"
                else
                    log_item "d2_eod" "degraded" "enriched ${rows} 行但 screener snapshot_origin=$origin (≠eod)"
                fi
            fi
        fi
    fi
fi

# =============================================================================
# D6 — 复盘 R13 (15:40): 复盘归档 Block 3 avg_change_pct vs enriched 手动均值
# =============================================================================
if have_item "D6"; then
    recap_file="$DATA_DIR/user_data/ai_market_recaps.json"
    recap_t="[]"
    if [ -f "$recap_file" ]; then
        recap_t="$(jq -c --arg d "$T" '[.[] | select(.as_of == $d)]' "$recap_file" 2>/dev/null || echo '[]')"
    fi
    n_recap="$(printf '%s' "$recap_t" | jq 'length')"
    mean_out="$("$PY_BIN" - "$DATA_DIR/kline_daily_enriched" "$T" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
root, target = Path(sys.argv[1]), sys.argv[2]
part = root / f"date={target}" / "part.parquet"
if not part.exists():
    print("MISSING"); sys.exit(0)
try:
    import polars as pl
except Exception:
    print("TOOL_UNAVAILABLE"); sys.exit(0)
df = pl.read_parquet(part)
if df.is_empty():
    print("EMPTY"); sys.exit(0)
try:
    prev = None
    for d in sorted(x.name.split("=")[1] for x in root.iterdir() if x.is_dir()):
        if d >= target:
            break
        prev = d
    if prev is None:
        print("NO_PREV"); sys.exit(0)
    pdf = pl.read_parquet(root / f"date={prev}" / "part.parquet") \
        .select(["symbol", "close"]).rename({"close": "prev_close"})
    m = df.select(["symbol", "close"]) \
        .join(pdf, on="symbol", how="inner") \
        .with_columns((pl.col("close") / pl.col("prev_close") - 1).alias("chg"))
    vals = m["chg"].drop_nulls().to_list()
    print(f"{sum(vals)/len(vals):.6f}" if vals else "EMPTY")
except Exception as e:
    print(f"ERR:{e}"); sys.exit(0)
PY
)"
    case "$mean_out" in
        MISSING)
            log_item "d6_recap_r13" "degraded" "enriched/date=$T 缺失 → 手动均值不可算 (复盘 Block 3 无法比对)"
            ;;
        TOOL_UNAVAILABLE)
            log_item "d6_recap_r13" "degraded" "enriched 读不可用 (polars 缺失)"
            ;;
        NO_PREV)
            log_item "d6_recap_r13" "degraded" "前一交易日 enriched 分区缺失 → 手动均值不可算"
            ;;
        ERR:*)
            log_item "d6_recap_r13" "degraded" "手动均值计算失败: ${mean_out#ERR:}"
            ;;
        EMPTY)
            log_item "d6_recap_r13" "degraded" "enriched/date=$T 空帧或无有效 change_pct"
            ;;
        *)
            if [ "$n_recap" = "0" ]; then
                log_item "d6_recap_r13" "degraded" \
                    "手动均值 change_pct=$mean_out; 复盘归档无 $T 条目 (LLM 复盘默认关 → 面板未归档, 部署日人工比对)"
            else
                # 归档内容中提取 Block 3 avg_change_pct (build_auction_slice 文本)
                arc_chg="$(printf '%s' "$recap_t" | jq -r '[.[].content // ""] | join("\n")' \
                    | grep -oE '平均change_pct=[-+]?[0-9.]+' | head -1 | cut -d= -f2)"
                if [ -z "$arc_chg" ]; then
                    log_item "d6_recap_r13" "degraded" \
                        "归档有 $n_recap 条但未含可解析 Block 3 avg_change_pct (LLM 默认关, 面板未内嵌) — pending_human"
                else
                    diff_ok="$("$PY_BIN" - "$mean_out" "$arc_chg" <<'PY'
from __future__ import annotations
import sys
a, b = float(sys.argv[1]), float(sys.argv[2])
print("yes" if abs(a - b) <= 0.001 else "no")
PY
)"
                    if [ "$diff_ok" = "yes" ]; then
                        log_item "d6_recap_r13" "pass" "归档 Block3=$arc_chg vs 手动均值=$mean_out 差≤0.1%"
                    else
                        log_item "d6_recap_r13" "BLOCKER" "归档 Block3=$arc_chg vs 手动均值=$mean_out 差>0.1% (R13 mismatch)"
                        BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
                    fi
                fi
            fi
            ;;
    esac
fi

# =============================================================================
# D5 — 复盘归档 (15:40): 归档存在 + 面板三块 data_completeness 注记
# =============================================================================
if have_item "D5"; then
    recap_file="$DATA_DIR/user_data/ai_market_recaps.json"
    recap_t="[]"
    if [ -f "$recap_file" ]; then
        recap_t="$(jq -c --arg d "$T" '[.[] | select(.as_of == $d)]' "$recap_file" 2>/dev/null || echo '[]')"
    fi
    n_recap="$(printf '%s' "$recap_t" | jq 'length')"
    if [ "$n_recap" = "0" ]; then
        log_item "d5_recap" "degraded" \
            "复盘归档无 $T 条目 (LLM 复盘默认关 preferences.py:441 enabled:false → 15:40 未生成; 部署日人工确认)"
    else
        # 面板三块源在场检查 (Block1 kline_auction / Block2 enriched / Block3 premarket)
        b1="$( [ -d "$DATA_DIR/kline_auction/date=$T" ] && echo present || echo absent )"
        b2="$( [ -f "$DATA_DIR/kline_daily_enriched/date=$T/part.parquet" ] && echo present || echo absent )"
        b3="$( [ -f "$DATA_DIR/premarket_results/date=$T/part.json" ] && echo present || echo absent )"
        present_cnt=0
        [ "$b1" = "present" ] && present_cnt=$((present_cnt + 1))
        [ "$b2" = "present" ] && present_cnt=$((present_cnt + 1))
        [ "$b3" = "present" ] && present_cnt=$((present_cnt + 1))
        if [ "$present_cnt" = "3" ]; then
            log_item "d5_recap" "pass" \
                "复盘归档 $n_recap 条 + 面板三块源全在场 (Block1/2/3 present); 引用切片外数字不可程序判定 → pending_human"
        else
            log_item "d5_recap" "degraded" \
                "复盘归档 $n_recap 条; 面板源: Block1(kline_auction)=$b1 Block2(enriched)=$b2 Block3(premarket)=$b3 — 缺块带诚实注记 (data_completeness); 引用切片外数字不可程序判定 → pending_human"
        fi
    fi
fi

# =============================================================================
# D7 — 概念 drift 探针 (每交易日): drift.jsonl + ext_history 分区 + 零副作用
# =============================================================================
if have_item "D7"; then
    drift="$DATA_DIR/ext_history/_probe/drift.jsonl"
    kinds_ok=0; kinds_missing=""
    for kind in gn_ths hy_ths; do
        if [ -f "$drift" ] && grep -q "\"date\":\"$T\"" "$drift" && grep "\"date\":\"$T\"" "$drift" | grep -q "\"kind\":\"$kind\""; then
            kinds_ok=$((kinds_ok + 1))
        else
            kinds_missing="$kinds_missing $kind"
        fi
    done
    part_ok=0
    for kind in gn_ths hy_ths; do
        if [ -f "$DATA_DIR/ext_history/$kind/date=$T/part.parquet" ] && \
           [ -f "$DATA_DIR/ext_history/$kind/date=$T/manifest.json" ]; then
            part_ok=$((part_ok + 1))
        fi
    done
    ext_writes="$("$PY_BIN" - "$DATA_DIR/ext_data" "$T" <<'PY'
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
root, tdate = Path(sys.argv[1]), sys.argv[2]
if not root.exists():
    print("0"); sys.exit(0)
n = 0
for p in root.rglob("*"):
    if p.is_file():
        try:
            d = datetime.fromtimestamp(p.stat().st_mtime, tz=ZoneInfo("Asia/Shanghai"))
            if d.date().isoformat() == tdate:
                n += 1
        except Exception:
            pass
print(n)
PY
)"
    if [ "$kinds_ok" = "2" ] && [ "$part_ok" = "2" ]; then
        if [ "$ext_writes" != "0" ]; then
            log_item "d7_probe" "BLOCKER" "探针运行日 $T 但 ext_data 出现 $ext_writes 个当日写入 (零副作用断言被破坏)"
            BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
        else
            log_item "d7_probe" "pass" "drift.jsonl 双 kind 行 + ext_history 双分区 + manifest; ext_data 零写入"
        fi
    else
        if [ -d "$DATA_DIR/ext_history" ]; then
            log_item "d7_probe" "degraded" \
                "drift/分区未齐: kinds_ok=$kinds_ok/2 part_ok=$part_ok/2 (抓取失败诚实 skip / 尚未运行)"
        else
            log_item "d7_probe" "degraded" "ext_history 目录不存在 (探针尚未运行 — 诚实, 非 BLOCKER)"
        fi
    fi
fi

# =============================================================================
# D8 — 竞价采集 sidecar (09:26 采集 / 09:40 对账 / 15:40 提审) + 分钟点亮门
# =============================================================================
if have_item "D8"; then
    ledger_file="$DATA_DIR/user_data/auction_sidecar_ledger.jsonl"
    ledger_rows="$("$PY_BIN" - "$ledger_file" "$T" <<'PY'
from __future__ import annotations
import json, sys
from pathlib import Path
f, tdate = Path(sys.argv[1]), sys.argv[2]
if not f.exists():
    print("[]"); sys.exit(0)
out = []
with open(f, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("trade_date") == tdate:
            out.append(ev)
print(json.dumps(out, ensure_ascii=False))
PY
)"

    # —— 09:26 采集 ——
    staging_part="$DATA_DIR/tick_staging/date=$T/part.parquet"
    staging_manifest="$DATA_DIR/tick_staging/date=$T/manifest.json"
    capture_verdict="degraded"; capture_ev="tick_staging/date=$T 分区缺失 (采集未跑/全失败 fail-closed)"
    if [ -f "$staging_part" ] && [ -f "$staging_manifest" ]; then
        comp_ok="$(jq -r '.completeness.ok // false' "$staging_manifest")"
        if [ "$comp_ok" = "true" ]; then
            capture_verdict="pass"; capture_ev="tick_staging/date=$T 分区 + manifest completeness.ok=true"
        else
            capture_verdict="degraded"; capture_ev="tick_staging 分区存在但 completeness.ok=false (fail-closed)"
        fi
    else
        cap_ledger="$(printf '%s' "$ledger_rows" | jq -c '[.[] | select(.job == "auction_sidecar_capture")]')"
        cap_reason="$(printf '%s' "$cap_ledger" | jq -r 'if length > 0 then (.[-1].reason // .[-1].skipped // "no_ledger_reason") else "no_ledger_entry" end')"
        capture_ev="tick_staging/date=$T 缺失; capture 台账 reason=$cap_reason (fail-closed)"
    fi

    # —— 09:40 对账 ——
    rec_verdict=""; rec_ev=""
    if [ "$NOW_MIN" -ge 580 ]; then
        rec_ledger="$(printf '%s' "$ledger_rows" | jq -c '[.[] | select(.job == "auction_sidecar_reconcile")]')"
        rec_n="$(printf '%s' "$rec_ledger" | jq 'length')"
        if [ "$rec_n" = "0" ]; then
            rec_verdict="degraded"; rec_ev="对账台账无 $T 行 (09:40 job 未跑/未落)"
        else
            rec_skipped="$(printf '%s' "$rec_ledger" | jq -r '.[-1].skipped // ""')"
            rec_reason="$(printf '%s' "$rec_ledger" | jq -r '.[-1].reason // ""')"
            rec_ok="$(printf '%s' "$rec_ledger" | jq -r '.[-1].ok // 0')"
            rec_req="$(printf '%s' "$rec_ledger" | jq -r '.[-1].requested // 0')"
            rec_events="$(printf '%s' "$rec_ledger" | jq -r '[.[-1].events[]?] | join(",")')"
            if [ "$rec_skipped" = "no_data" ]; then
                rec_verdict="skipped_no_data"; rec_ev="对账 skipped=no_data (非交易日, 零告警)"
            elif [ "$rec_reason" != "" ]; then
                rec_verdict="degraded"; rec_ev="对账 reason=$rec_reason events=[$rec_events] (fail-closed)"
            elif [ "$rec_ok" = "$rec_req" ] && [ "$rec_req" != "0" ]; then
                rec_verdict="pass"; rec_ev="对账 closed ($rec_ok/$rec_req 检查闭合, 零告警)"
            else
                rec_verdict="degraded"; rec_ev="对账状态未闭合 ok=$rec_ok/$rec_req events=[$rec_events]"
            fi
        fi
    fi

    # —— 15:40 提审 ——
    pro_verdict=""; pro_ev=""
    if [ "$NOW_MIN" -ge 940 ]; then
        ka_part="$DATA_DIR/kline_auction/date=$T"
        pro_ledger="$(printf '%s' "$ledger_rows" | jq -c '[.[] | select(.job == "auction_sidecar_promote")]')"
        pro_n="$(printf '%s' "$pro_ledger" | jq 'length')"
        if [ -d "$ka_part" ]; then
            pro_verdict="pass"; pro_ev="kline_auction/date=$T 分区存在 (提审仅 09:25 撮合行)"
        elif [ "$pro_n" = "0" ]; then
            pro_verdict="degraded"; pro_ev="kline_auction/date=$T 缺失且提审台账无行 (15:40 未跑/闸门不过)"
        else
            pro_reason="$(printf '%s' "$pro_ledger" | jq -r '.[-1].reason // "not_promoted"')"
            pro_verdict="degraded"; pro_ev="提审 reason=$pro_reason → 0 写 (诚实 fail-closed)"
        fi
    fi

    # —— 合并判定 ——
    if [ "$NOW_MIN" -lt 580 ]; then
        log_item "d8_sidecar" "$capture_verdict" "$capture_ev (09:40/15:40 未到)"
    else
        combined="$capture_verdict $rec_verdict $pro_verdict"
        if printf '%s\n' "$capture_verdict" "$rec_verdict" "$pro_verdict" | grep -qx "BLOCKER"; then
            log_item "d8_sidecar" "BLOCKER" "采集/对账/提审含 BLOCKER: $combined"
            BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
        elif printf '%s\n' "$capture_verdict" "$rec_verdict" "$pro_verdict" | grep -qx "skipped_no_data"; then
            log_item "d8_sidecar" "skipped_no_data" "$capture_ev; $rec_ev; $pro_ev (非交易日零告警)"
        elif printf '%s\n' "$capture_verdict" "$rec_verdict" "$pro_verdict" | grep -vqx "pass"; then
            log_item "d8_sidecar" "degraded" "采集=$capture_verdict 对账=$rec_verdict 提审=$pro_verdict — fail-closed 诚实态"
        else
            log_item "d8_sidecar" "pass" "采集/对账/提审全 pass: $capture_ev; $rec_ev; $pro_ev"
        fi
    fi
fi

# =============================================================================
# D8 分钟点亮门 (15:30 后, 非盘中) — 独立 item: minute_light
# =============================================================================
if have_item "minute_light"; then
    if [ "$NOW_MIN" -lt 930 ]; then
        log_item "minute_light" "not_before_1530" \
            "墙钟 $NOW_ISO_FINAL (CN ${NOW_MIN}min) < 15:30 — 盘中拒绝判定 (防误判; kline_minute 分区 15:30 后才写)"
    else
        kmin="$DATA_DIR/kline_minute/date=$T/part.parquet"
        if [ ! -f "$kmin" ]; then
            log_item "minute_light" "empty_lake_fail_closed" \
                "kline_minute/date=$T 分区不存在 — 空湖 fail-closed (total=0 诚实通过态, 非 BLOCKER)"
        else
            rows="$("$PY_BIN" - "$kmin" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    import polars as pl
    print(pl.read_parquet(p).height)
except Exception:
    print("TOOL_UNAVAILABLE")
PY
)"
            if [ "$rows" = "TOOL_UNAVAILABLE" ]; then
                log_item "minute_light" "degraded" "kline_minute 分区存在但行数不可读"
            elif [ "$rows" = "0" ]; then
                log_item "minute_light" "empty_lake_fail_closed" \
                    "kline_minute/date=$T 分区 0 行 — 空湖 fail-closed (诚实通过态, 非 BLOCKER)"
            else
                # 引擎运行结果扫描: backtest_results 当日 run 中 auction_intraday_confirm 命中
                hit="no"; note=""
                if [ -d "$DATA_DIR/backtest_results" ]; then
                    scan="$("$PY_BIN" - "$DATA_DIR/backtest_results" "$T" <<'PY'
from __future__ import annotations
import json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
root, tdate = Path(sys.argv[1]), sys.argv[2]
try:
    import polars as pl
except Exception:
    print("TOOL_UNAVAILABLE"); sys.exit(0)
hit = "no"; note = ""
for run in sorted(root.glob("run_id=*")):
    mf = run / "manifest.json"
    if not mf.exists():
        continue
    try:
        m = json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        continue
    created = m.get("created_at", "")
    try:
        cd = datetime.fromisoformat(created).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    except Exception:
        cd = ""
    strategies = [s.get("id") if isinstance(s, dict) else s for s in (m.get("strategies") or [])]
    if "auction_intraday_confirm" not in strategies:
        continue
    if cd == tdate or (m.get("window") or {}).get("effective_end", "")[:10] == tdate:
        try:
            df = pl.read_parquet(run / "part.parquet")
            if not df.is_empty() and "strategy" in df.columns:
                rows = df.filter(pl.col("strategy") == "auction_intraday_confirm")
                if not rows.is_empty():
                    hit = "yes"
                    break
        except Exception:
            pass
    if not note and m.get("minute_note"):
        note = m["minute_note"]
print(json.dumps({"hit": hit, "note": note}, ensure_ascii=False))
PY
)"
                    if [ "$scan" != "TOOL_UNAVAILABLE" ]; then
                        hit="$(printf '%s' "$scan" | jq -r '.hit')"
                        note="$(printf '%s' "$scan" | jq -r '.note')"
                    fi
                fi
                if [ "$hit" = "yes" ]; then
                    log_item "minute_light" "lit" \
                        "kline_minute/date=$T ${rows} 行 + 引擎 auction_intraday_confirm 命中行非空 (报告层 minute_confirm 不参与)"
                elif [ -n "$note" ]; then
                    log_item "minute_light" "degraded" \
                        "kline_minute ${rows} 行但无 auction_intraday_confirm 命中; 注记: ${note:0:100}"
                else
                    log_item "minute_light" "BLOCKER" \
                        "kline_minute/date=$T ${rows} 行在场但无 auction_intraday_confirm 命中且无注记"
                    BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
                fi
            fi
        fi
    fi
fi

# =============================================================================
# D3 — 竞价真列 (条件项): 竞价源未配置 → conditional_not_configured 通过态
# =============================================================================
if have_item "D3"; then
    ka_part="$DATA_DIR/kline_auction/date=$T/part.parquet"
    if [ ! -f "$ka_part" ]; then
        log_item "d3_auction_columns" "conditional_not_configured" \
            "kline_auction/date=$T 分区缺失 → 竞价源未配置/未提审 (fail-closed 通过态)"
    else
        cols="$("$PY_BIN" - "$ka_part" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    import polars as pl
    print(",".join(pl.read_parquet(p).columns))
except Exception:
    print("TOOL_UNAVAILABLE")
PY
)"
        if [ "$cols" = "TOOL_UNAVAILABLE" ]; then
            log_item "d3_auction_columns" "degraded" "kline_auction 分区存在但列不可读"
        else
            need_ok=yes
            for c in auction_unmatched_volume virtual_price; do
                printf '%s' "$cols" | tr ',' '\n' | grep -qx "$c" || need_ok=no
            done
            if [ "$need_ok" = "yes" ]; then
                log_item "d3_auction_columns" "conditional_available" "kline_auction/date=$T 真列在场 (含 auction_unmatched_volume/virtual_price)"
            else
                log_item "d3_auction_columns" "conditional_not_configured" \
                    "kline_auction/date=$T 列=[$cols] 缺真列 → 竞价源未配置 (通过态)"
            fi
        fi
    fi
fi

# =============================================================================
# 输出台账 + 退出码
# =============================================================================
if [ -n "$OUT_FILE" ]; then
    tmp="${OUT_FILE}.tmp.$$"
    printf '%s\n' "$LEDGER" > "$tmp"
    mv -f "$tmp" "$OUT_FILE"
    chmod 600 "$OUT_FILE" 2>/dev/null || true
fi

# stdout = 台账 JSON (可管道消费: `... | jq`); 人类可读表走 stderr
printf '%s\n' "$LEDGER" | jq -c '.[]'
printf '\n=== runbook %s (T=%s, now=%s) ===\n' "$ITEMS" "$T" "$NOW_ISO_FINAL" >&2
printf '%s\n' "$LEDGER" | jq -r '.[] | "\(.item)\t\(.verdict)\t\(.evidence)"' >&2

if [ "$BLOCKER_COUNT" -gt 0 ]; then
    echo "BLOCKER count=$BLOCKER_COUNT → exit 2" >&2
    exit 2
fi
exit 0
