# GameInputTester (Python 版)

针对**自研 Win PC 游戏**的键盘输入测试工具，**Python 3** + tkinter + ctypes 实现，**功能与 C# 版完全对齐**。

> **C# 版**：[lema/](../lema) — .NET 8 + WinForms
> **Python 版**（本目录）：开发期可跨平台，运行时需 Windows

## 功能列表

### ✅ 已实现（功能完整）

| 功能 | 实现方式 |
|---|---|
| **SendInput + 扫描码** | `ctypes` → `user32.SendInput`，强制 `KEYEVENTF_SCANCODE`，扩展键自动处理 |
| **WH_KEYBOARD_LL 录制** | 隐藏窗口 + 钩子线程，Down/Up 事件，物理键名反查为逻辑名 |
| **冷却随机回放** | 加权洗牌 + 跨轮 `lastTrigger` + 0~+N 抖动 + 操作间隔区间随机 |
| **脚本回放** | 按录制顺序 + 区间随机延迟 |
| **多配置** | `configs/*.json` 扫描 + 列表切换 + 启动记忆上次选择 |
| **键位映射编辑对话框** | tkinter Toplevel + Treeview，7 列（Logical/Physical 下拉 / Cooldown / Jitter / AfterMin / AfterMax / Weight） |
| **内置 JSON 编辑器** | tkinter Text 控件 + 格式化 + JSON 校验 + Ctrl+S 保存 |
| **配置列表右键菜单** | 编辑... / 用记事本打开 / 删除 |
| **状态栏** | 实时显示当前配置 / 模式 / 键数 / 轮数 / 冷却策略 |
| **全局热键** | F4 映射 / F5 录制 / F6 回放 / F7 停止 + Ctrl+S 保存 |
| **US 104 键扫描码** | 字母 / 数字 / 符号 / F1-F12 / 方向 / 编辑 / 修饰 / 小键盘 |
| **日志限长** | 5000 行自动裁剪，避免内存爆炸 |
| **零第三方依赖** | 纯标准库（ctypes / tkinter / json / threading） |
| **跨平台静态检查** | macOS / Linux 上 `py_compile` 即可 |
| **CI** | GitHub Actions：ubuntu py_compile + Windows smoke test |

## 快速开始

### macOS / Linux（开发期）

```bash
cd lema_py
python3 -m py_compile game_input_tester.py
# ✓ 静态检查通过
```

### Windows（运行）

```bash
# 1. 装 Python 3.9+（推荐 3.11）
# 2. 跑
python game_input_tester.py
```

