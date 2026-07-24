"""JSON mapping config loader and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from .keys import KeyError_, normalize_key_name, normalize_modifiers, parse_combo, resolve_vk


@dataclass(frozen=True)
class Trigger:
    key: str
    key_vk: int
    modifiers: FrozenSet[str]
    tap: str  # "single" | "double"


@dataclass(frozen=True)
class Action:
    type: str
    sequence: Tuple[str, ...]
    # Pre-parsed combos: list of (mods, vk)
    parsed_sequence: Tuple[Tuple[FrozenSet[str], int], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Mapping:
    id: str
    trigger: Trigger
    action: Action
    # Per-mapping double-tap window; None = use settings.doubleTapMs
    double_tap_ms: Optional[int] = None


@dataclass(frozen=True)
class Settings:
    double_tap_ms: int = 280
    sequence_delay_ms: int = 30


@dataclass(frozen=True)
class AppConfig:
    version: int
    settings: Settings
    mappings: Tuple[Mapping, ...]


class ConfigError(ValueError):
    pass


def _require_dict(obj: Any, label: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise ConfigError(f"{label} must be an object")
    return obj


def _parse_positive_ms(raw: Any, label: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be an integer (milliseconds)") from exc
    if value <= 0:
        raise ConfigError(f"{label} must be > 0")
    return value


def _parse_settings(raw: Any) -> Settings:
    if raw is None:
        return Settings()
    data = _require_dict(raw, "settings")
    double_tap = _parse_positive_ms(data.get("doubleTapMs", 280), "settings.doubleTapMs")
    seq_delay = int(data.get("sequenceDelayMs", 30))
    if seq_delay < 0:
        raise ConfigError("settings.sequenceDelayMs must be >= 0")
    return Settings(double_tap_ms=double_tap, sequence_delay_ms=seq_delay)


def _parse_trigger(raw: Any, mapping_id: str) -> Trigger:
    data = _require_dict(raw, f"mappings[{mapping_id}].trigger")
    if "key" not in data:
        raise ConfigError(f"mappings[{mapping_id}].trigger.key is required")
    key = normalize_key_name(str(data["key"]))
    try:
        key_vk = resolve_vk(key)
    except KeyError_ as exc:
        raise ConfigError(str(exc)) from exc
    try:
        mods = normalize_modifiers(data.get("modifiers") or [])
    except KeyError_ as exc:
        raise ConfigError(str(exc)) from exc
    tap = normalize_key_name(str(data.get("tap", "single")))
    if tap not in ("single", "double"):
        raise ConfigError(
            f"mappings[{mapping_id}].trigger.tap must be 'single' or 'double', got {tap!r}"
        )
    return Trigger(key=key, key_vk=key_vk, modifiers=mods, tap=tap)


def _parse_action(raw: Any, mapping_id: str) -> Action:
    data = _require_dict(raw, f"mappings[{mapping_id}].action")
    action_type = str(data.get("type", "keys"))
    if action_type != "keys":
        raise ConfigError(
            f"mappings[{mapping_id}].action.type must be 'keys' in v1, got {action_type!r}"
        )
    seq_raw = data.get("sequence")
    if not isinstance(seq_raw, list) or not seq_raw:
        raise ConfigError(
            f"mappings[{mapping_id}].action.sequence must be a non-empty array"
        )
    sequence: List[str] = []
    parsed: List[Tuple[FrozenSet[str], int]] = []
    for item in seq_raw:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                f"mappings[{mapping_id}].action.sequence items must be non-empty strings"
            )
        sequence.append(item.strip())
        try:
            parsed.append(parse_combo(item))
        except KeyError_ as exc:
            raise ConfigError(
                f"mappings[{mapping_id}].action.sequence invalid combo {item!r}: {exc}"
            ) from exc
    return Action(
        type=action_type,
        sequence=tuple(sequence),
        parsed_sequence=tuple(parsed),
    )


def _parse_mapping(raw: Any, index: int) -> Mapping:
    data = _require_dict(raw, f"mappings[{index}]")
    mapping_id = str(data.get("id") or f"mapping-{index}")
    if "trigger" not in data or "action" not in data:
        raise ConfigError(f"mappings[{mapping_id}] requires trigger and action")
    trigger = _parse_trigger(data["trigger"], mapping_id)
    # Per-mapping override: top-level doubleTapMs, or trigger.doubleTapMs
    raw_dt = data.get("doubleTapMs")
    if raw_dt is None and isinstance(data.get("trigger"), dict):
        raw_dt = data["trigger"].get("doubleTapMs")
    double_tap_ms: Optional[int] = None
    if raw_dt is not None:
        double_tap_ms = _parse_positive_ms(
            raw_dt, f"mappings[{mapping_id}].doubleTapMs"
        )
        if trigger.tap != "double":
            raise ConfigError(
                f"mappings[{mapping_id}].doubleTapMs is only valid when trigger.tap is 'double'"
            )
    return Mapping(
        id=mapping_id,
        trigger=trigger,
        action=_parse_action(data["action"], mapping_id),
        double_tap_ms=double_tap_ms,
    )


def parse_config_data(raw: Any) -> AppConfig:
    """Parse and validate an in-memory config object."""
    data = _require_dict(raw, "root")
    version = int(data.get("version", 1))
    if version != 1:
        raise ConfigError(f"Unsupported config version: {version}")
    mappings_raw = data.get("mappings")
    if not isinstance(mappings_raw, list):
        raise ConfigError("'mappings' must be an array")
    mappings = tuple(_parse_mapping(item, i) for i, item in enumerate(mappings_raw))
    seen: Dict[Tuple[FrozenSet[str], int, str], str] = {}
    for m in mappings:
        sig = (m.trigger.modifiers, m.trigger.key_vk, m.trigger.tap)
        if sig in seen:
            raise ConfigError(
                f"Duplicate trigger for {m.id!r} and {seen[sig]!r}: "
                f"mods={sorted(m.trigger.modifiers)} key={m.trigger.key} tap={m.trigger.tap}"
            )
        seen[sig] = m.id
    return AppConfig(
        version=version,
        settings=_parse_settings(data.get("settings")),
        mappings=mappings,
    )


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    return parse_config_data(raw)


def mapping_to_dict(mapping: Mapping) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "id": mapping.id,
        "trigger": {
            "key": mapping.trigger.key,
            "tap": mapping.trigger.tap,
        },
        "action": {
            "type": mapping.action.type,
        },
    }
    if mapping.trigger.modifiers:
        item["trigger"]["modifiers"] = sorted(mapping.trigger.modifiers)
    if mapping.double_tap_ms is not None:
        item["doubleTapMs"] = mapping.double_tap_ms
    if mapping.action.type == "keys":
        item["action"]["sequence"] = list(mapping.action.sequence)
    return item


def config_to_dict(config: AppConfig) -> Dict[str, Any]:
    return {
        "version": config.version,
        "settings": {
            "doubleTapMs": config.settings.double_tap_ms,
            "sequenceDelayMs": config.settings.sequence_delay_ms,
        },
        "mappings": [mapping_to_dict(m) for m in config.mappings],
    }


def save_config(path: str | Path, config: AppConfig) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(config_to_dict(config), ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def save_config_data(path: str | Path, data: Dict[str, Any]) -> AppConfig:
    """Validate dict, save to disk, return parsed config."""
    config = parse_config_data(data)
    save_config(path, config)
    return config


def find_mapping(
    config: AppConfig,
    modifiers: FrozenSet[str],
    key_vk: int,
    tap: str,
) -> Optional[Mapping]:
    for m in config.mappings:
        t = m.trigger
        if t.key_vk == key_vk and t.modifiers == modifiers and t.tap == tap:
            return m
    return None


def has_double_mapping(config: AppConfig, modifiers: FrozenSet[str], key_vk: int) -> bool:
    return find_mapping(config, modifiers, key_vk, "double") is not None


def effective_double_tap_ms(config: AppConfig, mapping: Mapping) -> int:
    """Per-mapping doubleTapMs, falling back to settings.doubleTapMs."""
    if mapping.double_tap_ms is not None:
        return mapping.double_tap_ms
    return config.settings.double_tap_ms
