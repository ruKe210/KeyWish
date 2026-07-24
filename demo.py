#!/usr/bin/env python3
"""Runnable demo for KeyWish keyboard mapping engine."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from keymap import ConfigError, LowLevelKeyboardHook, MappingEngine, load_config  # noqa: E402
from keymap.keys import resolve_vk  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="KeyWish keyboard mapping demo")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "example_mappings.json"),
        help="Path to mappings JSON",
    )
    parser.add_argument(
        "--exit-key",
        default="pause",
        help="Key that stops the demo (default: pause)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("demo")

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log.error("Config error: %s", exc)
        return 1

    try:
        exit_vk = resolve_vk(args.exit_key)
    except Exception as exc:
        log.error("Invalid --exit-key: %s", exc)
        return 1

    stop_event = threading.Event()

    def on_match(mapping, tap: str) -> None:
        log.info(">> hit %-20s tap=%-6s -> %s", mapping.id, tap, list(mapping.action.sequence))

    def request_stop() -> None:
        stop_event.set()

    engine = MappingEngine(
        config,
        on_match=on_match,
        exit_vk=exit_vk,
        on_exit=request_stop,
    )
    hook = LowLevelKeyboardHook(engine.handle_event)

    log.info("Loaded %d mapping(s) from %s", len(config.mappings), args.config)
    for m in config.mappings:
        mods = "+".join(sorted(m.trigger.modifiers)) or "(none)"
        log.info(
            "  - %-18s mods=%-12s key=%-8s tap=%s -> %s",
            m.id,
            mods,
            m.trigger.key,
            m.trigger.tap,
            list(m.action.sequence),
        )
    log.info(
        "Settings: doubleTapMs=%s sequenceDelayMs=%s",
        config.settings.double_tap_ms,
        config.settings.sequence_delay_ms,
    )
    log.info("Hook starting. Press %s to quit (or Ctrl+C in this console).", args.exit_key)

    try:
        hook.start()
    except RuntimeError as exc:
        log.error("%s", exc)
        log.error("Tip: try running the console as Administrator.")
        return 1

    try:
        while not stop_event.wait(0.2):
            pass
    except KeyboardInterrupt:
        log.info("Interrupted.")
    finally:
        hook.stop()
        engine.shutdown()
        log.info("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
