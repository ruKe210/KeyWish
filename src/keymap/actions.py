"""SendInput-based macro sequence executor."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import FrozenSet, Iterable, Sequence, Tuple

from .keys import MODIFIER_PRIMARY_VK

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

# Must match Windows ULONG_PTR (pointer-sized unsigned)
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT(ctypes.Structure):
    """Win32 INPUT — union must include MOUSEINPUT so sizeof is 40 on x64 (else SendInput error 87)."""

    class _INPUT(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT),
    ]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT

MAPVK_VK_TO_VSC = 0

# Extended keys that need KEYEVENTF_EXTENDEDKEY
_EXTENDED_VKS = frozenset(
    {
        0x21,  # pageup
        0x22,  # pagedown
        0x23,  # end
        0x24,  # home
        0x25,  # left
        0x26,  # up
        0x27,  # right
        0x28,  # down
        0x2D,  # insert
        0x2E,  # delete
        0x5B,  # lwin
        0x5C,  # rwin
        0x5D,  # apps
        0xA3,  # rctrl
        0xA5,  # ralt
    }
)

# Preferred send order for modifiers
_MOD_ORDER = ("ctrl", "alt", "shift", "win")


def _flags_for(vk: int, key_up: bool) -> int:
    flags = 0
    if key_up:
        flags |= KEYEVENTF_KEYUP
    if vk in _EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    return flags


def _make_key_input(vk: int, key_up: bool = False) -> INPUT:
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) & 0xFF
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(
        wVk=vk & 0xFFFF,
        wScan=scan & 0xFFFF,
        dwFlags=_flags_for(vk, key_up),
        time=0,
        dwExtraInfo=0,
    )
    return inp


def send_key_events(events: Sequence[Tuple[int, bool]]) -> None:
    """Send a batch of (vk, key_up) events via SendInput."""
    if not events:
        return
    n = len(events)
    arr = (INPUT * n)()
    for i, (vk, up) in enumerate(events):
        arr[i] = _make_key_input(vk, up)
    cb = ctypes.sizeof(INPUT)
    # Expected: 28 on x86, 40 on x64
    sent = user32.SendInput(n, arr, cb)
    if sent != n:
        err = ctypes.get_last_error()
        raise OSError(
            f"SendInput failed: sent {sent}/{n}, error={err}, sizeof(INPUT)={cb}"
        )


def send_combo(
    modifiers: Iterable[str],
    key_vk: int,
    already_down: Iterable[str] | None = None,
) -> None:
    """
    Send a chord. Modifiers listed in already_down are assumed physically held
    and will NOT be pressed/released (avoids breaking real Ctrl+C while waiting
    for a possible double-tap).
    """
    wanted = set(modifiers)
    held = set(already_down or ())
    mods = [m for m in _MOD_ORDER if m in wanted]
    to_press = [m for m in mods if m not in held]
    events: list[Tuple[int, bool]] = []
    for m in to_press:
        events.append((MODIFIER_PRIMARY_VK[m], False))
    events.append((key_vk, False))
    events.append((key_vk, True))
    for m in reversed(to_press):
        events.append((MODIFIER_PRIMARY_VK[m], True))
    send_key_events(events)


def send_raw_key(vk: int, key_up: bool) -> None:
    send_key_events([(vk, key_up)])


def replay_tap(vk: int) -> None:
    """Replay a simple key down+up (no modifiers)."""
    send_key_events([(vk, False), (vk, True)])


def replay_chord(
    modifiers: Iterable[str],
    key_vk: int,
    already_down: Iterable[str] | None = None,
) -> None:
    """Replay the original chord after a failed double-tap wait."""
    mods = frozenset(modifiers)
    if not mods:
        replay_tap(key_vk)
        return
    send_combo(mods, key_vk, already_down=already_down)


class ActionExecutor:
    def __init__(self, sequence_delay_ms: int = 30) -> None:
        self.sequence_delay_ms = sequence_delay_ms

    def execute_sequence(
        self,
        parsed_sequence: Sequence[Tuple[FrozenSet[str], int]],
        already_down: Iterable[str] | None = None,
    ) -> None:
        delay = self.sequence_delay_ms / 1000.0
        held = frozenset(already_down or ())
        for i, (mods, vk) in enumerate(parsed_sequence):
            send_combo(mods, vk, already_down=held)
            if i < len(parsed_sequence) - 1 and delay > 0:
                time.sleep(delay)
