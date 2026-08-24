"""Bounded Feishu, Telegram, and Server酱 (SCT) delivery with durable, credential-safe outcomes."""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import httpx

from app.operational.repository import OperationalRepository
from app.services import webhook_adapter

logger = logging.getLogger(__name__)

_TELEGRAM_API_ORIGIN = "https://api.telegram.org"
_SAFE_ERROR = "delivery failed"

# Server酱 (SCT) dedup + daily limit (D-05)
SCT_DEDUP_TTL = 300.0  # seconds — 5 minute dedup window
SCT_DAILY_LIMIT = 200  # max SCT pushes per day before degradation


def _fixture_mode() -> bool:
    return os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes"}


def _fixture_receiver_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "receiver" or not parsed.path.startswith("/"):
        raise ValueError("fixture delivery target must be an internal receiver URL")
    return url


@dataclass(frozen=True)
class DeliveryConfig:
    """The approved configuration for exactly one external channel."""

    channel: str
    config: Mapping[str, Any]


class NotificationChannel(Protocol):
    """A narrow, synchronous transport invoked only by the bounded worker."""

    name: str

    def deliver(self, event: Mapping[str, Any]) -> Mapping[str, str]: ...


def _message(event: Mapping[str, Any]) -> tuple[str, str]:
    source = str(event.get("source") or "alert")
    title = f"AthenaQuant · {source}"
    symbol = str(event.get("symbol") or "").strip()
    name = str(event.get("name") or "").strip()
    message = str(event.get("message") or "").strip()
    return title, " ".join(part for part in (symbol, name, message) if part)


class FeishuChannel:
    name = "feishu"

    def __init__(self, delivery_config: DeliveryConfig, *, timeout_seconds: float = 2.0) -> None:
        if delivery_config.channel != self.name:
            raise ValueError("Feishu delivery config must use the feishu channel")
        self._fixture_url = ""
        self._webhook = str(delivery_config.config.get("webhook") or "").strip()
        self._secret = str(delivery_config.config.get("secret") or "").strip()
        if _fixture_mode():
            self._fixture_url = _fixture_receiver_url(delivery_config.config.get("fixture_url"))
        elif not webhook_adapter.is_valid_feishu_url(self._webhook):
            raise ValueError("Feishu webhook must use the approved hook prefix")
        self._timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)

    def deliver(self, event: Mapping[str, Any]) -> Mapping[str, str]:
        title, body = _message(event)
        payload = webhook_adapter.build_feishu_text_payload(title, body, self._secret)
        response = httpx.post(self._fixture_url or self._webhook, json=payload, timeout=self._timeout)
        if response.status_code != 200:
            raise RuntimeError(f"Feishu returned HTTP {response.status_code}")
        try:
            body_json = response.json()
        except ValueError:
            return {"status": "sent"}
        if isinstance(body_json, dict) and body_json.get("code", body_json.get("StatusCode", 0)) != 0:
            raise RuntimeError("Feishu rejected the notification")
        return {"status": "sent"}


