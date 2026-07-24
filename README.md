# KeyWish

Windows 系统级键盘映射核心库（第一版）：通过 JSON 配置单击 / 组合键 / 双击 / 修饰键+双击，并附带可运行 demo。

## 环境

使用本机 Miniconda `base` 环境（Python 3.10+）：

```bash
cd D:\double\KeyWish
conda activate base
python demo.py --config config/example_mappings.json
```

核心仅依赖 Python 标准库（`ctypes` / `json` / `threading`），无需额外 pip 包。

按 `Pause` 退出 demo；也可在控制台按 `Ctrl+C`。部分环境可能需要**管理员权限**才能安装全局键盘钩子。

## JSON 配置

见 [`config/example_mappings.json`](config/example_mappings.json)。

| 字段 | 说明 |
|------|------|
| `trigger.key` | 主键，如 `c` / `f1` |
| `trigger.modifiers` | 可选：`ctrl` / `alt` / `shift` / `win`（**严格匹配**集合） |
| `trigger.tap` | `single` 或 `double` |
| `doubleTapMs` | **可选，写在单条 mapping 上**：该条双击判定窗口（毫秒）；不写则用全局默认 |
| `action.sequence` | 宏序列，如 `["ctrl+d", "ctrl+c"]` |
| `settings.doubleTapMs` | 全局默认双击判定窗口（毫秒） |
| `settings.sequenceDelayMs` | 宏序列项间隔（毫秒） |

每条映射可单独设置双击时间，例如：

```json
{
  "id": "ctrl-double-c",
  "doubleTapMs": 350,
  "trigger": { "key": "c", "modifiers": ["ctrl"], "tap": "double" },
  "action": { "type": "keys", "sequence": ["ctrl+d", "ctrl+c"] }
}
```

示例能力：

- `F1` → `Ctrl+C`
- `Ctrl+A` → `Ctrl+Shift+S`
- 双击 `C` → `Ctrl+V`
- `Ctrl` + 双击 `C` → `Ctrl+D` 然后 `Ctrl+C`

## 目录

```
KeyWish/
  demo.py
  config/example_mappings.json
  src/keymap/
    config.py    # JSON 加载与校验
    keys.py      # 键名 ↔ VK
    hook.py      # WH_KEYBOARD_LL
    engine.py    # 匹配与双击状态机
    actions.py   # SendInput 宏执行
```

## 注意

- 注入键（`SendInput`）带 `LLKHF_INJECTED`，不会再次进入映射，避免死循环。
- 存在 `double` 规则的键：第一次按下会被短暂吞掉，超时后执行 `single` 映射或回放原键。
- 杀毒 / 安全软件可能拦截低级键盘钩子。
