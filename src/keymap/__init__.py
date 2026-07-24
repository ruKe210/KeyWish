"""KeyWish: Windows system-wide keyboard remapping engine."""

from .config import AppConfig, ConfigError, load_config
from .engine import MappingEngine
from .hook import LowLevelKeyboardHook

__all__ = [
    "AppConfig",
    "ConfigError",
    "MappingEngine",
    "LowLevelKeyboardHook",
    "load_config",
]

__version__ = "0.1.0"