class TelegramChannel:
    name = "telegram"

    def __init__(self, delivery_config: DeliveryConfig, *, timeout_seconds: float = 2.0) -> None:
        if delivery_config.channel != self.name:
            raise ValueError("Telegram delivery config must use the telegram channel")
        self._fixture_url = ""
        if "url" in delivery_config.config:
            raise ValueError("Telegram delivery does not accept a caller-provided URL")
        self._bot_token = str(delivery_config.config.get("bot_token") or "").strip()
        self._chat_id = str(delivery_config.config.get("chat_id") or "").strip()
        if _fixture_mode():
            self._fixture_url = _fixture_receiver_url(delivery_config.config.get("fixture_url"))
        elif not self._bot_token or not self._chat_id:
            raise ValueError("Telegram requires bot_token and chat_id")
        self._timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)

    def deliver(self, event: Mapping[str, Any]) -> Mapping[str, str]:
        title, body = _message(event)
        url = self._fixture_url or f"{_TELEGRAM_API_ORIGIN}/bot{quote(self._bot_token, safe='')}/sendMessage"
        response = httpx.post(
            url,
            json={"chat_id": self._chat_id, "text": f"{title}\n{body}".strip()},
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Telegram returned HTTP {response.status_code}")
        try:
            body_json = response.json()
        except ValueError:
            return {"status": "sent"}
        if isinstance(body_json, dict) and body_json.get("ok") is False:
            raise RuntimeError("Telegram rejected the notification")
        return {"status": "sent"}

class SctChannel:
    name = "sct"

    def __init__(self, delivery_config: DeliveryConfig, *, timeout_seconds: float = 2.0) -> None:
        if delivery_config.channel != self.name:
            raise ValueError("SCT delivery config must use the sct channel")
        self._fixture_url = ""
        self._sendkey = str(delivery_config.config.get("sendkey") or "").strip()
        if _fixture_mode():
            self._fixture_url = _fixture_receiver_url(delivery_config.config.get("fixture_url"))
        elif not self._sendkey:
            raise ValueError("SCT requires a sendkey")
        self._timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)

    def deliver(self, event: Mapping[str, Any]) -> Mapping[str, str]:
        from app.audit.service import get_audit_repo

        title, body = _message(event)
        url = self._fixture_url or f"https://sctapi.ftqq.com/{self._sendkey}.send"
        t0 = time.perf_counter()
        error: str | None = None
        response: httpx.Response | None = None
        try:
            response = httpx.post(
                url,
                data={"title": title, "desp": body},
                timeout=self._timeout,
            )
            if response.status_code != 200:
                raise RuntimeError(f"SCT returned HTTP {response.status_code}")
            try:
                body_json = response.json()
            except ValueError:
                body_json = None
                return {"status": "sent"}
            if isinstance(body_json, dict) and body_json.get("code", 0) != 0:
                raise RuntimeError("Server酱 rejected the notification")
            return {"status": "sent"}
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            audit_repo = get_audit_repo()
            if audit_repo is not None:
                try:
                    response_summary = None
                    raw_content = None
                    if response is not None:
                        response_summary = str(response.text)[:200] if response.text else None
                        raw_content = response.content[:500]
                    audit_repo.append(
                        tool="sct",
                        category="notification",
                        scope=f"notification:{event.get('id', '')}",
                        response_summary=response_summary,
                        raw=raw_content,
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        error=error,
                    )
                except Exception:
                    pass  # audit failure must not block delivery


def _safe_error(error: Exception, config: Mapping[str, Any]) -> str:
    """Return bounded diagnostics without retaining credentials or endpoint details."""
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, httpx.HTTPStatusError):
        return f"http_{error.response.status_code}"
    message = str(error)
    for value in config.values():
        if isinstance(value, str) and value:
            message = message.replace(value, "[redacted]")
    message = re.sub(r"https?://\S+", "[redacted-url]", message)
    message = message.strip()[:160]
    if not message or "[redacted" in message or "token" in message.lower() or "secret" in message.lower():
        return _SAFE_ERROR
    return message


