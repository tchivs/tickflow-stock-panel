"""OQ-3 概念 PIT 逐日漂移探针 (manual-only, operator 部署后跑)。

每交易日 capture 当前概念/行业快照 → 记录分区 sha256 → 追加 drift.jsonl;
周终报告去重哈希/逐日变化/概念增删样本。零副作用于 ext 当前快照 /
strategy_cache / screener_results; 只写 data/ext_history/ 与 _probe/ 输出。

用法:
    python scripts/probe_concept_drift.py [YYYY-MM-DD] [--upstream]
    DATA_DIR=/path/to/data python scripts/probe_concept_drift.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import date
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))  # backend/ — app 包根

from app.services import concept_history  # noqa: E402


def main() -> int:
    env_data = os.environ.get("DATA_DIR")
    data_dir = Path(env_data) if env_data else (Path(__file__).resolve().parents[2] / "data")

    use_upstream = "--upstream" in sys.argv
    as_of = next((a for a in sys.argv[1:] if a != "--upstream"), None)
    if as_of is None:
        as_of = date.today().isoformat()
    if not concept_history._DATE_RE.fullmatch(as_of):
        print(f"invalid as_of: {as_of!r}")
        return 1

    try:
        if use_upstream:
            result = concept_history.capture_from_upstream(data_dir, as_of)
        else:
            result = concept_history.capture(data_dir, as_of)

        probe_dir = data_dir / "ext_history" / "_probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        drift_path = probe_dir / "drift.jsonl"

        summary: list[str] = []
        for kind in ("gn_ths", "hy_ths"):
            res = result.get(kind, {})
            sha = concept_history.partition_sha256(data_dir, kind, as_of)
            part = concept_history.read_partition(data_dir, kind, as_of)
            rows = res.get("rows")
            effective_date = None
            if part is not None:
                if rows is None:
                    rows = len(part["rows"])
                fetched = part["manifest"].get("fetched_at") or ""
                effective_date = fetched[:10] if fetched else None
            line = {
                "date": as_of,
                "kind": kind,
                "sha256": sha,
                "rows": rows,
                "effective_date": effective_date,
            }
            with open(drift_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
            summary.append(f"{kind} sha={sha} rows={rows} eff={effective_date}")

        n_lines = 0
        if drift_path.exists():
            with open(drift_path, encoding="utf-8") as f:
                n_lines = sum(1 for _ in f)
        print(f"probe {as_of}: " + "; ".join(summary) + f"; drift.jsonl lines={n_lines}")
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
