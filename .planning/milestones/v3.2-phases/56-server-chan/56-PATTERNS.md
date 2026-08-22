# Phase 56: Server酱微信推送 - Pattern Map

**Generated:** 2026-08-22
**Phase dir:** `.planning/phases/56-server-chan/`

## Analog Files (new file → closest existing analog)

| New File | Analog File | Similarity | Key Pattern |
|----------|-------------|------------|-------------|
| `SctChannel` (in delivery.py) | `FeishuChannel` (delivery.py:60-87) | 95% | `__init__(delivery_config, timeout_seconds)`, `deliver(event) -> {"status":"sent"}`, httpx.post + code!=0 检查 |
| `get_sct_sendkey()` / `set_sct_sendkey()` (preferences.py) | `get_feishu_webhook_url()` / `set_feishu_webhook_url()` (preferences.py:966-978) | 100% | `load().get(key, default)` / `save({key: value})` |
| `PUT /preferences/sct-sendkey` (settings.py) | `PUT /preferences/wecom-webhook` (settings.py:1115-1133) | 90% | Pydantic model + `preferences.set_*` + return dict |
| `POST /sct-test` (settings.py) | N/A (new, but test pattern from `wecom-bot-toggle`) | 70% | Send test msg → return status |
| SCT audit in `SctChannel.deliver()` | `chain.py` audit pattern (data_providers/chain.py:165-168) | 80% | `get_audit_repo().append(tool=..., category=..., ...)` |
| 去重 TTL | `quiet_period` in NotificationDeliveryService.enqueue() (delivery.py:175-181) | 75% | Skip + create "skipped" outcome |
| Settings.tsx SCT section | Settings.tsx feishu/telegram section | 85% | Input + save + test button |

## Key Code Excerpts

### NotificationChannel Protocol (delivery.py:43-48)
```python
class NotificationChannel(Protocol):
    name: str
    def __init__(self, delivery_config: DeliveryConfig, *, timeout_seconds: float = 2.0) -> None: ...
    def deliver(self, event: Mapping[str, Any]) -> Mapping[str, str]: ...
```

### _channel_for registration point (delivery.py:193-201)
```python
def _channel_for(self, delivery_config: DeliveryConfig) -> NotificationChannel:
    channel = self._channels.get(delivery_config.channel)
    if channel is not None:
        return channel
    if delivery_config.channel == FeishuChannel.name:
        return FeishuChannel(delivery_config, timeout_seconds=self._timeout_seconds)
    if delivery_config.channel == TelegramChannel.name:
        return TelegramChannel(delivery_config, timeout_seconds=self._timeout_seconds)
    raise ValueError("unsupported notification channel")
```

### ToolCallAuditRepository.append (envelope.py:148-165)
```python
def append(self, *, tool: str, category: str, params: dict | None = None,
           scope: str | None = None, principal: str | None = None,
           response_summary: str | None = None, raw: str | bytes | None = None,
           duration_ms: float = 0.0, error: str | None = None, ...) -> ToolCallEnvelope:
```

### Channel whitelist (preferences.py:736-741)
```python
REVIEW_PUSH_CHANNELS = {"feishu", "wecom"}
RULE_DELIVERY_CHANNELS = {"feishu", "telegram"}
```

### monitor_rules normalize (monitor_rules.py:38-39, 362-369)
```python
DELIVERY_CHANNELS = {"feishu", "telegram"}
# normalize strips channels not in whitelist
```

## Patterns to Follow

1. **Channel class pattern:** name attr → `__init__(delivery_config, timeout_seconds)` → `deliver(event) -> {"status":"sent"|"failed"}` + raise on failure
2. **DeliveryConfig:** `{channel: "sct", config: {"sendkey": "..."}}` — passed from delivery service
3. **Settings API:** Pydantic `BaseModel` input → `preferences.set_*` → return dict with saved value (脱敏)
4. **Audit:** Call `get_audit_repo().append()` inside `deliver()` with timing
5. **Safe errors:** Use `_safe_error()` to avoid leaking credentials in error messages
6. **Test fixture mode:** `_fixture_mode()` + `_fixture_receiver_url()` for test isolation

## Patterns to Avoid

- **Don't** create a separate `sct_adapter.py` file — SCT channel belongs in `delivery.py` with FeishuChannel/TelegramChannel
- **Don't** skip audit — every SCT push must have a ToolCallEnvelope
- **Don't** add SCT to `webhook_adapter.py` — that's for webhook URL validation; SCT uses a fixed API endpoint
- **Don't** forget to update `monitor_rules.normalize()` — it currently strips `wecom`; SCT must not be stripped
