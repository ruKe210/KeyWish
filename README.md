# KeyWish

Windows 系统级键盘映射与宏工具。用一份 JSON 配置，把「按下某个键 / 组合键 / 双击 / 修饰键+双击」转成你想要的按键序列，在任意应用中全局生效。

## 这个工具是做什么的

日常里很多快捷键只有「单击」一种语义，例如 `Ctrl+C` 是复制。KeyWish 在此之上增加一层可配置的按键语义，典型用途包括：

- **一键变组合键**：例如按 `F1` 实际发出 `Ctrl+C`
- **组合键重映射**：例如把 `Ctrl+A` 改成 `Ctrl+Shift+S`
- **双击手势**：例如双击某个键触发粘贴或其它宏
- **修饰键 + 双击**：例如按住 `Ctrl` 再双击 `C`，依次发出 `Ctrl+D`、`Ctrl+C`（先删行再复制等自定义流程），而**单击 `Ctrl+C` 仍然保持原来的复制**
- **宏序列**：一次触发连续输出多个组合键，项与项之间可设间隔

简单说：它让你用「双击」「组合 + 双击」等更丰富的手势，扩展键盘能力，又不牺牲原有单击快捷键的习惯。

规则全部写在 JSON 里，改配置、重启 demo 即可调整，无需改代码。

## 环境与运行

使用本机 Miniconda `base` 环境（Python 3.10+）：

```bash
cd D:\double\KeyWish
conda activate base
```

### 图形界面（推荐）

```bash
python gui.py
```

界面支持：

- **一键启用 / 关闭** 全局键盘映射
- **映射列表一行一条**：显示触发方式与宏，启用后标记【生效中】
- **保存到 JSON**：写入当前配置文件
- **导入 JSON…**：
  - **增量合并**：把导入规则追加进当前 JSON（保留原规则）
  - **全部替换**：用导入内容覆盖当前 JSON（路径不变）
- **添加 / 编辑 / 删除 / 复制** 映射规则
- 启用时自动保存；保存后若正在启用会热重载

也可以启动时直接指定配置文件：

```bash
python gui.py D:\path\to\my_mappings.json
```

### 命令行 demo

```bash
python demo.py --config config/example_mappings.json
```

核心仅依赖 Python 标准库（`ctypes` / `json` / `threading` / `tkinter`）。  
部分环境可能需要**管理员权限**才能安装全局键盘钩子。

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
- `Ctrl` + 双击 `C` → `Ctrl+D` 然后 `Ctrl+C`（单击 `Ctrl+C` 仍为复制）

## 目录

```
KeyWish/
  gui.py                         # 图形界面（推荐）
  demo.py                        # 命令行 demo
  config/example_mappings.json
  src/keymap/
    config.py    # JSON 加载 / 保存 / 校验
    service.py   # 一键启停
    keys.py      # 键名 ↔ VK
    hook.py      # WH_KEYBOARD_LL
    engine.py    # 匹配与双击状态机
    actions.py   # SendInput 宏执行
```

## 注意

- 注入键（`SendInput`）带 `LLKHF_INJECTED`，不会再次进入映射，避免死循环。
- 存在 `double` 规则的键：第一次按下会被短暂吞掉，超时后执行 `single` 映射或回放原组合（保证单击 `Ctrl+C` 等行为不丢）。
- 杀毒 / 安全软件可能拦截低级键盘钩子。
