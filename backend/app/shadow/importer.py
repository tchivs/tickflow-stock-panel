"""Bounded CSV/XLSX normalization into immutable Shadow import attempts."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO, StringIO
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence
from uuid import uuid4
from xml.etree import ElementTree
import sqlite3
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.shadow.artifacts import ShadowArtifactError, ShadowArtifactStore
from app.shadow.repository import ShadowRepository, ShadowRepositoryError


_CANONICAL_FIELDS = frozenset(
    {
        "broker_fill_id",
        "symbol",
        "side",
        "executed_at",
        "quantity",
        "price",
        "fees",
        "currency",
        "account_alias",
    }
)
_REQUIRED_FIELDS = frozenset({"symbol", "side", "executed_at", "quantity", "price"})
_MEDIA_BY_SUFFIX = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_SIDE_VALUES = {
    "买": "buy",
    "买入": "buy",
    "buy": "buy",
    "b": "buy",
    "卖": "sell",
    "卖出": "sell",
    "sell": "sell",
    "s": "sell",
}
_CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
_XML_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_TARGET_TIMEZONE = ZoneInfo("Asia/Shanghai")


class ShadowImportError(ValueError):
    """Untrusted import bytes or mapping failed a bounded safe check."""


@dataclass(frozen=True, slots=True)
class ShadowImportLimits:
    max_bytes: int = 8 * 1024 * 1024
    max_rows: int = 100_000
    max_columns: int = 64
    max_cell_chars: int = 4_096

    def __post_init__(self) -> None:
        if (
            self.max_bytes <= 0
            or self.max_rows <= 0
            or self.max_columns <= 0
            or self.max_cell_chars <= 0
        ):
            raise ValueError("Shadow import limits must be positive")


class ShadowImporter:
    """Parse only local caller-provided bytes; never connect to a broker or mutate accounts."""

    IMPORTER_VERSION = "shadow-importer-v1"
    MAPPING_VERSION = "shadow-canonical-fill-v1"

    def __init__(
        self,
        *,
        repository: ShadowRepository,
        artifact_store: ShadowArtifactStore,
        limits: ShadowImportLimits | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.limits = limits or ShadowImportLimits()
        self.repository.set_artifact_verifier(self.artifact_store.load)

    def preview(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
        mapping: Mapping[str, str],
        source_timezone: str,
    ) -> dict[str, Any]:
        suffix, canonical_mapping, timezone = self._validate_request(
            filename=filename,
            media_type=media_type,
            content=content,
            mapping=mapping,
            source_timezone=source_timezone,
        )
        rows, encoding = self._parse(
            suffix=suffix,
            content=content,
            mapping=canonical_mapping,
            source_timezone=timezone,
        )
        return {
            "status": "preview_ready",
            "encoding": encoding,
            "mapping_version": self.MAPPING_VERSION,
            "source_row_count": len(rows),
            "rows": rows,
        }

    def confirm_import(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
        mapping: Mapping[str, str],
        source_timezone: str,
        principal: str,
        source_label: str,
        supersedes_batch_id: str | None = None,
    ) -> dict[str, Any]:
        suffix, canonical_mapping, timezone = self._validate_request(
            filename=filename,
            media_type=media_type,
            content=content,
            mapping=mapping,
            source_timezone=source_timezone,
        )
        principal_value = self._bounded_text(principal, "principal", 128)
        source_label_value = self._bounded_text(source_label, "source label", 256)
        batch_id = uuid4().hex
        try:
            descriptor = self.artifact_store.create(
                batch_id=batch_id,
                content=content,
                media_type=media_type,
                source_label=source_label_value,
                original_name=Path(filename).name,
            )
        except ShadowArtifactError as error:
            raise ShadowImportError("raw import artifact could not be finalized") from error

        rows: list[dict[str, Any]] = []
        diagnostics: list[dict[str, object]] = []
        status = "completed"
        rejected_count = 0
        try:
            rows, _encoding = self._parse(
                suffix=suffix,
                content=content,
                mapping=canonical_mapping,
                source_timezone=timezone,
            )
        except ShadowImportError:
            status = "rejected"
            rows = []
            rejected_count = 1
            diagnostics = [
                {
                    "severity": "error",
                    "code": "parse_rejected",
                    "message": "The local execution log could not be safely normalized.",
                }
            ]

        trade_rows = [
            {
                "id": uuid4().hex,
                **row,
            }
            for row in rows
        ]
        try:
            return self.repository.append_import_batch(
                batch_id=batch_id,
                principal=principal_value,
                raw_artifact=descriptor,
                content_sha256=sha256(content).hexdigest(),
                source_label=source_label_value,
                importer_version=self.IMPORTER_VERSION,
                mapping_version=self.MAPPING_VERSION,
                supersedes_batch_id=supersedes_batch_id,
                source_row_count=len(rows) if status == "completed" else 0,
                trades=trade_rows,
                rejected_row_count=rejected_count,
                diagnostics=diagnostics,
                status=status,
            )
        except (ShadowRepositoryError, KeyError, sqlite3.Error) as error:
            try:
                self.artifact_store.discard_uncommitted(
                    batch_id=batch_id, descriptor=descriptor
                )
            except ShadowArtifactError:
                pass
            raise ShadowImportError("import attempt could not be persisted") from error

    def _validate_request(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
        mapping: Mapping[str, str],
        source_timezone: str,
    ) -> tuple[str, dict[str, str], ZoneInfo]:
        if not isinstance(filename, str) or not filename or len(filename) > 255:
            raise ShadowImportError("filename is invalid")
        if Path(filename).name != filename or any(separator in filename for separator in ("/", "\\")):
            raise ShadowImportError("filename must not contain a path")
        suffix = Path(filename).suffix.lower()
        if suffix not in _MEDIA_BY_SUFFIX or media_type != _MEDIA_BY_SUFFIX[suffix]:
            raise ShadowImportError("file extension and media type are not an approved pair")
        if not isinstance(content, bytes) or not content or len(content) > self.limits.max_bytes:
            raise ShadowImportError("file exceeds the configured byte boundary")
        if not isinstance(mapping, Mapping) or not mapping:
            raise ShadowImportError("mapping is required")
        if not set(mapping).issubset(_CANONICAL_FIELDS) or not _REQUIRED_FIELDS.issubset(mapping):
            raise ShadowImportError("mapping contains missing or unsupported canonical fields")
        canonical_mapping: dict[str, str] = {}
        for field, column in mapping.items():
            if not isinstance(column, str) or not column.strip() or len(column) > 128:
                raise ShadowImportError("mapping source column is invalid")
            canonical_mapping[str(field)] = column.strip()
        if len(set(canonical_mapping.values())) != len(canonical_mapping):
            raise ShadowImportError("mapping source columns must be unique")
        try:
            timezone = ZoneInfo(source_timezone)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
            raise ShadowImportError("source timezone is invalid") from error
        return suffix, canonical_mapping, timezone

    def _parse(
        self,
        *,
        suffix: str,
        content: bytes,
        mapping: Mapping[str, str],
        source_timezone: ZoneInfo,
    ) -> tuple[list[dict[str, Any]], str]:
        if suffix == ".csv":
            source_rows, encoding = self._parse_csv(content)
        elif suffix == ".xlsx":
            source_rows, encoding = self._parse_xlsx(content), "xlsx"
        else:
            raise ShadowImportError("unsupported import format")
        if not source_rows:
            raise ShadowImportError("execution log contains no rows")
        headers = list(source_rows[0])
        if len(headers) > self.limits.max_columns or len(set(headers)) != len(headers):
            raise ShadowImportError("execution log column boundary is invalid")
        missing_columns = set(mapping.values()) - set(headers)
        if missing_columns:
            raise ShadowImportError("mapped source columns are unavailable")
        if len(source_rows) > self.limits.max_rows:
            raise ShadowImportError("execution log exceeds the configured row boundary")
        normalized: list[dict[str, Any]] = []
        for ordinal, source in enumerate(source_rows, start=1):
            if set(source) != set(headers):
                raise ShadowImportError("execution log rows have inconsistent columns")
            for value in source.values():
                if len(value) > self.limits.max_cell_chars:
                    raise ShadowImportError("execution log cell exceeds the configured boundary")
            normalized.append(
                self._normalize_row(
                    source=source,
                    mapping=mapping,
                    source_timezone=source_timezone,
                    ordinal=ordinal,
                )
            )
        return normalized, encoding

    def _parse_csv(self, content: bytes) -> tuple[list[dict[str, str]], str]:
        decoded: str | None = None
        encoding = ""
        for candidate in ("utf-8-sig", "gb18030"):
            try:
                decoded = content.decode(candidate, errors="strict")
                encoding = "utf-8" if candidate == "utf-8-sig" else candidate
                break
            except UnicodeDecodeError:
                continue
        if decoded is None or "\x00" in decoded:
            raise ShadowImportError("CSV encoding is not UTF-8 or GB18030")
        try:
            reader = csv.DictReader(StringIO(decoded, newline=""))
            if not reader.fieldnames or any(field is None or not field for field in reader.fieldnames):
                raise ShadowImportError("CSV header is invalid")
            if len(reader.fieldnames) > self.limits.max_columns:
                raise ShadowImportError("execution log exceeds the configured column boundary")
            rows: list[dict[str, str]] = []
            for source in reader:
                if None in source or any(value is None for value in source.values()):
                    raise ShadowImportError("CSV row shape is invalid")
                if len(rows) >= self.limits.max_rows:
                    raise ShadowImportError("execution log exceeds the configured row boundary")
                row = {str(key): str(value) for key, value in source.items()}
                if any(len(value) > self.limits.max_cell_chars for value in row.values()):
                    raise ShadowImportError("execution log cell exceeds the configured boundary")
                rows.append(row)
            return rows, encoding
        except (csv.Error, UnicodeError) as error:
            raise ShadowImportError("CSV could not be safely parsed") from error

    def _parse_xlsx(self, content: bytes) -> list[dict[str, str]]:
        try:
            with ZipFile(BytesIO(content)) as archive:
                infos = archive.infolist()
                if not infos or len(infos) > 256:
                    raise ShadowImportError("XLSX package boundary is invalid")
                maximum_uncompressed = max(
                    self.limits.max_bytes * 32,
                    self.limits.max_rows * min(self.limits.max_columns, 16) * 8,
                )
                total_uncompressed = 0
                names: set[str] = set()
                for info in infos:
                    path = PurePosixPath(info.filename)
                    if (
                        path.is_absolute()
                        or ".." in path.parts
                        or info.flag_bits & 0x1
                        or (info.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise ShadowImportError("XLSX package contains an unsafe member")
                    total_uncompressed += info.file_size
                    if total_uncompressed > maximum_uncompressed:
                        raise ShadowImportError("XLSX package exceeds the decompression boundary")
                    names.add(info.filename)
                if any(name.lower().endswith(("vbaproject.bin", ".exe", ".dll")) for name in names):
                    raise ShadowImportError("XLSX package contains executable content")
                shared = self._xlsx_shared_strings(archive, names)
                sheet_name = self._xlsx_sheet_name(names)
                root = ElementTree.fromstring(archive.read(sheet_name))
        except ShadowImportError:
            raise
        except (BadZipFile, KeyError, OSError, ElementTree.ParseError, UnicodeError) as error:
            raise ShadowImportError("XLSX could not be safely parsed") from error

        rows_by_number: dict[int, dict[int, str]] = {}
        for cell in root.findall(f".//{{{_XML_MAIN}}}c"):
            reference = cell.attrib.get("r", "")
            matched = _CELL_REF.fullmatch(reference)
            if matched is None:
                raise ShadowImportError("XLSX cell reference is invalid")
            column = self._column_number(matched.group(1))
            row_number = int(matched.group(2))
            if column > self.limits.max_columns or row_number > self.limits.max_rows + 1:
                raise ShadowImportError("XLSX exceeds configured row or column boundaries")
            value = self._xlsx_cell_value(cell, shared)
            if len(value) > self.limits.max_cell_chars:
                raise ShadowImportError("execution log cell exceeds the configured boundary")
            rows_by_number.setdefault(row_number, {})[column] = value
        if not rows_by_number or 1 not in rows_by_number:
            raise ShadowImportError("XLSX header is unavailable")
        header_cells = rows_by_number[1]
        if not header_cells:
            raise ShadowImportError("XLSX header is unavailable")
        maximum_column = max(header_cells)
        headers = [header_cells.get(index, "") for index in range(1, maximum_column + 1)]
        if any(not header for header in headers) or len(set(headers)) != len(headers):
            raise ShadowImportError("XLSX header is invalid")
        output: list[dict[str, str]] = []
        for row_number in sorted(number for number in rows_by_number if number > 1):
            cells = rows_by_number[row_number]
            output.append(
                {
                    header: cells.get(index, "")
                    for index, header in enumerate(headers, start=1)
                }
            )
        return output

    def _normalize_row(
        self,
        *,
        source: Mapping[str, str],
        mapping: Mapping[str, str],
        source_timezone: ZoneInfo,
        ordinal: int,
    ) -> dict[str, Any]:
        def mapped(field: str, default: str = "") -> str:
            column = mapping.get(field)
            return default if column is None else source[column].strip()

        symbol = mapped("symbol").upper()
        if not symbol or len(symbol) > 32:
            raise ShadowImportError("symbol value is invalid")
        side = _SIDE_VALUES.get(mapped("side").lower())
        if side is None:
            raise ShadowImportError("side value is invalid")
        executed_at = self._normalized_time(mapped("executed_at"), source_timezone)
        quantity = self._finite_number(mapped("quantity"), "quantity", positive=True)
        price = self._finite_number(mapped("price"), "price", positive=False)
        fees = self._finite_number(mapped("fees", "0") or "0", "fees", positive=False)
        currency = (mapped("currency", "CNY") or "CNY").upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ShadowImportError("currency value is invalid")
        account_alias = mapped("account_alias", "unattributed") or "unattributed"
        if len(account_alias) > 128:
            raise ShadowImportError("account alias is invalid")
        broker_fill_id = mapped("broker_fill_id") or None
        if broker_fill_id is not None and len(broker_fill_id) > 128:
            raise ShadowImportError("broker fill identifier is invalid")

        duplicate_payload = {
            "account_alias": account_alias,
            "symbol": symbol,
            "side": side,
            "executed_at": executed_at,
            "quantity": quantity,
            "price": price,
            "fees": fees,
            "currency": currency,
        }
        duplicate_group_hash = self._digest(duplicate_payload)
        identity_payload = (
            {"broker_fill_id": broker_fill_id}
            if broker_fill_id is not None
            else {**duplicate_payload, "source_row_ordinal": ordinal}
        )
        normalized = {
            "broker_fill_id": broker_fill_id,
            **duplicate_payload,
        }
        return {
            "row_identity": self._digest(identity_payload),
            "duplicate_group_hash": duplicate_group_hash,
            "broker_fill_id": broker_fill_id,
            "account_alias": account_alias,
            "symbol": symbol,
            "side": side,
            "executed_at": executed_at,
            "quantity": quantity,
            "price": price,
            "fees": fees,
            "currency": currency,
            "source_row_ordinal": ordinal,
            "source_values": dict(source),
            "normalized": normalized,
        }

    @staticmethod
    def _normalized_time(raw: str, source_timezone: ZoneInfo) -> str:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise ShadowImportError("execution timestamp is invalid") from error
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=source_timezone)
        return parsed.astimezone(_TARGET_TIMEZONE).isoformat()

    @staticmethod
    def _finite_number(raw: str, field: str, *, positive: bool) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ShadowImportError(f"{field} value is invalid") from error
        if not math.isfinite(value) or value < 0 or (positive and value <= 0):
            raise ShadowImportError(f"{field} value is invalid")
        return value

    @staticmethod
    def _digest(value: object) -> str:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    @staticmethod
    def _bounded_text(value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ShadowImportError(f"{field} is invalid")
        return value.strip()

    @staticmethod
    def _xlsx_shared_strings(archive: ZipFile, names: set[str]) -> list[str]:
        if "xl/sharedStrings.xml" not in names:
            return []
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        return [
            "".join(node.text or "" for node in item.findall(f".//{{{_XML_MAIN}}}t"))
            for item in root.findall(f"{{{_XML_MAIN}}}si")
        ]

    @staticmethod
    def _xlsx_sheet_name(names: set[str]) -> str:
        candidates = sorted(
            name
            for name in names
            if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", name)
        )
        if not candidates:
            raise ShadowImportError("XLSX contains no worksheet")
        return candidates[0]

    @staticmethod
    def _xlsx_cell_value(cell: ElementTree.Element, shared: Sequence[str]) -> str:
        formula = cell.find(f"{{{_XML_MAIN}}}f")
        if formula is not None:
            return f"={formula.text or ''}"
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            return "".join(
                node.text or "" for node in cell.findall(f".//{{{_XML_MAIN}}}t")
            )
        value_node = cell.find(f"{{{_XML_MAIN}}}v")
        value = "" if value_node is None or value_node.text is None else value_node.text
        if cell_type == "s":
            try:
                return shared[int(value)]
            except (IndexError, TypeError, ValueError) as error:
                raise ShadowImportError("XLSX shared string reference is invalid") from error
        if cell_type == "b":
            return "true" if value == "1" else "false"
        return value

    @staticmethod
    def _column_number(letters: str) -> int:
        value = 0
        for letter in letters:
            value = value * 26 + ord(letter) - ord("A") + 1
        return value