### Windows（打包成 exe）

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=appicon.ico --name GameInputTester game_input_tester.py
# 产物: dist/GameInputTester.exe (~30 MB)
```

## 使用流程

1. 启动 → 默认 4 个映射 (A/S/D/F)，状态栏显示当前状态
2. 按 **F4** → 弹出 7 列映射编辑对话框（Physical 列下拉选 US 104 键）→ 编辑完点"保存"
3. 把 `samples/*.json` 拷到 `configs/`，左侧"刷新列表" → 双击加载（或右键"编辑..."）
4. 切到游戏窗口（前台）→ 按 **F6** 启动回放
5. 按 **F7** 停止

**全局热键**：`F4` 映射 / `F5` 录制 / `F6` 回放 / `F7` 停止 / `Ctrl+S` 保存

## 与 C# 版对比

| 维度 | C# 版 | Python 版 |
|---|---|---|
| **功能完整度** | ✅ 100% | ✅ 100%（本版） |
| 开发平台 | 任意（推荐 macOS） | 任意（macOS 能 py_compile） |
| 运行平台 | Windows only | **Windows only** |
| 单 exe 大小 | ~70 MB | ~30 MB |
| 启动速度 | 50ms | 300ms（解释启动） |
| 录制功能 | 钩子 | 钩子（相同原理） |
| 内置编辑器 | RichTextBox | tkinter Text |
| 第三方依赖 | 0 | 0 |
| 学习曲线 | 陡 | 平 |
| **UI 精致度** | WinForms（原生） | tkinter（够用但不漂亮） |
| **生态丰富度** | NuGet | pip（无依赖） |

## 文件结构

```
lema_py/
├── game_input_tester.py     ~966 行（核心 + UI + 录制 + 4 个对话框）
├── requirements.txt         零依赖
├── README.md                本文件
├── .gitignore
├── .github/workflows/build.yml  CI: ubuntu py_compile + Windows smoke
└── samples/
    ├── combat_weighted.json   RPG 技能循环（5 键加权）
    ├── menu_navigate.json    菜单导航
    └── README.md             字段说明
```

## 配置文件格式

```json
[
  {
    "logical": "Basic",
    "physical": "q",
    "cooldown_ms": 3000,
    "jitter_ms": 300,
    "after_min_ms": 800,
    "after_max_ms": 1500,
    "weight": 5
  }
]
```

**字段含义**：

| 字段 | 含义 |
|---|---|
| `logical` | 语义化名字（仅用于显示） |
| `physical` | 物理键名（小写），见 `SCANCODE` 字典 |
| `cooldown_ms` | 基础冷却（毫秒） |
| `jitter_ms` | 0~+N 抖动（**只延后不提前**），0=无抖动 |
| `after_min_ms` | 发完后到选下一个键的最小等待 |
| `after_max_ms` | 发完后到选下一个键的最大等待 |
| `weight` | 加权（整数，0=禁用该键） |

## 核心实现要点

### SendInput + 扫描码

```python
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', ctypes.c_ushort),
        ('wScan', ctypes.c_ushort),  # 扫描码
        ('dwFlags', ctypes.c_uint),  # KEYEVENTF_SCANCODE | EXTENDEDKEY
        ...
    ]

def send_scan_code(scan):
    flags = KEYEVENTF_SCANCODE
    if scan >= 0xE000:
        flags |= KEYEVENTF_EXTENDEDKEY  # 扩展键（方向键/右Ctrl等）
    # 发送 down + up
    ...
```

### WH_KEYBOARD_LL 录制

```python
class Recorder:
    def _run(self):
        # 1. 注册窗口类
        # 2. 创建隐藏窗口
        # 3. SetWindowsHookEx(WH_KEYBOARD_LL) 装钩子
        # 4. GetMessageW 消息循环
        # 5. 钩子回调 PostMessageW 把事件派发给窗口
        # 6. 窗口 WndProc 调用 on_event 回调
```

**线程模型**：钩子线程跑消息循环，事件通过 PostMessageW 派发，窗口 WndProc 里调 Python 回调（避免在系统钩子线程上做重活）。

### 全局热键

```python
user32.RegisterHotKey(hwnd, id, 0, VK_F4)  # F4 = 0x73
# 消息循环里收到 WM_HOTKEY → 启动新线程调回调
```

### 冷却回放

```python
while round_n < rounds and not cancel:
    pool = []
    for s in slots:
        pool.extend([s] * s.weight)  # 加权展开
    rng.shuffle(pool)  # Fisher-Yates 洗牌

    for pick in pool:
        ready = last_trigger[pick.physical] + pick.cooldown_ms + jitter
        if now < ready:
            cancel.wait((ready - now) / 1000.0)
        send_key(pick.physical)
        last_trigger[pick.physical] = now
        cancel.wait(after_ms / 1000.0)
```

## CI

`.github/workflows/build.yml` 跑：

1. **Ubuntu 静态检查**：`python3 -m py_compile game_input_tester.py`
2. **Windows smoke test**：验证关键 API 存在（SCANCODE / send_scan_code / CooldownPlayer / register_hotkeys / Recorder / ScriptPlayer / MappingDialog / EditConfigDialog）

## 已知限制

- **只在 Windows 跑**（Win32 API 限制）
- **Python 解释器冷启动 ~300ms**（C# 50ms）
- **tkinter UI 不如 WinForms 精致**（够用但不够好看）
- **无 exe 图标**（PyInstaller 打包时可加 `--icon=appicon.ico`）

## 许可

仅供自研游戏开发测试使用，请勿用于绕过任何第三方游戏的反作弊系统。
