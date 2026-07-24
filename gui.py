#!/usr/bin/env python3
"""KeyWish graphical UI: edit mappings/macros and one-click enable/disable."""

from __future__ import annotations

import copy
import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

def _app_dir() -> Path:
    """Directory for user-writable files (next to exe when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    """Read-only resources bundled inside the exe."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


ROOT = _app_dir()
SRC = Path(__file__).resolve().parent / "src" if not getattr(sys, "frozen", False) else ROOT
if not getattr(sys, "frozen", False) and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from keymap import ConfigError  # noqa: E402
from keymap.config import parse_config_data, save_config_data  # noqa: E402
from keymap.service import KeyWishService  # noqa: E402

DEFAULT_CONFIG = ROOT / "config" / "mappings.json"
_BUNDLED_EXAMPLE = _bundle_dir() / "config" / "example_mappings.json"


def ensure_default_config() -> Path:
    """Ensure a writable config exists beside the app; seed from bundled example."""
    DEFAULT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_CONFIG.is_file():
        if _BUNDLED_EXAMPLE.is_file():
            DEFAULT_CONFIG.write_text(
                _BUNDLED_EXAMPLE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            # Fallback minimal config
            DEFAULT_CONFIG.write_text(
                '{\n  "version": 1,\n  "settings": {"doubleTapMs": 280, "sequenceDelayMs": 30},\n'
                '  "mappings": []\n}\n',
                encoding="utf-8",
            )
    return DEFAULT_CONFIG


def _format_trigger(trigger: Dict[str, Any]) -> str:
    mods = list(trigger.get("modifiers") or [])
    key = str(trigger.get("key") or "?")
    tap = str(trigger.get("tap") or "single")
    mod_s = "+".join(m.upper() if m != "win" else "Win" for m in mods)
    key_s = key.upper() if len(key) == 1 else key
    chord = f"{mod_s}+{key_s}" if mod_s else key_s
    tap_s = "双击" if tap == "double" else "单击"
    return f"{chord}（{tap_s}）"


def _format_macro(action: Dict[str, Any]) -> str:
    if action.get("type") == "keys":
        return " → ".join(action.get("sequence") or [])
    return str(action.get("type") or "")


def _format_mapping_line(index: int, mapping: Dict[str, Any], *, enabled: bool) -> str:
    """One human-readable line per mapping."""
    status = "【生效中】" if enabled else "【未启用】"
    mid = mapping.get("id") or f"mapping-{index}"
    trigger = _format_trigger(mapping.get("trigger") or {})
    macro = _format_macro(mapping.get("action") or {})
    dt = mapping.get("doubleTapMs")
    dt_s = f"  双击判定={dt}ms" if dt is not None else ""
    return f"{status}  #{index + 1}  {mid}  |  {trigger}  =>  {macro}{dt_s}"


class MappingDialog(tk.Toplevel):
    """Add / edit a single mapping rule."""

    def __init__(self, master: tk.Misc, title: str, initial: Optional[Dict[str, Any]] = None):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: Optional[Dict[str, Any]] = None

        initial = initial or {}
        trigger = initial.get("trigger") or {}
        action = initial.get("action") or {"type": "keys", "sequence": []}
        mods = set(trigger.get("modifiers") or [])

        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        self.var_id = tk.StringVar(value=str(initial.get("id") or ""))
        self.var_key = tk.StringVar(value=str(trigger.get("key") or ""))
        self.var_tap = tk.StringVar(value=str(trigger.get("tap") or "double"))
        self.var_dt = tk.StringVar(
            value="" if initial.get("doubleTapMs") is None else str(initial.get("doubleTapMs"))
        )
        seq = action.get("sequence") or []
        self.var_seq = tk.StringVar(value=", ".join(seq) if isinstance(seq, list) else "")

        self.var_ctrl = tk.BooleanVar(value="ctrl" in mods)
        self.var_alt = tk.BooleanVar(value="alt" in mods)
        self.var_shift = tk.BooleanVar(value="shift" in mods)
        self.var_win = tk.BooleanVar(value="win" in mods)

        rows = [
            ("规则 ID", self.var_id),
            ("触发主键 (如 c / f1)", self.var_key),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(frm, textvariable=var, width=36).grid(row=i, column=1, sticky="ew", pady=4)

        ttk.Label(frm, text="修饰键").grid(row=2, column=0, sticky="w", pady=4)
        mod_fr = ttk.Frame(frm)
        mod_fr.grid(row=2, column=1, sticky="w")
        for text, var in (
            ("Ctrl", self.var_ctrl),
            ("Alt", self.var_alt),
            ("Shift", self.var_shift),
            ("Win", self.var_win),
        ):
            ttk.Checkbutton(mod_fr, text=text, variable=var).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(frm, text="触发方式").grid(row=3, column=0, sticky="w", pady=4)
        tap_fr = ttk.Frame(frm)
        tap_fr.grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(tap_fr, text="单击", value="single", variable=self.var_tap).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Radiobutton(tap_fr, text="双击", value="double", variable=self.var_tap).pack(
            side=tk.LEFT
        )

        ttk.Label(frm, text="双击判定(ms，可空)").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.var_dt, width=12).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(frm, text="宏序列").grid(row=5, column=0, sticky="nw", pady=4)
        seq_fr = ttk.Frame(frm)
        seq_fr.grid(row=5, column=1, sticky="ew", pady=4)
        ttk.Entry(seq_fr, textvariable=self.var_seq, width=36).pack(anchor="w")
        ttk.Label(
            seq_fr,
            text="多项用逗号分隔，如：ctrl+d, ctrl+c",
            foreground="#666",
        ).pack(anchor="w", pady=(2, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btns, text="确定", command=self._ok).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_visibility()
        self.focus()

    def _ok(self) -> None:
        mid = self.var_id.get().strip() or "mapping"
        key = self.var_key.get().strip()
        if not key:
            messagebox.showerror("错误", "请填写触发主键", parent=self)
            return
        mods = []
        if self.var_ctrl.get():
            mods.append("ctrl")
        if self.var_alt.get():
            mods.append("alt")
        if self.var_shift.get():
            mods.append("shift")
        if self.var_win.get():
            mods.append("win")
        seq_raw = self.var_seq.get().strip()
        if not seq_raw:
            messagebox.showerror("错误", "请填写宏序列", parent=self)
            return
        sequence = [p.strip() for p in seq_raw.replace(";", ",").split(",") if p.strip()]
        item: Dict[str, Any] = {
            "id": mid,
            "trigger": {"key": key, "tap": self.var_tap.get(), "modifiers": mods},
            "action": {"type": "keys", "sequence": sequence},
        }
        dt = self.var_dt.get().strip()
        if dt:
            try:
                item["doubleTapMs"] = int(dt)
            except ValueError:
                messagebox.showerror("错误", "双击判定必须是整数毫秒", parent=self)
                return
        try:
            parse_config_data(
                {
                    "version": 1,
                    "settings": {"doubleTapMs": 280, "sequenceDelayMs": 30},
                    "mappings": [item],
                }
            )
        except ConfigError as exc:
            messagebox.showerror("配置无效", str(exc), parent=self)
            return
        self.result = item
        self.destroy()


class ImportModeDialog(tk.Toplevel):
    """Choose incremental merge vs replace for JSON import."""

    def __init__(self, master: tk.Misc, src_name: str, count: int):
        super().__init__(master)
        self.title("选择导入方式")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: Optional[str] = None  # "merge" | "replace"

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frm,
            text=f"即将导入：{src_name}\n共 {count} 条映射规则\n\n请选择如何写入当前配置 JSON：",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 12))

        ttk.Button(
            frm,
            text="增量合并（追加到当前 JSON，保留原有规则）",
            command=lambda: self._choose("merge"),
        ).pack(fill=tk.X, pady=4)
        ttk.Button(
            frm,
            text="全部替换（用导入内容覆盖当前 JSON）",
            command=lambda: self._choose("replace"),
        ).pack(fill=tk.X, pady=4)
        ttk.Button(frm, text="取消", command=self.destroy).pack(fill=tk.X, pady=(12, 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_visibility()
        self.focus()

    def _choose(self, mode: str) -> None:
        self.result = mode
        self.destroy()


class KeyWishApp(tk.Tk):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.title("KeyWish - 键盘映射 / 宏")
        self.geometry("980x680")
        self.minsize(820, 560)

        self.config_path = config_path
        self.service = KeyWishService()
        self.data: Dict[str, Any] = {
            "version": 1,
            "settings": {"doubleTapMs": 280, "sequenceDelayMs": 30},
            "mappings": [],
        }
        self._dirty = False

        self._build_ui()
        self._load_file(config_path, quiet=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_status(False)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        self.btn_toggle = ttk.Button(top, text="启用", command=self._toggle, width=12)
        self.btn_toggle.pack(side=tk.LEFT)

        self.lbl_status = ttk.Label(
            top, text="状态：已关闭", font=("Microsoft YaHei UI", 11, "bold")
        )
        self.lbl_status.pack(side=tk.LEFT, padx=12)

        ttk.Button(top, text="保存到 JSON", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(top, text="另存为…", command=self._save_as).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(top, text="导入 JSON…", command=self._import_json).pack(
            side=tk.RIGHT, padx=(0, 6)
        )

        path_fr = ttk.Frame(self, padding=(10, 0))
        path_fr.pack(fill=tk.X)
        self.lbl_path = ttk.Label(path_fr, text="", foreground="#555")
        self.lbl_path.pack(anchor="w")

        settings = ttk.LabelFrame(self, text="全局设置", padding=10)
        settings.pack(fill=tk.X, padx=10, pady=8)
        self.var_global_dt = tk.StringVar(value="280")
        self.var_seq_delay = tk.StringVar(value="30")
        ttk.Label(settings, text="默认双击判定 (ms)").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.var_global_dt, width=10).grid(
            row=0, column=1, sticky="w", padx=(6, 20)
        )
        ttk.Label(settings, text="宏序列间隔 (ms)").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.var_seq_delay, width=10).grid(
            row=0, column=3, sticky="w", padx=(6, 0)
        )

        mid = ttk.LabelFrame(self, text="当前映射列表（一行一条）", padding=10)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        btn_row = ttk.Frame(mid)
        btn_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(btn_row, text="添加", command=self._add).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="编辑", command=self._edit).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="删除", command=self._delete).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="复制", command=self._duplicate).pack(side=tk.LEFT, padx=6)
        self.lbl_count = ttk.Label(btn_row, text="共 0 条")
        self.lbl_count.pack(side=tk.RIGHT)

        list_fr = ttk.Frame(mid)
        list_fr.pack(fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(list_fr, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(
            list_fr,
            yscrollcommand=scroll.set,
            font=("Consolas", 10),
            activestyle="dotbox",
            selectmode=tk.BROWSE,
            height=14,
        )
        scroll.config(command=self.listbox.yview)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._edit())

        tip = ttk.Label(
            mid,
            text="说明：启用后每行会显示【生效中】；所有改动点「保存到 JSON」写入当前配置文件。",
            foreground="#666",
        )
        tip.pack(anchor="w", pady=(6, 0))

        log_fr = ttk.LabelFrame(self, text="日志", padding=8)
        log_fr.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))
        self.txt_log = tk.Text(log_fr, height=7, wrap=tk.WORD, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        self._update_path_label()

    def _log(self, msg: str) -> None:
        self.txt_log.configure(state=tk.NORMAL)
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state=tk.DISABLED)

    def _update_path_label(self) -> None:
        mark = "（有未保存更改）" if self._dirty else ""
        self.lbl_path.configure(text=f"当前 JSON：{self.config_path}  {mark}")

    def _set_status(self, running: bool) -> None:
        if running:
            self.lbl_status.configure(text="状态：已启用", foreground="#0a7a2f")
            self.btn_toggle.configure(text="关闭")
        else:
            self.lbl_status.configure(text="状态：已关闭", foreground="#a33")
            self.btn_toggle.configure(text="启用")
        self._refresh_list()

    def _mappings(self) -> List[Dict[str, Any]]:
        return list(self.data.get("mappings") or [])

    def _refresh_list(self) -> None:
        enabled = self.service.running
        self.listbox.delete(0, tk.END)
        mappings = self._mappings()
        for i, m in enumerate(mappings):
            line = _format_mapping_line(i, m, enabled=enabled)
            self.listbox.insert(tk.END, line)
            if enabled:
                self.listbox.itemconfig(i, foreground="#0a7a2f")
            else:
                self.listbox.itemconfig(i, foreground="#333")
        self.lbl_count.configure(text=f"共 {len(mappings)} 条")

    def _collect_settings_into_data(self) -> None:
        try:
            dt = int(self.var_global_dt.get().strip())
            sd = int(self.var_seq_delay.get().strip())
        except ValueError as exc:
            raise ConfigError("全局设置必须是整数") from exc
        self.data["version"] = 1
        self.data["settings"] = {"doubleTapMs": dt, "sequenceDelayMs": sd}

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_path_label()

    def _read_json_file(self, path: Path) -> Dict[str, Any]:
        import json

        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ConfigError(f"无法读取文件：{exc}") from exc
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"JSON 格式错误：{exc}") from exc
        parse_config_data(raw)
        return raw

    def _apply_settings_to_ui(self) -> None:
        settings = self.data.get("settings") or {}
        self.var_global_dt.set(str(settings.get("doubleTapMs", 280)))
        self.var_seq_delay.set(str(settings.get("sequenceDelayMs", 30)))

    def _load_file(self, path: Path, quiet: bool = False) -> None:
        try:
            raw = self._read_json_file(path)
            self.data = raw
            self.config_path = path
            self._apply_settings_to_ui()
            self._dirty = False
            self._refresh_list()
            self._update_path_label()
            if not quiet:
                self._log(f"已加载：{path}（{len(self._mappings())} 条）")
                for i, m in enumerate(self._mappings()):
                    self._log("  " + _format_mapping_line(i, m, enabled=False))
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc), parent=self)

    def _build_validated_config(self):
        self._collect_settings_into_data()
        return parse_config_data(self.data)

    def _persist_to_current_json(self) -> int:
        """Validate and write self.data into self.config_path. Returns mapping count."""
        cfg = self._build_validated_config()
        save_config_data(self.config_path, self.data)
        self._dirty = False
        self._update_path_label()
        return len(cfg.mappings)

    def _save(self) -> None:
        try:
            n = self._persist_to_current_json()
            self._log(f"已保存到 JSON：{self.config_path}（{n} 条）")
            for i, m in enumerate(self._mappings()):
                self._log("  " + _format_mapping_line(i, m, enabled=self.service.running))
            if self.service.running:
                cfg = parse_config_data(self.data)
                self.service.start(cfg, on_match=self._on_match)
                self._set_status(True)
                self._log("已热重载，映射保持启用")
            else:
                self._refresh_list()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)

    def _save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="另存为 JSON 配置",
            defaultextension=".json",
            filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")],
            initialdir=str(self.config_path.parent),
            initialfile=self.config_path.name,
        )
        if not path:
            return
        self.config_path = Path(path)
        self._save()

    def _import_json(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="导入玩家自定义 JSON",
            filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")],
            initialdir=str(self.config_path.parent),
        )
        if not path:
            return
        src = Path(path)

        try:
            imported = self._read_json_file(src)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return

        incoming = list(imported.get("mappings") or [])
        dlg = ImportModeDialog(self, src.name, len(incoming))
        self.wait_window(dlg)
        if not dlg.result:
            return
        mode = dlg.result

        was_running = self.service.running
        if was_running:
            self.service.stop()
            self._set_status(False)
            self._log("已暂时关闭映射以便导入")

        original_path = self.config_path  # always write back to current JSON

        try:
            if mode == "replace":
                # Replace content of current JSON file (keep path)
                self.data = copy.deepcopy(imported)
                self._apply_settings_to_ui()
                n = self._persist_to_current_json()
                self._refresh_list()
                self._log(f"已替换写入：{original_path}（来自 {src.name}，{n} 条）")
                for i, m in enumerate(self._mappings()):
                    self._log("  " + _format_mapping_line(i, m, enabled=False))
                messagebox.showinfo(
                    "替换成功",
                    f"已用导入内容覆盖当前 JSON：\n{original_path}\n共 {n} 条规则。",
                    parent=self,
                )
            else:
                # Incremental merge into current JSON
                if not incoming:
                    messagebox.showwarning("导入", "该 JSON 里没有 mappings 规则", parent=self)
                    return
                existing_ids = {str(m.get("id")) for m in self._mappings()}
                added = 0
                renamed = 0
                snapshot = copy.deepcopy(self.data.get("mappings") or [])
                for item in incoming:
                    item = copy.deepcopy(item)
                    mid = str(item.get("id") or f"imported-{added}")
                    if mid in existing_ids:
                        base = mid
                        k = 2
                        while f"{base}-{k}" in existing_ids:
                            k += 1
                        mid = f"{base}-{k}"
                        item["id"] = mid
                        renamed += 1
                    existing_ids.add(mid)
                    item["id"] = mid
                    self.data.setdefault("mappings", []).append(item)
                    added += 1
                try:
                    n = self._persist_to_current_json()
                except ConfigError as exc:
                    self.data["mappings"] = snapshot
                    self._refresh_list()
                    messagebox.showerror(
                        "合并失败",
                        f"增量合并后配置无效（可能触发键冲突）：\n{exc}",
                        parent=self,
                    )
                    return
                self._refresh_list()
                msg = f"已增量合并 {added} 条到 {original_path}（现共 {n} 条）"
                if renamed:
                    msg += f"；{renamed} 条因 ID 冲突已改名"
                self._log(msg)
                for i, m in enumerate(self._mappings()):
                    self._log("  " + _format_mapping_line(i, m, enabled=False))
                messagebox.showinfo("合并成功", msg, parent=self)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return

        if was_running:
            try:
                cfg = parse_config_data(self.data)
                self.service.start(cfg, on_match=self._on_match)
                self._set_status(True)
                self._log("导入完成，已重新启用")
            except Exception as exc:
                messagebox.showerror("重新启用失败", str(exc), parent=self)

    def _selected_index(self) -> Optional[int]:
        sel = self.listbox.curselection()
        if not sel:
            return None
        return int(sel[0])

    def _add(self) -> None:
        dlg = MappingDialog(self, "添加映射")
        self.wait_window(dlg)
        if not dlg.result:
            return
        self.data.setdefault("mappings", []).append(dlg.result)
        self._mark_dirty()
        self._refresh_list()

    def _edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("提示", "请先选择一条规则", parent=self)
            return
        current = copy.deepcopy(self._mappings()[idx])
        dlg = MappingDialog(self, "编辑映射", current)
        self.wait_window(dlg)
        if not dlg.result:
            return
        self.data["mappings"][idx] = dlg.result
        self._mark_dirty()
        self._refresh_list()

    def _delete(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("提示", "请先选择一条规则", parent=self)
            return
        if not messagebox.askyesno("确认", "删除选中的规则？", parent=self):
            return
        self.data["mappings"].pop(idx)
        self._mark_dirty()
        self._refresh_list()

    def _duplicate(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("提示", "请先选择一条规则", parent=self)
            return
        item = copy.deepcopy(self._mappings()[idx])
        item["id"] = str(item.get("id", "mapping")) + "-copy"
        self.data.setdefault("mappings", []).append(item)
        self._mark_dirty()
        self._refresh_list()

    def _on_match(self, mapping, tap: str) -> None:
        seq = list(mapping.action.sequence) if mapping.action.type == "keys" else mapping.action.type
        self.after(0, lambda: self._log(f"命中 {mapping.id} tap={tap} -> {seq}"))

    def _toggle(self) -> None:
        if self.service.running:
            self.service.stop()
            self._set_status(False)
            self._log("已关闭键盘映射")
            return
        try:
            n = self._persist_to_current_json()
            cfg = parse_config_data(self.data)
            self.service.start(cfg, on_match=self._on_match)
            self._set_status(True)
            self._log(f"已启用并保存（{n} 条规则）-> {self.config_path}")
            for i, m in enumerate(self._mappings()):
                self._log("  " + _format_mapping_line(i, m, enabled=True))
        except Exception as exc:
            self._set_status(False)
            messagebox.showerror(
                "启用失败",
                f"{exc}\n\n若提示钩子失败，可尝试以管理员身份运行。",
                parent=self,
            )

    def _on_close(self) -> None:
        if self.service.running:
            if not messagebox.askyesno("退出", "映射仍在启用，确定退出并关闭？", parent=self):
                return
            self.service.stop()
        if self._dirty:
            if messagebox.askyesno("保存", "有未保存的更改，是否保存到 JSON？", parent=self):
                try:
                    self._save()
                except Exception:
                    pass
        self.destroy()


def main() -> int:
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_dir / "keywish.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    if len(sys.argv) > 1:
        config = Path(sys.argv[1])
    else:
        config = ensure_default_config()
    app = KeyWishApp(config)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
