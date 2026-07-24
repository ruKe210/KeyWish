"""KeyWish: Windows system-wide keyboard remapping engine."""

from .config import AppConfig, ConfigError, load_config, save_config
from .engine import MappingEngine
from .hook import LowLevelKeyboardHook
from .service import KeyWishService

__all__ = [
    "AppConfig",
    "ConfigError",
    "MappingEngine",
    "LowLevelKeyboardHook",
    "KeyWishService",
    "load_config",
    "save_config",
]

__version__ = "0.1.0"
