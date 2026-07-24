"""Key name <-> virtual-key code helpers for Windows."""

from __future__ import annotations

from typing import FrozenSet, Iterable, List, Set, Tuple

# Virtual-key codes (subset commonly used for remapping)
VK: dict[str, int] = {
    # Letters
    **{chr(ord("a") + i): 0x41 + i for i in range(26)},
    # Digits
    **{str(i): 0x30 + i for i in range(10)},
    # Function keys
    **{f"f{i}": 0x70 + (i - 1) for i in range(1, 13)},
    # Navigation / editing
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    # Punctuation (US layout VK)
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
    # Misc
    "pause": 0x13,
    "capslock": 0x14,
    "printscreen": 0x2C,
    "scrolllock": 0x91,
    "numlock": 0x90,
    "apps": 0x5D,
    "menu": 0x5D,
}

MODIFIER_VK: dict[str, Tuple[int, ...]] = {
    "ctrl": (0x11, 0xA2, 0xA3),  # VK_CONTROL, L/R
    "alt": (0x12, 0xA4, 0xA5),
    "shift": (0x10, 0xA0, 0xA1),
    "win": (0x5B, 0x5C),  # LWIN / RWIN
}

MODIFIER_PRIMARY_VK: dict[str, int] = {
    "ctrl": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
}

VK_TO_MODIFIER: dict[int, str] = {}
for _name, _vks in MODIFIER_VK.items():
    for _vk in _vks:
        VK_TO_MODIFIER[_vk] = _name

VALID_MODIFIERS = frozenset(MODIFIER_VK.keys())

# Reverse lookup for logging
VK_TO_NAME: dict[int, str] = {}
for _name, _vk in VK.items():
    VK_TO_NAME.setdefault(_vk, _name)
for _name, _vk in MODIFIER_PRIMARY_VK.items():
    VK_TO_NAME.setdefault(_vk, _name)


class KeyError_(ValueError):
    """Raised when a key name cannot be resolved."""


def normalize_key_name(name: str) -> str:
    return name.strip().lower()


def resolve_vk(name: str) -> int:
    key = normalize_key_name(name)
    if key in MODIFIER_PRIMARY_VK:
        return MODIFIER_PRIMARY_VK[key]
    if key not in VK:
        raise KeyError_(f"Unknown key name: {name!r}")
    return VK[key]


def vk_name(vk: int) -> str:
    return VK_TO_NAME.get(vk, f"vk_0x{vk:02X}")


def is_modifier_vk(vk: int) -> bool:
    return vk in VK_TO_MODIFIER


def modifier_name_for_vk(vk: int) -> str | None:
    return VK_TO_MODIFIER.get(vk)


def normalize_modifiers(mods: Iterable[str] | None) -> FrozenSet[str]:
    if not mods:
        return frozenset()
    out: Set[str] = set()
    for m in mods:
        name = normalize_key_name(m)
        if name not in VALID_MODIFIERS:
            raise KeyError_(f"Unknown modifier: {m!r} (expected ctrl/alt/shift/win)")
        out.add(name)
    return frozenset(out)


def parse_combo(combo: str) -> Tuple[FrozenSet[str], int]:
    """Parse 'ctrl+shift+s' or 'f1' into (modifiers, primary_vk)."""
    parts = [normalize_key_name(p) for p in combo.split("+") if p.strip()]
    if not parts:
        raise KeyError_(f"Empty key combo: {combo!r}")
    mods: List[str] = []
    primary: str | None = None
    for part in parts:
        if part in VALID_MODIFIERS:
            mods.append(part)
        else:
            if primary is not None:
                raise KeyError_(f"Multiple primary keys in combo: {combo!r}")
            primary = part
    if primary is None:
        # Allow bare modifier like "ctrl" as primary
        if len(mods) == 1:
            return frozenset(), MODIFIER_PRIMARY_VK[mods[0]]
        raise KeyError_(f"No primary key in combo: {combo!r}")
    return normalize_modifiers(mods), resolve_vk(primary)
