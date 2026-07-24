"""Mapping engine: modifier tracking, single/double tap matching, replay."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, FrozenSet, Optional, Set

from .actions import ActionExecutor, replay_chord
from .config import (
    AppConfig,
    Mapping,
    effective_double_tap_ms,
    find_mapping,
)
from .keys import is_modifier_vk, modifier_name_for_vk, vk_name

logger = logging.getLogger("keymap.engine")


@dataclass
class _Pending:
    key_vk: int
    modifiers: FrozenSet[str]
    timer: threading.Timer


class MappingEngine:
    def __init__(
        self,
        config: AppConfig,
        executor: Optional[ActionExecutor] = None,
        on_match: Optional[Callable[[Mapping, str], None]] = None,
        exit_vk: Optional[int] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ) -> None:
        self.config = config
        self.executor = executor or ActionExecutor(config.settings.sequence_delay_ms)
        self.on_match = on_match
        self.exit_vk = exit_vk
        self.on_exit = on_exit

        self._mods_down: Set[str] = set()
        self._lock = threading.RLock()
        self._pending: Optional[_Pending] = None
        # Swallow matching key-up after we consumed a key-down
        self._suppress_ups: Set[int] = set()

    def current_modifiers(self) -> FrozenSet[str]:
        with self._lock:
            return frozenset(self._mods_down)

    def handle_event(self, vk: int, is_down: bool, injected: bool, time_ms: int) -> bool:
        """
        Process a low-level keyboard event.
        Returns True to swallow the event.
        """
        del time_ms  # reserved for future use

        if injected:
            return False

        # Exit key (e.g. Pause) — only on key down, no modifiers required
        if self.exit_vk is not None and vk == self.exit_vk and is_down:
            logger.info("Exit key pressed (%s)", vk_name(vk))
            if self.on_exit:
                threading.Thread(target=self.on_exit, name="keymap-exit", daemon=True).start()
            return True

        # Track modifiers
        if is_modifier_vk(vk):
            name = modifier_name_for_vk(vk)
            if name:
                with self._lock:
                    if is_down:
                        self._mods_down.add(name)
                    else:
                        self._mods_down.discard(name)
            return False

        if is_down:
            return self._on_key_down(vk)
        return self._on_key_up(vk)

    def _on_key_up(self, vk: int) -> bool:
        with self._lock:
            if vk in self._suppress_ups:
                self._suppress_ups.discard(vk)
                return True
            # If this key is still pending double-tap, swallow the up
            if self._pending is not None and self._pending.key_vk == vk:
                return True
        return False

    def _on_key_down(self, vk: int) -> bool:
        with self._lock:
            mods = frozenset(self._mods_down)

            # Second tap of a pending double?
            if self._pending is not None:
                pending = self._pending
                if pending.key_vk == vk and pending.modifiers == mods:
                    self._cancel_pending_locked()
                    mapping = find_mapping(self.config, mods, vk, "double")
                    if mapping is not None:
                        self._suppress_ups.add(vk)
                        self._fire(mapping, "double")
                        return True
                    # No double mapping somehow — fall through
                else:
                    # Different key/mod combo: resolve pending first, then process new key
                    self._resolve_pending_as_single_locked()

            if has_double_mapping(self.config, mods, vk):
                # Start pending window; swallow this down
                self._suppress_ups.add(vk)
                timer = threading.Timer(
                    self.config.settings.double_tap_ms / 1000.0,
                    self._on_pending_timeout,
                    args=(vk, mods),
                )
                timer.daemon = True
                self._pending = _Pending(key_vk=vk, modifiers=mods, timer=timer)
                timer.start()
                logger.debug(
                    "Pending double-tap: key=%s mods=%s",
                    vk_name(vk),
                    sorted(mods),
                )
                return True

            mapping = find_mapping(self.config, mods, vk, "single")
            if mapping is not None:
                self._suppress_ups.add(vk)
                self._fire(mapping, "single")
                return True

        return False

    def _on_pending_timeout(self, vk: int, mods: FrozenSet[str]) -> None:
        with self._lock:
            if self._pending is None:
                return
            if self._pending.key_vk != vk or self._pending.modifiers != mods:
                return
            self._pending = None
            self._resolve_single_after_timeout(vk, mods)

    def _resolve_pending_as_single_locked(self) -> None:
        if self._pending is None:
            return
        pending = self._pending
        self._cancel_pending_locked()
        self._resolve_single_after_timeout(pending.key_vk, pending.modifiers)

    def _resolve_single_after_timeout(self, vk: int, mods: FrozenSet[str]) -> None:
        mapping = find_mapping(self.config, mods, vk, "single")
        if mapping is not None:
            self._fire(mapping, "single")
            return

        # No single mapping: passthrough original chord (e.g. Ctrl+C stays copy).
        held_now = frozenset(self._mods_down)
        logger.info(
            "Double-tap timeout, passthrough key=%s mods=%s (held=%s)",
            vk_name(vk),
            sorted(mods),
            sorted(held_now),
        )
        self._suppress_ups.discard(vk)

        def _replay() -> None:
            try:
                # If user still holds the same modifiers, only inject primary key
                # so physical Ctrl+C remains a real copy without releasing Ctrl.
                replay_chord(mods, vk, already_down=held_now)
            except OSError as exc:
                logger.error("Passthrough replay failed: %s", exc)

        threading.Thread(target=_replay, name="keymap-replay", daemon=True).start()

    def _cancel_pending_locked(self) -> None:
        if self._pending is None:
            return
        self._pending.timer.cancel()
        self._pending = None

    def _fire(self, mapping: Mapping, tap: str) -> None:
        logger.info(
            "Match id=%s tap=%s sequence=%s",
            mapping.id,
            tap,
            list(mapping.action.sequence),
        )
        if self.on_match:
            try:
                self.on_match(mapping, tap)
            except Exception:
                logger.exception("on_match callback error")

        parsed = mapping.action.parsed_sequence
        held_now = frozenset(self._mods_down)

        def _run() -> None:
            # Tiny yield so the swallowed key settles before injection
            time.sleep(0.01)
            try:
                # Skip re-pressing modifiers the user is still holding
                # (Ctrl+double-C while Ctrl is down → only send D / C).
                self.executor.execute_sequence(parsed, already_down=held_now)
            except OSError as exc:
                logger.error("Action failed for %s: %s", mapping.id, exc)

        threading.Thread(target=_run, name=f"keymap-action-{mapping.id}", daemon=True).start()

    def shutdown(self) -> None:
        with self._lock:
            self._cancel_pending_locked()
            self._suppress_ups.clear()
            self._mods_down.clear()
