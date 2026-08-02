"""Phase 11 不可变权重/协方差工件存储 (PFOL-04).

职责: PortfolioArtifactService 在应用数据根下的 research_artifacts/<run_id>/
写入不可变 JSON 工件 —— 命名空间与每个文件都用 O_EXCL 独占创建 + fsync +
sha256 校验和, 读取时校验和必须匹配 (镜像 research/artifacts.py:_write_json
与 backtest/frozen_panel.py:load 的既有纪律)。

不知道: 求解逻辑 (optimizer.py)、风险模型 (risk.py)、运行记录
(repository.py 持有 run 行与 output_sha256)。
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np

_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


class ArtifactWriteError(RuntimeError):
    """An optimization artifact bundle could not be made durably immutable."""


class ArtifactReadError(RuntimeError):
    """An optimization artifact read failed the checksum-verification gate."""


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """A content-addressed reference to one managed optimization artifact."""

    run_id: str
    relative_path: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PortfolioArtifactService:
    """Writes optimization weight/covariance artifacts below one app-owned root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve() / "research_artifacts"

    def write_bundle(
        self,
        *,
        run_id: str,
        weights: dict[str, float],
        baseline_weights: dict[str, float],
        covariance: np.ndarray | None = None,
    ) -> list[ArtifactDescriptor]:
        """Create an all-new namespace and immutable JSON artifact files.

        命名空间 O_EXCL 创建: 二次写入同一 run_id 直接失败 (immutable,
        绝不覆盖)。weights / baseline_weights 必写; covariance 可选 (作为
        二维列表序列化, 供 Phase 12 协方差工件接缝使用)。

        Args:
            run_id: 32 位小写 hex (与 run 行 id 一致)。
            weights: {symbol: weight} 输出权重。
            baseline_weights: {symbol: weight} 基线权重。
            covariance: (n, n) 协方差矩阵, 可选。

        Returns:
            每个写入文件的 ArtifactDescriptor 列表 (含 checksum_sha256)。
        """
        namespace = self._namespace(run_id)
        try:
            namespace.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise ArtifactWriteError(f"artifact namespace already exists for run {run_id}") from error
        except OSError as error:
            raise ArtifactWriteError(f"could not create artifact namespace: {error}") from error

        descriptors = [
            self._write_json(namespace, run_id, "weights.json", dict(weights)),
            self._write_json(namespace, run_id, "baseline_weights.json", dict(baseline_weights)),
        ]
        try:
            if covariance is not None:
                # 协方差工件按 8 位小数规范化 (与 risk.covariance_sha256 的摘要口径
                # 字节一致): 工件字节的 sha256 == risk_model_json 里的 covariance_sha256,
                # 使 Phase 12 能按摘要做 checksum 校验读取 (PFOL-01/04)。
                rounded = np.asarray(covariance, dtype=float).round(8)
                descriptors.append(
                    self._write_json(namespace, run_id, "covariance.json", rounded.tolist())
                )
        except Exception:
            # IN-05: 中段写入失败时清理命名空间, 绝不留下孤儿的部分 bundle
            # (先写好的文件与 run 记录不一致, 只会污染审计面)。
            shutil.rmtree(namespace, ignore_errors=True)
            raise
        return descriptors

    def read_artifact(self, relative_path: str, *, checksum_sha256: str) -> bytes:
        """Checksum-verified artifact read (frozen_panel load pattern).

        Args:
            relative_path: 相对 research_artifacts/ 的工件路径
                (如 ``research_artifacts/<run_id>/weights.json``)。
            checksum_sha256: 期望的 sha256 (来自 run 行 output_sha256 等)。

        Returns:
            工件字节。校验和不匹配 / 文件缺失时抛 ArtifactReadError。
        """
        path = self.root.parent / relative_path
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ArtifactReadError("artifact path escapes the managed root") from error
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ArtifactReadError(f"artifact not found: {relative_path}") from error
        if sha256(content).hexdigest() != checksum_sha256:
            raise ArtifactReadError("artifact checksum mismatch")
        return content

    def write_analysis_artifact(
        self,
        run_id: str,
        *,
        subdir: str,
        filename: str,
        payload: object,
    ) -> ArtifactDescriptor:
        """Write an analysis artifact inside the run's EXISTING namespace.

        Phase 12: attribution/drawdown analyzers land their O_EXCL + fsync +
        sha256 artifacts under ``research_artifacts/<run_id>/<subdir>/``. The run
        namespace is owned by the optimization bundle (``write_bundle``) — it is
        NEVER recreated here (that would break the O_EXCL run-namespace
        discipline); a missing namespace raises ``ArtifactWriteError``.

        Args:
            run_id: 32 位小写 hex (与 run 行 id 一致)。
            subdir: 命名空间内的一级子目录 (managed basename, 拒绝 ``..`` 与分隔符)。
            filename: 文件名 (managed basename)。
            payload: JSON 可序列化对象。

        Returns:
            ArtifactDescriptor (含 checksum_sha256, 供证据行 output_sha256 使用)。
        """
        subdir = self._managed_name(subdir, field="subdir")
        filename = self._managed_name(filename, field="filename")
        namespace = self._namespace(run_id)
        if not namespace.is_dir():
            raise ArtifactWriteError(f"artifact namespace does not exist for run {run_id}")
        target = namespace / subdir
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ArtifactWriteError(f"could not create analysis subdir: {error}") from error
        return self._write_json(target, run_id, filename, payload)

    def _namespace(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise ArtifactWriteError("run ID must be an opaque UUID hex value")
        namespace = self.root / run_id
        try:
            namespace.relative_to(self.root)
        except ValueError as error:
            raise ArtifactWriteError("artifact namespace escapes the managed root") from error
        return namespace

    @staticmethod
    def _managed_name(name: str, *, field: str) -> str:
        """Reject ``..``, empty names, and any path separators (escape guard)."""
        if not isinstance(name, str) or name in ("", ".", ".."):
            raise ArtifactWriteError(f"{field} must be a managed basename")
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ArtifactWriteError(f"{field} must be a managed basename")
        return name

    def _write_json(
        self,
        namespace: Path,
        run_id: str,
        filename: str,
        payload: object,
    ) -> ArtifactDescriptor:
        filename = self._managed_name(filename, field="artifact filename")
        path = namespace / filename
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ArtifactWriteError("artifact path escapes the managed root") from error

        # 规范化字节使 checksum 独立可复验且稳定。
        content = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ArtifactWriteError(f"artifact already exists: {filename}") from error
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            # 部分写入的文件绝不能作为完成的工件呈现。
            path.unlink(missing_ok=True)
            raise

        return ArtifactDescriptor(
            run_id=run_id,
            relative_path=path.relative_to(self.root.parent).as_posix(),
            content_type="application/json",
            byte_size=len(content),
            checksum_sha256=sha256(content).hexdigest(),
            created_at=datetime.now(UTC).isoformat(),
        )