class NotificationDeliveryService:
    """Creates one durable outcome per channel and updates it independently of alerts."""

    def __init__(
        self,
        *,
        repository: OperationalRepository,
        channels: Mapping[str, NotificationChannel] | None = None,
        max_workers: int = 2,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._repository = repository
        self._channels = dict(channels or {})
        self._timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="notification-delivery",
        )
        self._futures: set[Future[None]] = set()
        # SCT dedup + daily limit (D-05) — 线程安全锁
        self._dedup_lock = threading.Lock()
        self._dedup_cache: dict[str, float] = {}
        self._daily_count = 0
        self._daily_date = date.today()
        # 批量摘要: 超过每日上限后收集被跳过事件, 仅发一条摘要 (D-05 补齐)
        self._overflow_events: list[str] = []
        self._overflow_summary_sent = False
    def enqueue(
        self,
        *,
        event_id: str,
        channel_configs: list[DeliveryConfig],
        quiet_period: bool = False,
        bypass_quiet_period: bool = False,
    ) -> None:
        event = self._repository.get_alert_event(event_id)
        if event is None:
            raise ValueError("delivery event does not exist")
        for delivery_config in channel_configs:
            if quiet_period and not bypass_quiet_period:
                self._repository.create_delivery_outcome(
                    event_id=event_id,
                    channel=delivery_config.channel,
                    status="skipped",
                    error="quiet_period",
                )
                continue
            # SCT dedup + daily limit (D-05) — 线程安全
            if delivery_config.channel == SctChannel.name:
                with self._dedup_lock:
                    now = time.time()
                    today = date.today()
                    if self._daily_date != today:
                        self._daily_count = 0
                        self._daily_date = today
                        self._overflow_events = []
                        self._overflow_summary_sent = False
                    dedup_key = f"{event.get('rule_id', '')}:{event.get('symbol', '')}:{event.get('type', '')}"
                    last_seen = self._dedup_cache.get(dedup_key)
                    if last_seen is not None and (now - last_seen) < SCT_DEDUP_TTL:
                        self._repository.create_delivery_outcome(
                            event_id=event_id,
                            channel=delivery_config.channel,
                            status="skipped",
                            error="dedup",
                        )
                        continue
                    if self._daily_count >= SCT_DAILY_LIMIT:
                        # 批量摘要: 收集被跳过事件 ID, 首次超限时发送一条摘要推送
                        self._overflow_events.append(event_id)
                        self._repository.create_delivery_outcome(
                            event_id=event_id,
                            channel=delivery_config.channel,
                            status="skipped",
                            error="daily_limit_exceeded",
                        )
                        if not self._overflow_summary_sent:
                            self._overflow_summary_sent = True
                            self._send_overflow_summary(delivery_config)
                        continue
                    self._dedup_cache[dedup_key] = now
                    self._daily_count += 1
            self._repository.create_delivery_outcome(
                event_id=event_id,
                channel=delivery_config.channel,
                status="pending",
                error=None,
            )
            future = self._executor.submit(self._deliver, event_id, event, delivery_config)
            self._futures.add(future)
            future.add_done_callback(self._futures.discard)

    def _channel_for(self, delivery_config: DeliveryConfig) -> NotificationChannel:
        channel = self._channels.get(delivery_config.channel)
        if channel is not None:
            return channel
        if delivery_config.channel == FeishuChannel.name:
            return FeishuChannel(delivery_config, timeout_seconds=self._timeout_seconds)
        if delivery_config.channel == TelegramChannel.name:
            return TelegramChannel(delivery_config, timeout_seconds=self._timeout_seconds)
        if delivery_config.channel == SctChannel.name:
            return SctChannel(delivery_config, timeout_seconds=self._timeout_seconds)
        raise ValueError("unsupported notification channel")

    def _deliver(self, event_id: str, event: Mapping[str, Any], delivery_config: DeliveryConfig) -> None:
        try:
            result = self._channel_for(delivery_config).deliver(event)
            status = str(result.get("status", "sent"))
            if status not in {"sent", "failed", "skipped"}:
                status = "failed"
            raw_error = result.get("error") if status != "sent" else None
            safe_error = (
                _safe_error(RuntimeError(str(raw_error)), delivery_config.config)
                if raw_error is not None
                else None
            )
            self._repository.update_delivery_outcome(
                event_id=event_id,
                channel=delivery_config.channel,
                status=status,
                error=safe_error,
            )
        except Exception as error:
            logger.warning("notification delivery failed for %s", delivery_config.channel)
            self._repository.update_delivery_outcome(
                event_id=event_id,
                channel=delivery_config.channel,
                status="failed",
                error=_safe_error(error, delivery_config.config),
            )


    def _send_overflow_summary(self, delivery_config: DeliveryConfig) -> None:
        """超限后发送一条批量摘要推送 (D-05 补齐)。

        将当日被跳过的事件聚合为一条摘要, 通过 SCT 渠道发送,
        避免逐条推送淹没用户。摘要不占用每日配额。
        """
        try:
            channel = self._channel_for(delivery_config)
            count = max(self._daily_count, SCT_DAILY_LIMIT)
            summary_event = {
                "id": f"overflow_summary_{date.today()}",
                "rule_id": "system",
                "symbol": "",
                "type": "daily_limit_summary",
                "severity": "info",
                "message": f"今日 SCT 推送已达上限({count}条), 后续告警已聚合跳过",
                "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            }
            channel.deliver(summary_event)
        except Exception:
            logger.warning("SCT overflow summary delivery failed")
    def drain(self, timeout: float | None = None) -> None:
        """Wait for currently queued work in tests and controlled shutdown paths."""
        futures = tuple(self._futures)
        if futures:
            wait(futures, timeout=timeout)
