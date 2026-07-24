#!/usr/bin/env python3
"""Offline smoke test (no global hook)."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from keymap import ConfigError, MappingEngine, load_config
from keymap.config import effective_double_tap_ms, save_config
from keymap.keys import resolve_vk


def main() -> int:
    cfg = load_config(ROOT / "config" / "example_mappings.json")
    assert len(cfg.mappings) == 2
    by_id = {m.id: m for m in cfg.mappings}
    assert effective_double_tap_ms(cfg, by_id["ctrl-double-c"]) == 200
    print("config OK")

    # save roundtrip
    tmp = Path(tempfile.gettempdir()) / "keywish_roundtrip.json"
    save_config(tmp, cfg)
    cfg2 = load_config(tmp)
    assert len(cfg2.mappings) == 2
    print("save OK")

    hits: list[tuple[str, str]] = []
    replays: list[tuple] = []
    eng = MappingEngine(cfg, on_match=lambda m, t: hits.append((m.id, t)))
    eng.executor.execute_sequence = lambda seq, already_down=None: None  # type: ignore[method-assign]

    eng._mods_down.add("ctrl")
    assert eng.handle_event(resolve_vk("c"), True, False, 0) is True
    assert eng.handle_event(resolve_vk("c"), False, False, 0) is True
    assert eng.handle_event(resolve_vk("c"), True, False, 0) is True
    time.sleep(0.05)
    assert any(h[0] == "ctrl-double-c" for h in hits), hits
    print("ctrl-double-c OK", hits)

    hits.clear()
    eng2 = MappingEngine(cfg, on_match=lambda m, t: hits.append((m.id, t)))
    eng2.executor.execute_sequence = lambda seq, already_down=None: None  # type: ignore[method-assign]

    import keymap.engine as engine_mod

    original_replay = engine_mod.replay_chord

    def capture_replay(mods, vk, already_down=None):
        replays.append((frozenset(mods), vk, frozenset(already_down or [])))

    engine_mod.replay_chord = capture_replay  # type: ignore[attr-defined]
    try:
        eng2._mods_down.add("ctrl")
        assert eng2.handle_event(resolve_vk("c"), True, False, 0) is True
        assert eng2.handle_event(resolve_vk("c"), False, False, 0) is True
        time.sleep(effective_double_tap_ms(cfg, by_id["ctrl-double-c"]) / 1000.0 + 0.08)
    finally:
        engine_mod.replay_chord = original_replay  # type: ignore[attr-defined]

    assert hits == [], f"single ctrl+c should not match a mapping, got {hits}"
    assert replays, "expected passthrough replay for single ctrl+c"
    print("ctrl-single-c passthrough OK", replays)

    bad = Path(tempfile.gettempdir()) / "keywish_bad.json"
    bad.write_text(
        '{"version":1,"mappings":[{"id":"x","trigger":{"key":"zzz"},'
        '"action":{"type":"keys","sequence":["a"]}}]}',
        encoding="utf-8",
    )
    try:
        load_config(bad)
        raise AssertionError("expected ConfigError")
    except ConfigError as exc:
        print("bad key OK:", exc)

    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
