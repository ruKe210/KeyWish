"""Start/stop facade for the global keyboard hook."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from .config import AppConfig, Mapping
from .engine import MappingEngine
from .hook import LowLevelKeyboardHook

logger = logging.getLogger("keymap.service")

MatchCallback = Callable[[Mapping, str], None]


class KeyWishService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._hook: Optional[LowLevelKeyboardHook] = None
        self._engine: Optional[MappingEngine] = None
        self._running = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(
        self,
        config: AppConfig,
        *,
        on_match: Optional[MatchCallback] = None,
    ) -> None:
        with self._lock:
            if self._running:
                self._stop_unlocked()
            if not config.mappings:
                raise RuntimeError("没有可启用的映射，请先添加至少一条规则")

            engine = MappingEngine(config, on_match=on_match)
            hook = LowLevelKeyboardHook(engine.handle_event)
            try:
                hook.start()
            except RuntimeError:
                engine.shutdown()
                raise
            self._engine = engine
            self._hook = hook
            self._running = True
            logger.info("KeyWish enabled (%d mapping(s))", len(config.mappings))

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        if self._hook is not None:
            try:
                self._hook.stop()
            except Exception:
                logger.exception("Hook stop failed")
            self._hook = None
        if self._engine is not None:
            try:
                self._engine.shutdown()
            except Exception:
                logger.exception("Engine shutdown failed")
            self._engine = None
        if self._running:
            logger.info("KeyWish disabled")
        self._running = False
