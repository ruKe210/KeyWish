"""Windows low-level keyboard hook (WH_KEYBOARD_LL)."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10
LLKHF_ALTDOWN = 0x20
LLKHF_UP = 0x80

HC_ACTION = 0

LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = LRESULT
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# Handler: (vk, is_down, injected, time_ms) -> True to swallow
KeyHandler = Callable[[int, bool, bool, int], bool]


class LowLevelKeyboardHook:
    """Install a WH_KEYBOARD_LL hook on a dedicated thread with a message pump."""

    def __init__(self, handler: KeyHandler) -> None:
        self._handler = handler
        self._hook: Optional[wintypes.HHOOK] = None
        self._proc: Optional[HOOKPROC] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._ready = threading.Event()
        self._error: Optional[BaseException] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="keymap-hook", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("Keyboard hook failed to start (timeout)")
        if self._error is not None:
            raise RuntimeError(f"Keyboard hook failed to start: {self._error}") from self._error

    def stop(self) -> None:
        if not self._running:
            return
        tid = self._thread_id
        if tid is not None:
            user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._running = False

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._proc = HOOKPROC(self._callback)
        # For WH_KEYBOARD_LL, hMod can be NULL on modern Windows when hook is in-process
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            self._error = OSError(f"SetWindowsHookExW failed, error={ctypes.get_last_error()}")
            self._ready.set()
            return
        self._running = True
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._running = False

    def _callback(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode == HC_ACTION and lParam:
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = int(info.vkCode)
            injected = bool(info.flags & LLKHF_INJECTED)
            is_up = bool(info.flags & LLKHF_UP) or wParam in (WM_KEYUP, WM_SYSKEYUP)
            is_down = not is_up
            try:
                swallow = self._handler(vk, is_down, injected, int(info.time))
            except Exception:
                # Never break the hook chain on handler errors
                swallow = False
            if swallow:
                return 1
        return int(user32.CallNextHookEx(self._hook, nCode, wParam, lParam))
