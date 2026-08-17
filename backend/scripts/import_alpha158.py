#!/usr/bin/env python
"""幂等导入 Alpha158 公式语料到 factor registry。

把 app/research/alpha158.py 的 128 条 qlib Alpha158 转写公式注册为正式因子
修订版 (formal catalog), 之后走既有 admission 管线评估。幂等键 =
canonical expression: 已存在的跳过, 重复运行零副作用。

用法 (从 backend/ 目录):
    uv run --no-sync python -m scripts.import_alpha158           # 导入
    uv run --no-sync python -m scripts.import_alpha158 --dry-run # 只统计
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

from app.config import settings
from app.research.alpha158 import build_alpha158, provenance
from app.research.factor_dsl import parse_factor
from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository


def _database_path() -> Path:
    """research 库 = <data_dir>/operational.db (与 bootstrap.py 同源)。"""
    return settings.data_dir / "operational.db"


def _iter_existing(registry: FactorRegistry) -> Iterator[str]:
    for revision in registry.list_current():
        yield revision.canonical_expression


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只统计, 不写入")
    args = parser.parse_args(argv)

    repository = ResearchRepository(_database_path())
    repository.migrate()
    registry = FactorRegistry(repository)
    factors = build_alpha158()
    existing = set(_iter_existing(registry))

    created = 0
    skipped = 0
    for factor in factors:
        canonical = parse_factor(factor.expression).canonical_expression
        if canonical in existing:
            skipped += 1
            continue
        if args.dry_run:
            created += 1
            continue
        registry.create_factor(
            name=f"A158 {factor.name}",
            expression=factor.expression,
            description=factor.description,
            hypothesis=f"qlib Alpha158 {factor.name}: {factor.description}",
            provenance={**provenance(), "factor": factor.name},
        )
        created += 1

    verb = "would create" if args.dry_run else "created"
    print(f"alpha158: total={len(factors)} {verb}={created} skipped(existing)={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
