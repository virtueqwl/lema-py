"""
GameInputTester - Python 版 (完整功能)

针对自研 Win PC 游戏的键盘输入测试工具。
- 开发：macOS / Linux 都能写代码（py_compile 静态检查）
- 运行：Windows only（Win32 SendInput / RegisterHotKey / WH_KEYBOARD_LL）
- 打包：PyInstaller --onefile --windowed
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import random
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path

# ===== Win32 API =====
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# ===== 扫描码表（US 104 键，Set 1） =====
SCANCODE = {
    'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12, 'f': 0x21,
    'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24, 'k': 0x25, 'l': 0x26,
    'm': 0x32, 'n': 0x31, 'o': 0x18, 'p': 0x19, 'q': 0x10, 'r': 0x13,
    's': 0x1F, 't': 0x14, 'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D,
    'y': 0x15, 'z': 0x2C,
    '0': 0x0B, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A,
    '`': 0x29, '-': 0x0C, '=': 0x0D, '[': 0x1A, ']': 0x1B, '\\': 0x2B,
    ';': 0x27, "'": 0x28, ',': 0x33, '.': 0x34, '/': 0x35,
    'shift': 0x2A, 'rshift': 0x36, 'ctrl': 0x1D, 'rctrl': 0xE01D,
    'alt': 0x38, 'ralt': 0xE038,
    'caps': 0x3A, 'num': 0x45, 'scroll': 0x46,
    'space': 0x39, 'enter': 0x1C, 'escape': 0x01, 'tab': 0x0F, 'back': 0x0E,
    'up': 0xE048, 'down': 0xE050, 'left': 0xE04B, 'right': 0xE04D,
    'home': 0xE047, 'end': 0xE04F, 'insert': 0xE052, 'delete': 0xE053,
    'pageup': 0xE049, 'pagedown': 0xE051,
    'f1': 0x3B, 'f2': 0x3C, 'f3': 0x3D, 'f4': 0x3E, 'f5': 0x3F,
    'f6': 0x40, 'f7': 0x41, 'f8': 0x42, 'f9': 0x43, 'f10': 0x44,
    'f11': 0x57, 'f12': 0x58,
    'numpad0': 0x52, 'numpad1': 0x4F, 'numpad2': 0x50, 'numpad3': 0x51,
    'numpad4': 0x4B, 'numpad5': 0x4C, 'numpad6': 0x4D, 'numpad7': 0x47,
    'numpad8': 0x48, 'numpad9': 0x49,
    'multiply': 0x37, 'add': 0x4E, 'subtract': 0x4A,
    'decimal': 0x53, 'divide': 0xE035,
}

# 物理键名 → 逻辑名（用于录制时反查）
PHYSICAL_NAMES = {v: k for k, v in SCANCODE.items()}

# UI 用：所有可用的键（按 SCANCODE 字典顺序）
AVAILABLE_KEYS = sorted(SCANCODE.keys(), key=lambda x: SCANCODE[x])

# ===== INPUT 结构 =====
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', ctypes.c_ushort),
        ('wScan', ctypes.c_ushort),
        ('dwFlags', ctypes.c_uint),
        ('time', ctypes.c_uint),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_uint)),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint), ('u', INPUT_UNION)]

KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP    = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

def send_scan_code(scan: int):
    """发送一个完整的"按下-抬起"事件。"""
    flags = KEYEVENTF_SCANCODE
    if scan >= 0xE000:
        flags |= KEYEVENTF_EXTENDEDKEY
    ki_down = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    ki_up   = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
    user32.SendInput(1, ctypes.byref(INPUT(type=1, u=INPUT_UNION(ki=ki_down))), ctypes.sizeof(INPUT))
    user32.SendInput(1, ctypes.byref(INPUT(type=1, u=INPUT_UNION(ki=ki_up))),   ctypes.sizeof(INPUT))

def send_key(name: str):
    """根据键名发送（小写）。"""
    code = SCANCODE.get(name.lower())
    if code is None:
        raise ValueError(f"未知键: {name}")
    send_scan_code(code)

# ===== 焦点管理 =====
def get_foreground_hwnd() -> int:
    """获取当前前台窗口的 HWND（整数）。"""
    return user32.GetForegroundWindow()

def get_hwnd_title(hwnd: int) -> str:
    """获取窗口标题（调试用）。"""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def focus_window(hwnd: int) -> bool:
    """强制把指定窗口设为前台（用 alt 键 hack 绕过 Windows 限制）。"""
    if not hwnd:
        return False
    # 取消最小化
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # alt 键 hack：让 SetForegroundWindow 真正生效
    user32.keybd_event(0x12, 0x38, 0, 0)  # VK_MENU down
    user32.keybd_event(0x12, 0x38, 2, 0)  # VK_MENU up
    return bool(user32.SetForegroundWindow(hwnd))

# ===== 全局热键 =====
# 注：F4-F7 热键现在通过 Recorder 钩子识别（见 HOTKEY_VK_TO_ACTION），
# 不再用 RegisterHotKey（焦点问题）。register_hotkeys 函数已删除。

# ===== 应用根目录 =====
# 开发期：脚本所在目录
# 打包后（PyInstaller --onefile）：exe 所在目录
def _app_dir() -> Path:
    """返回 exe / 脚本所在的目录（用于 configs/、settings.json 等运行时数据）。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包：sys.executable 是 exe 路径
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

# ===== 录制（WH_KEYBOARD_LL 钩子） =====
# VK code → 我们的物理键名（跟 SCANCODE 的 key 对齐）
VK_TO_NAME = {
    # 字母
    **{i: chr(i).lower() for i in range(ord('A'), ord('Z') + 1)},
    # 数字
    **{i: chr(i - ord('0') + ord('0')) for i in range(0x30, 0x3A)},
    # 功能键
    **{0x70 + i: f'f{i+1}' for i in range(12)},
    # 方向 / 编辑
    0x25: 'left', 0x26: 'up', 0x27: 'right', 0x28: 'down',
    0x24: 'home', 0x23: 'end', 0x2D: 'insert', 0x2E: 'delete',
    0x21: 'pageup', 0x22: 'pagedown',
    # 基础
    0x20: 'space', 0x0D: 'enter', 0x1B: 'escape', 0x09: 'tab', 0x08: 'back',
    # 修饰
    0xA0: 'shift', 0xA1: 'rshift', 0xA2: 'ctrl', 0xA3: 'rctrl',
    0xA4: 'alt', 0xA5: 'ralt',
    0x14: 'caps', 0x90: 'num', 0x91: 'scroll',
    # 小键盘
    **{0x60 + i: f'numpad{i}' for i in range(10)},
    0x6A: 'multiply', 0x6B: 'add', 0x6D: 'subtract', 0x6E: 'decimal', 0x6F: 'divide',
    # 符号
    0xC0: '`', 0xBD: '-', 0xBB: '=', 0xDB: '[', 0xDD: ']', 0xDC: '\\',
    0xBA: ';', 0xDE: "'", 0xBC: ',', 0xBE: '.', 0xBF: '/',
}

# 全局热键 VK → 逻辑动作（被 Recorder 钩子识别）
HOTKEY_VK_TO_ACTION = {
    0x73: 'F4',  # 键位映射
    0x74: 'F5',  # 录制切换
    0x75: 'F6',  # 启动回放
    0x76: 'F7',  # 停止回放
}

class Recorder:
    """WH_KEYBOARD_LL 低层键盘钩子，事件直接回调。"""
    WH_KEYBOARD_LL = 13
    HC_ACTION = 0
    LLKHF_UP = 0x80

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ('vkCode', ctypes.c_uint),
            ('scanCode', ctypes.c_uint),
            ('flags', ctypes.c_uint),
            ('time', ctypes.c_uint),
            ('dwExtraInfo', ctypes.POINTER(ctypes.c_uint)),
        ]

    def __init__(self, on_event):
        self._on_event = on_event
        self._on_hotkey = None  # 形如 lambda hwnd, action: ...（钩子触发时调）
        self._hook_id = None
        self._thread = None
        self._hwnd = None
        self._wndproc_ref = None
        self._hook_proc_ref = None
        self._stop = threading.Event()
        self._start_ms = 0
        self._watch_keys = set()  # 空 = 录所有
        self._logical_name_of = lambda k: k

    def set_hotkey_callback(self, cb):
        """设置热键回调：cb(hwnd, action) — 钩子线程里同步调。"""
        self._on_hotkey = cb

    def set_filter(self, watch_keys: set, logical_name_of):
        self._watch_keys = set(watch_keys) if watch_keys else set()
        if logical_name_of:
            self._logical_name_of = logical_name_of

    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._start_ms = int(time.time() * 1000)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        # 发 WM_QUIT 让 GetMessage 返回 0
        if self._hwnd:
            try:
                user32.PostMessageW(self._hwnd, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None
        if self._hook_id:
            try:
                user32.UnhookWindowsHookEx(self._hook_id)
            except Exception:
                pass
            self._hook_id = None
        if self._hwnd:
            try:
                user32.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None
            try:
                user32.UnregisterClassW("GameInputTesterRecClass", kernel32.GetModuleHandleW(None))
            except Exception:
                pass

    def _run(self):
        """钩子线程：建消息泵窗口 → 装钩子 → 事件直接回调。"""
        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,            # 返回值
            ctypes.c_int,             # nCode
            ctypes.c_uint,            # wParam
            ctypes.c_int              # lParam
        )
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int, ctypes.c_uint, ctypes.c_int, ctypes.c_int
        )

        # 钩子回调：直接在钩子线程调 on_event（on_event 内部要线程安全）
        def hook_proc(nCode, wParam, lParam):
            if nCode == self.HC_ACTION and not self._stop.is_set():
                try:
                    info = ctypes.cast(lParam, ctypes.POINTER(self.KBDLLHOOKSTRUCT))[0]
                    vk = info.vkCode
                    is_down = (info.flags & self.LLKHF_UP) == 0

                    # F4-F7 热键：钩子触发时焦点还没切走，GetForegroundWindow
                    # 拿到的就是真正的"按下热键时的前台窗口"（记事本/游戏）
                    if is_down and self._on_hotkey and vk in HOTKEY_VK_TO_ACTION:
                        try:
                            hwnd = user32.GetForegroundWindow()
                            self._on_hotkey(hwnd, HOTKEY_VK_TO_ACTION[vk])
                        except Exception:
                            pass
                        # 不返回 False：让事件继续传给原目标窗口（让游戏能收到 F4-F7）
                        return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

                    # 录制事件
                    key_name = VK_TO_NAME.get(vk, f'vk{vk:02x}')
                    if not self._watch_keys or key_name in self._watch_keys:
                        try:
                            logical = self._logical_name_of(key_name) or key_name
                            self._on_event(logical, key_name, is_down,
                                           int(time.time() * 1000) - self._start_ms)
                        except Exception:
                            pass
                except Exception:
                    pass
            return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

        # 空 WndProc：让消息循环能跑（PeekMessage 派发）
        def wndproc(hwnd, msg, wparam, lparam):
            if msg == 0x0012:  # WM_QUIT
                pass
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._hook_proc_ref = HOOKPROC(hook_proc)
        self._wndproc_ref = WNDPROC(wndproc)

        # 装窗口（消息泵用）
        wc = user32.WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "GameInputTesterRecClass"
        user32.RegisterClassW(ctypes.byref(wc))
        self._hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "", 0,
            0, 0, 0, 0, None, None, wc.hInstance, None
        )
        if not self._hwnd:
            self._stop.set()
            return

        # 装钩子
        self._hook_id = user32.SetWindowsHookExW(
            self.WH_KEYBOARD_LL, self._hook_proc_ref,
            kernel32.GetModuleHandleW(None), 0
        )
        if not self._hook_id:
            self._stop.set()
            return

        # 消息循环（PeekMessage 非阻塞，配合 stop_event）
        msg = ctypes.wintypes.MSG()
        while not self._stop.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:  # 0 = WM_QUIT, -1 = error
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

# ===== 冷却回放（分组模式） =====
class CooldownPlayer:
    """
    分组冷却回放：
    - execute 区：每轮随机出现 N~M 次（受 cooldown 限制）
    - move / buff 区：每轮各只出现 1 次（按权重抽）
    - 整轮有超时（round_timeout_sec，0=不限）
    """
    GROUPS = ('execute', 'move', 'buff')

    def __init__(self, slots, rounds=1, reset_per_round=False,
                 execute_min=3, execute_max=6, round_timeout_sec=0,
                 on_progress=None, app=None):
        self.slots = slots
        self.rounds = rounds
        self.reset_per_round = reset_per_round
        self.execute_min = max(1, int(execute_min))
        self.execute_max = max(self.execute_min, int(execute_max))
        self.round_timeout_sec = max(0, int(round_timeout_sec))
        self.on_progress = on_progress
        self.app = app
        self.cancel = threading.Event()

    def _group_of(self, s):
        g = s.get('group', 'execute')
        return g if g in self.GROUPS else 'execute'

    def _weighted_pick(self, pool, rng):
        """按 weight 字段加权随机抽一个（不是简单随机）。"""
        if not pool:
            return None
        total = sum(max(0, int(s.get('weight', 1))) for s in pool)
        if total <= 0:
            return rng.choice(pool)
        r = rng.uniform(0, total)
        acc = 0
        for s in pool:
            acc += max(0, int(s.get('weight', 1)))
            if r <= acc:
                return s
        return pool[-1]

    def run(self):
        rng = random.Random()
        last_trigger = {s['physical']: 0 for s in self.slots}
        # 实时拿当前前台窗口的 HWND（用于判断焦点是否在主窗口/无效）
        hwnd_my = int(self.app.root.winfo_id()) if hasattr(self, 'app') else 0

        # 按 group 分桶
        buckets = {g: [s for s in self.slots if self._group_of(s) == g and int(s.get('weight', 1)) > 0]
                   for g in self.GROUPS}

        round_n = 0
        while (self.rounds == 0 or round_n < self.rounds) and not self.cancel.is_set():
            round_n += 1
            if self.reset_per_round:
                last_trigger = {s['physical']: 0 for s in self.slots}

            # 本轮已用的"一次性"键（move/buff 标记用过的）
            used_once = set()
            # 本轮执行区目标次数
            target_execute = rng.randint(self.execute_min, self.execute_max)
            executed = 0
            round_start = time.time()

            self.on_progress and self.on_progress(
                f"轮 {round_n} 开始 | execute={target_execute} 移动={len(buckets['move'])} buff={len(buckets['buff'])}"
            )

            while not self.cancel.is_set():
                now = int(time.time() * 1000)

                # 整轮超时检查
                if self.round_timeout_sec > 0:
                    elapsed = time.time() - round_start
                    if elapsed >= self.round_timeout_sec:
                        self.on_progress and self.on_progress(
                            f"轮 {round_n} 超时 ({elapsed:.1f}s)，跳过"
                        )
                        break

                # 检查退出条件：execute 达到目标 + move/buff 全用完
                move_done = (not buckets['move']) or all(s['physical'] in used_once for s in buckets['move'])
                buff_done = (not buckets['buff']) or all(s['physical'] in used_once for s in buckets['buff'])
                execute_done = executed >= target_execute
                if execute_done and move_done and buff_done:
                    self.on_progress and self.on_progress(
                        f"轮 {round_n} 完成 | 执行 {executed} 次"
                    )
                    break

                # 计算每个桶的"就绪"集合
                def ready_in(bucket):
                    return [s for s in bucket if now >= last_trigger[s['physical']] + self._cd_of(s, rng)]

                ready_execute = ready_in(buckets['execute'])
                # move/buff：去掉本轮已用的
                ready_move = [s for s in buckets['move'] if s['physical'] not in used_once and now >= last_trigger[s['physical']] + self._cd_of(s, rng)]
                ready_buff = [s for s in buckets['buff'] if s['physical'] not in used_once and now >= last_trigger[s['physical']] + self._cd_of(s, rng)]

                # 如果 execute 还没达到目标次数，execute 加权更高（×2 占比）
                if not execute_done:
                    candidates = ready_execute + ready_execute + ready_move + ready_buff
                else:
                    candidates = ready_move + ready_buff

                if not candidates:
                    # 等到任意一个就绪（取最近的就绪时间）
                    next_ready = []
                    for s in self.slots:
                        if s['physical'] in used_once and self._group_of(s) in ('move', 'buff'):
                            continue
                        ready_at = last_trigger[s['physical']] + self._cd_of(s, rng)
                        if ready_at > now:
                            next_ready.append(ready_at)
                    if not next_ready:
                        # 所有都就绪了（不会进 else，留兜底）
                        continue
                    delay = min(next_ready) - now
                    if self.cancel.wait(delay / 1000.0):
                        return
                    continue

                pick = self._weighted_pick(candidates, rng)
                if pick is None:
                    continue

                # 等到该键就绪（保险，理论上已经是就绪的）
                ready_at = last_trigger[pick['physical']] + self._cd_of(self._coerce_dict(pick), rng)
                delay = ready_at - int(time.time() * 1000)
                if delay > 0:
                    if self.cancel.wait(delay / 1000.0):
                        return

                # 实时检测前台窗口：如果是主窗口 / 无效 → 跳过（避免回环）
                cur_hwnd = user32.GetForegroundWindow()
                if cur_hwnd == 0 or cur_hwnd == hwnd_my:
                    self.on_progress and self.on_progress(
                        f"轮 {round_n} 跳过：前台在主窗口或无效"
                    )
                    self.cancel.wait(0.3)
                    continue

                # 发键（SendInput 自动发给当前前台窗口 cur_hwnd）
                send_key(pick['physical'])
                last_trigger[pick['physical']] = int(time.time() * 1000)
                group = self._group_of(pick)
                if group == 'execute':
                    executed += 1
                else:
                    used_once.add(pick['physical'])

                self.on_progress and self.on_progress(
                    f"轮 {round_n} | [{group}] {pick['logical']} ({pick['physical']}) | {executed}/{target_execute}"
                )

                # 触发后等待
                lo = min(int(pick.get('after_min_ms', 0)), int(pick.get('after_max_ms', 0)))
                hi = max(int(pick.get('after_min_ms', 0)), int(pick.get('after_max_ms', 0)))
                if hi > 0:
                    after = lo if lo == hi else rng.randint(lo, hi)
                    if self.cancel.wait(after / 1000.0):
                        return

    def _cd_of(self, s, rng):
        cd = int(s.get('cooldown_ms', 1000))
        jitter = rng.randint(0, int(s.get('jitter_ms', 0)) + 1)
        return cd + jitter

    def _coerce_dict(self, s):
        # candidates 列表里可能有重复引用（加权展开），已经是 dict 了
        return s

# ===== 脚本回放（按录制顺序） =====
class ScriptPlayer:
    def __init__(self, steps, loop=False, on_progress=None, app=None):
        self.steps = steps
        self.loop = loop
        self.on_progress = on_progress
        self.app = app
        self.cancel = threading.Event()

    def run(self):
        rng = random.Random()
        hwnd_my = int(self.app.root.winfo_id()) if hasattr(self, 'app') else 0
        while not self.cancel.is_set():
            for s in self.steps:
                if self.cancel.is_set():
                    return
                _, physical, mn, mx = s
                # 实时检测前台窗口
                cur_hwnd = user32.GetForegroundWindow()
                if cur_hwnd == 0 or cur_hwnd == hwnd_my:
                    self.on_progress and self.on_progress("script 跳过：前台不在")
                    self.cancel.wait(0.3)
                    continue
                send_key(physical)
                if self.on_progress:
                    self.on_progress(f"script | {s[0]} ({physical})")
                lo, hi = min(mn, mx), max(mn, mx)
                if hi > 0:
                    wait = lo if lo == hi else rng.randint(lo, hi)
                    if self.cancel.wait(wait / 1000.0):
                        return
            if not self.loop:
                break

# ===== Tkinter UI =====
class MappingDialog(tk.Toplevel):
    """键位映射编辑对话框（8 列 Treeview，含 Group）。"""
    COLUMNS = ['Logical', 'Physical', 'Group', 'CooldownMs', 'JitterMs', 'AfterMinMs', 'AfterMaxMs', 'Weight']

    def __init__(self, parent, mapping_data, on_save):
        super().__init__(parent)
        self.title("键位映射 — 冷却 / 抖动 / 加权 / 操作间隔")
        self.geometry("980x520")
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save

        # 提示
        hint = ttk.Label(self, text=(
            "  CooldownMs=冷却  JitterMs=0~+N 抖动  "
            "AfterMin/MaxMs=发完后到下一个键的等待（区间随机）  "
            "Weight=加权（0=禁用）\n"
            "  规则：发完键 → 等 after 区间 → 选下一个 → 等该键冷却好 → 发"
        ), background='#ffffe0', anchor='w', justify='left', padding=6)
        hint.pack(fill='x', side='top')

        # Treeview
        frame = ttk.Frame(self, padding=6)
        frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(frame, columns=self.COLUMNS, show='headings', height=15)
        for col in self.COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=110, anchor='w')
        self.tree.heading('Physical', text='Physical（US 104 键）')
        self.tree.heading('Group', text='Group（分组）')
        # Physical / Group 列下拉
        self.phys_combo_values = AVAILABLE_KEYS
        self.group_combo_values = ['execute', 'move', 'buff']
        for col, w in [('Logical', 100), ('Physical', 160), ('Group', 90), ('CooldownMs', 90), ('JitterMs', 80),
                       ('AfterMinMs', 100), ('AfterMaxMs', 100), ('Weight', 70)]:
            self.tree.column(col, width=w)

        vsb = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        # 加载数据
        for row in mapping_data:
            self.tree.insert('', 'end', values=[row.get(c.lower(), '') if c.lower() != 'group' else row.get('group', 'execute') for c in self.COLUMNS])

        # 编辑控件（点击单元格时弹出下拉框）
        self.tree.bind('<Double-1>', self._on_double_click)
        self._edit_entry = None
        self._edit_combo = None

        # 按钮条
        btn_bar = ttk.Frame(self, padding=6)
        btn_bar.pack(fill='x', side='bottom')
        ttk.Button(btn_bar, text="新增", command=self._add_row).pack(side='left', padx=2)
        ttk.Button(btn_bar, text="删除选中", command=self._del_row).pack(side='left', padx=2)
        ttk.Button(btn_bar, text="保存", command=self._save_and_close).pack(side='right', padx=2)
        ttk.Button(btn_bar, text="取消", command=self.destroy).pack(side='right', padx=2)

    def _on_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != 'cell':
            return
        col = self.tree.identify_column(event.x)
        col_idx = int(col.replace('#', '')) - 1
        col_name = self.COLUMNS[col_idx]
        item = self.tree.identify_row(event.y)
        if not item:
            return
        x, y, w, h = self.tree.bbox(item, col)
        current = self.tree.set(item, col_name)
        if col_name == 'Physical':
            # 下拉
            self._edit_combo = ttk.Combobox(self.tree, values=self.phys_combo_values, state='readonly')
            self._edit_combo.set(str(current))
            self._edit_combo.place(x=x, y=y, width=w, height=h)
            self._edit_combo.focus_set()
            self._edit_combo.bind('<<ComboboxSelected>>', lambda e: self._commit_edit(item, col_name, self._edit_combo.get()))
            self._edit_combo.bind('<FocusOut>', lambda e: self._destroy_edit())
        elif col_name == 'Group':
            # 下拉
            cur = str(current) if current in self.group_combo_values else 'execute'
            self._edit_combo = ttk.Combobox(self.tree, values=self.group_combo_values, state='readonly')
            self._edit_combo.set(cur)
            self._edit_combo.place(x=x, y=y, width=w, height=h)
            self._edit_combo.focus_set()
            self._edit_combo.bind('<<ComboboxSelected>>', lambda e: self._commit_edit(item, col_name, self._edit_combo.get()))
            self._edit_combo.bind('<FocusOut>', lambda e: self._destroy_edit())
        else:
            # 文本框
            self._edit_entry = ttk.Entry(self.tree)
            self._edit_entry.insert(0, str(current))
            self._edit_entry.place(x=x, y=y, width=w, height=h)
            self._edit_entry.focus_set()
            self._edit_entry.bind('<Return>', lambda e: self._commit_edit(item, col_name, self._edit_entry.get()))
            self._edit_entry.bind('<FocusOut>', lambda e: self._commit_edit(item, col_name, self._edit_entry.get()))

    def _commit_edit(self, item, col, value):
        self.tree.set(item, col, value)
        self._destroy_edit()

    def _destroy_edit(self):
        if self._edit_entry:
            self._edit_entry.destroy()
            self._edit_entry = None
        if self._edit_combo:
            self._edit_combo.destroy()
            self._edit_combo = None

    def _add_row(self):
        self.tree.insert('', 'end', values=['', 'a', 'execute', 1000, 0, 0, 0, 1])

    def _del_row(self):
        for item in self.tree.selection():
            self.tree.delete(item)

    def _save_and_close(self):
        result = []
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            row = {c.lower(): v for c, v in zip(self.COLUMNS, values)}
            try:
                row['cooldown_ms'] = int(row.get('cooldownms', 1000) or 1000)
                row['jitter_ms'] = int(row.get('jitterms', 0) or 0)
                row['after_min_ms'] = int(row.get('afterminms', 0) or 0)
                row['after_max_ms'] = int(row.get('aftermaxms', 0) or 0)
                row['weight'] = int(row.get('weight', 1) or 1)
                grp = str(row.get('group', 'execute') or 'execute')
                row['group'] = grp if grp in CooldownPlayer.GROUPS else 'execute'
            except (TypeError, ValueError) as e:
                messagebox.showerror("错误", f"数值列必须是整数: {e}", parent=self)
                return
            if not row.get('physical'):
                continue  # 跳过空行
            row.setdefault('logical', row['physical'])
            result.append(row)
        self.on_save(result)
        self.destroy()

class EditConfigDialog(tk.Toplevel):
    """内置 JSON 编辑器。"""
    def __init__(self, parent, file_path, on_saved):
        super().__init__(parent)
        self.title(f"编辑配置 — {Path(file_path).name}")
        self.geometry("800x600")
        self.transient(parent)
        self.grab_set()
        self.file_path = file_path
        self.on_saved = on_saved
        self._dirty = False

        # 工具条
        toolbar = ttk.Frame(self, padding=4)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text="格式化 (Alt+F)", command=self.format_json).pack(side='left', padx=2)
        ttk.Button(toolbar, text="校验 JSON (Alt+V)", command=self.validate_json).pack(side='left', padx=2)
        ttk.Button(toolbar, text="保存 (Ctrl+S)", command=self.save).pack(side='left', padx=2)
        ttk.Button(toolbar, text="重新加载", command=self.load_file).pack(side='left', padx=2)
        self.status_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.status_var).pack(side='right', padx=6)

        # 编辑器
        self.editor = tk.Text(self, font=('Consolas', 11), wrap='none', undo=True)
        self.editor.pack(fill='both', expand=True, padx=4, pady=4)
        self.editor.bind('<Control-s>', lambda e: self.save())
        self.editor.bind('<Control-S>', lambda e: self.save())
        self.editor.bind('<<Modified>>', self._on_modified)
        self.bind('<Alt-f>', lambda e: self.format_json())
        self.bind('<Alt-F>', lambda e: self.format_json())
        self.bind('<Alt-v>', lambda e: self.validate_json())
        self.bind('<Alt-V>', lambda e: self.validate_json())

        self.load_file()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    def _on_modified(self, event=None):
        if self.editor.edit_modified():
            self._dirty = True
            self.editor.edit_modified(False)
            self._update_status()

    def _update_status(self, msg=None, error=False):
        if msg:
            self.status_var.set(msg)
        else:
            content = self.editor.get('1.0', 'end-1c')
            lines = content.count('\n') + 1
            mark = '●' if self._dirty else '○'
            self.status_var.set(f"{mark}  {Path(self.file_path).name} | {len(content)} 字符 | {lines} 行")
        self.status_label_bg = '#ffe0e0' if error else self.cget('bg')

    def load_file(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', formatted)
            self._dirty = False
            self._update_status()
        except Exception as e:
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', f"// 加载失败: {e}\n\n")
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    self.editor.insert('end', f.read())
            except Exception:
                pass
            self._update_status(f"加载失败: {e}", error=True)

    def format_json(self):
        try:
            data = json.loads(self.editor.get('1.0', 'end-1c'))
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', formatted)
            self._dirty = True
            self._update_status("已格式化")
        except Exception as e:
            self._update_status(f"格式化失败: {e}", error=True)

    def validate_json(self):
        try:
            data = json.loads(self.editor.get('1.0', 'end-1c'))
            if isinstance(data, list):
                self._update_status(f"✓ JSON 有效，{len(data)} 项")
            else:
                self._update_status(f"✓ JSON 有效，根对象是 {type(data).__name__}")
        except Exception as e:
            self._update_status(f"❌ JSON 无效: {e}", error=True)

    def save(self):
        try:
            data = json.loads(self.editor.get('1.0', 'end-1c'))
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._dirty = False
            self._update_status(f"💾 已保存 {time.strftime('%H:%M:%S')}")
            self.on_saved(data)
        except Exception as e:
            self._update_status(f"❌ 保存失败: {e}", error=True)
            messagebox.showerror("保存失败", str(e), parent=self)

    def _on_close(self):
        if self._dirty:
            r = messagebox.askyesnocancel("未保存", "有未保存的修改，保存吗？", parent=self)
            if r is None:
                return
            if r:
                self.save()
        self.destroy()

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GameInputTester (Python)")
        self.root.geometry("1080x640")

        self.configs_dir = _app_dir() / "configs"
        self.configs_dir.mkdir(exist_ok=True)
        self.last_config_file = _app_dir() / "last_config.txt"
        self.mapping = self.load_default()
        # 全局配置：执行区每轮次数区间 + 整轮超时
        self.execute_min = 3
        self.execute_max = 6
        self.round_timeout_sec = 0
        self.active_config = None
        self._buffer = []  # 录制缓冲 [(logical, physical), ...]
        self._buffer_lock = threading.Lock()
        self._saved_hwnd = 0  # 启动回放时记录的前台窗口句柄，回放结束恢复
        self._player = None
        self._player_thread = None
        self._recorder = Recorder(on_event=self._on_recorded)
        self._recorder.set_hotkey_callback(self._on_hotkey)
        self._update_recorder_filter()
        # 钩子**启动后就一直跑**（同时承担"录制"和"全局热键"两个职责）
        self._recorder.start()

        self._build_ui()
        self._load_config_list()
        self._restore_last_config()
        self._update_status_bar()

    def _build_ui(self):
        # 顶栏：模式 + 轮数 + 重置开关
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill='x')
        ttk.Label(top, text="模式:").pack(side='left')
        self.mode_var = tk.StringVar(value="冷却随机（加权，按配置）")
        self.mode_combo = ttk.Combobox(top, textvariable=self.mode_var, values=[
            "冷却随机（加权，按配置）", "脚本回放（旧：按录制顺序）"
        ], state='readonly', width=28)
        self.mode_combo.pack(side='left', padx=4)
        self.mode_combo.bind('<<ComboboxSelected>>', lambda e: self._update_status_bar())

        sep = ttk.Separator(top, orient='vertical'); sep.pack(side='left', fill='y', padx=8)
        ttk.Label(top, text="轮数 (0=无限):").pack(side='left')
        self.rounds_var = tk.IntVar(value=5)
        ttk.Spinbox(top, from_=0, to=9999, textvariable=self.rounds_var, width=8).pack(side='left')

        sep2 = ttk.Separator(top, orient='vertical'); sep2.pack(side='left', fill='y', padx=8)
        self.reset_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="每轮重置冷却（独立测试）", variable=self.reset_var,
                        command=self._update_status_bar).pack(side='left')

        sep3 = ttk.Separator(top, orient='vertical'); sep3.pack(side='left', fill='y', padx=8)
        ttk.Label(top, text="执行区每轮:").pack(side='left')
        self.exec_min_var = tk.IntVar(value=3)
        ttk.Spinbox(top, from_=1, to=99, textvariable=self.exec_min_var, width=4,
                    command=self._update_status_bar).pack(side='left')
        ttk.Label(top, text="~").pack(side='left')
        self.exec_max_var = tk.IntVar(value=6)
        ttk.Spinbox(top, from_=1, to=99, textvariable=self.exec_max_var, width=4,
                    command=self._update_status_bar).pack(side='left')

        sep4 = ttk.Separator(top, orient='vertical'); sep4.pack(side='left', fill='y', padx=8)
        ttk.Label(top, text="轮超时(s):").pack(side='left')
        self.timeout_var = tk.IntVar(value=0)
        ttk.Spinbox(top, from_=0, to=9999, textvariable=self.timeout_var, width=5,
                    command=self._update_status_bar).pack(side='left')

        # 主体：SplitContainer
        main = ttk.PanedWindow(self.root, orient='horizontal')
        main.pack(fill='both', expand=True, padx=6, pady=6)

        # 左侧：配置列表
        left = ttk.Frame(main)
        main.add(left, weight=1)
        ttk.Label(left, text="配置文件 (configs/)", anchor='w', background='#e8e8e8',
                  relief='sunken', padding=2).pack(fill='x')
        self.config_listbox = tk.Listbox(left)
        self.config_listbox.pack(fill='both', expand=True)
        self.config_listbox.bind('<Double-Button-1>', lambda e: self._load_selected_config())
        self.config_listbox.bind('<Return>', lambda e: self._load_selected_config())
        # 右键菜单
        ctx = tk.Menu(self.root, tearoff=0)
        ctx.add_command(label="编辑...", command=self._edit_selected_config)
        ctx.add_command(label="用记事本打开", command=self._open_in_notepad)
        ctx.add_separator()
        ctx.add_command(label="删除", command=self._delete_active_config)
        def show_ctx(e):
            idx = self.config_listbox.nearest(e.y)
            if idx >= 0:
                self.config_listbox.selection_clear(0, 'end')
                self.config_listbox.selection_set(idx)
                self.config_listbox.activate(idx)
                ctx.tk_popup(e.x_root, e.y_root)
        self.config_listbox.bind('<Button-3>', show_ctx)
        ttk.Button(left, text="刷新列表", command=self._load_config_list).pack(fill='x')
        ttk.Button(left, text="打开目录", command=self._open_configs_dir).pack(fill='x')
        ttk.Button(left, text="删除当前", command=self._delete_active_config).pack(fill='x')

        # 右侧：日志 + 按钮
        right = ttk.Frame(main)
        main.add(right, weight=3)
        btn_bar = ttk.Frame(right, padding=6)
        btn_bar.pack(fill='x', side='bottom')
        for txt, cmd in [
            ("键位映射 (F4)", self.open_mapping_editor),
            ("录制 (F5 切换)", self.toggle_record),
            ("回放 (F6)", self.start_play),
            ("停止 (F7)", self.stop_play),
            ("保存配置 (Ctrl+S)", self.save_active_config),
        ]:
            ttk.Button(btn_bar, text=txt, command=cmd).pack(side='left', expand=True, fill='x', padx=2)

        self.log_text = tk.Text(right, font=('Consolas', 10), state='disabled', wrap='none')
        log_sb = ttk.Scrollbar(right, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_sb.set)
        self.log_text.pack(side='left', fill='both', expand=True, padx=(4, 0), pady=4)
        log_sb.pack(side='right', fill='y', pady=4)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief='sunken',
                                anchor='w', padding=(8, 2))
        status_bar.pack(side='bottom', fill='x')

        # Ctrl+S 保存
        self.root.bind('<Control-s>', lambda e: self.save_active_config())
        self.root.bind('<Control-S>', lambda e: self.save_active_config())

    def log(self, msg):
        def _append():
            try:
                self.log_text.config(state='normal')
                self.log_text.insert('end', f"{msg}\n")
                # 限长
                line_count = int(self.log_text.index('end-1c').split('.')[0])
                if line_count > 5000:
                    self.log_text.delete('1.0', '1001.0')
                self.log_text.see('end')
                self.log_text.config(state='disabled')
            except tk.TclError:
                pass
        self.root.after(0, _append)

    def _update_status_bar(self):
        mode = "冷却随机" if self.mode_combo.current() == 0 else "脚本回放"
        rounds = self.rounds_var.get()
        rounds_str = "∞" if rounds == 0 else str(rounds)
        reset_str = "每轮重置" if self.reset_var.get() else "跨轮累计"
        # 统计各 group 数量
        groups = {'execute': 0, 'move': 0, 'buff': 0}
        for s in self.mapping:
            g = s.get('group', 'execute')
            if g in groups:
                groups[g] += 1
        active = self.active_config or "(未命名)"
        tmo = f"超时={self.timeout_var.get()}s" if self.timeout_var.get() > 0 else "无超时"
        self.status_var.set(
            f"当前: {active} | 模式: {mode} | 总{len(self.mapping)}键 "
            f"(执行{groups['execute']}/移动{groups['move']}/BUFF{groups['buff']}) | "
            f"{rounds_str} 轮 | {reset_str} | 执行{self.exec_min_var.get()}~{self.exec_max_var.get()}次/轮 | {tmo}"
        )

    def _update_recorder_filter(self):
        """录制白名单 = 当前映射里所有 physical 键（空集 = 录所有键）。"""
        watch = {s.get('physical', '').lower() for s in self.mapping if s.get('physical')}
        self._recorder.set_filter(
            watch,
            lambda k: next((s.get('logical', k) for s in self.mapping
                            if s.get('physical', '').lower() == k.lower()), k))

    def _on_recorded(self, logical, physical, is_down, ts_ms):
        # 钩子线程 → 通过 log 走 UI 线程；_buffer 加锁
        evt_str = "Down" if is_down else "Up"
        if is_down:
            with self._buffer_lock:
                self._buffer.append((logical, physical))
        self.log(f"[{ts_ms:6}ms] {logical} {evt_str}")

    def _on_hotkey(self, hwnd: int, action: str):
        """全局热键回调（钩子线程，焦点**还在上一个前台窗口**时调）。
        hwnd 是按下 F4-F7 时真正的 GetForegroundWindow()。
        """
        # 钩子线程不能直接调 tkinter —— 用 after(0, ...) 派发到 UI 线程
        # 但 hwnd 必须先存好（_saved_hwnd）
        if action == 'F6':
            # 关键：钩子触发时 hwnd 是真正的"按下 F6 时的前台窗口"
            # 此时焦点还没切到主窗口，所以这个值是对的
            self._saved_hwnd = hwnd
            try:
                title = get_hwnd_title(hwnd) or f"HWND={hwnd}"
                self.log(f"💡 F6 按下，前台窗口: {title}")
            except Exception:
                self.log(f"💡 F6 按下，HWND={hwnd}")
        # 派发真正的回调到 UI 线程
        cb = {
            'F4': self.open_mapping_editor,
            'F5': self.toggle_record,
            'F6': self.start_play,
            'F7': self.stop_play,
        }.get(action)
        if cb:
            self.root.after(0, cb)

    # ===== 录制 / 回放 =====
    def toggle_record(self):
        if self._recorder._thread is not None:
            self._recorder.stop()
            with self._buffer_lock:
                n = len(self._buffer)
            self.log(f"■ REC done ({n} down events)")
            self._update_status_bar()
        else:
            if not self.mapping:
                self.log("⚠ 先在映射里加键")
                return
            with self._buffer_lock:
                self._buffer.clear()
            self._update_recorder_filter()
            self._recorder.start()
            self.log("● REC start")
            self._update_status_bar()

    def start_play(self):
        if self._player_thread and self._player_thread.is_alive():
            self.log("⚠ 已有回放在跑")
            return

        # 关键：_saved_hwnd 已经在 F6 按下时由钩子记录了（焦点还在前台窗口时）
        # 钩子触发早于焦点切换，所以这个值是真正的"前台窗口 HWND"
        if not self._saved_hwnd:
            self.log("⚠ 未记录前台窗口（请先切到记事本/游戏再按 F6）")
            return
        try:
            title = get_hwnd_title(self._saved_hwnd) or f"HWND={self._saved_hwnd}"
            self.log(f"💡 目标窗口: {title}")
        except Exception:
            self.log(f"💡 目标 HWND={self._saved_hwnd}")

        # 主窗口退缩到最小化（不退出，托盘图标可见可恢复）
        try:
            self.root.iconify()
        except Exception:
            pass

        # 启动前等旧 task
        rounds = self.rounds_var.get()
        if self.mode_combo.current() == 0:
            # 冷却随机（分组模式）
            if not self.mapping:
                self.log("⚠ 配置为空")
                return
            self.execute_min = self.exec_min_var.get()
            self.execute_max = max(self.execute_min, self.exec_max_var.get())
            self.round_timeout_sec = self.timeout_var.get()
            self._player = CooldownPlayer(
                self.mapping, rounds, self.reset_var.get(),
                execute_min=self.execute_min, execute_max=self.execute_max,
                round_timeout_sec=self.round_timeout_sec,
                on_progress=self.log, app=self)
            mode = "每轮重置" if self.reset_var.get() else "跨轮累计"
            tmo = f"{self.round_timeout_sec}s" if self.round_timeout_sec > 0 else "无"
            self.log(f"▶ COOLDOWN | {len(self.mapping)} 键 | {'∞' if rounds == 0 else rounds} 轮 | {mode} | "
                     f"执行{self.execute_min}~{self.execute_max}次/轮 | 超时={tmo}")
        else:
            # 脚本回放
            with self._buffer_lock:
                buffer_snapshot = list(self._buffer)
            steps = [(b[0], b[1],
                      self._get_wait_for(b[1], 'min'),
                      self._get_wait_for(b[1], 'max'))
                     for b in buffer_snapshot]
            if not steps:
                self.log("⚠ 没有可回放的动作（先录制）")
                return
            self._player = ScriptPlayer(steps, loop=False, on_progress=self.log, app=self)
            self.log(f"▶ SCRIPT | {len(steps)} steps")
        self._player_thread = threading.Thread(target=self._player.run, daemon=True)
        self._player_thread.start()

    def stop_play(self):
        if self._player:
            self._player.cancel.set()
            self.log("■ STOP")
        # 恢复主窗口
        try:
            self.root.deiconify()
        except Exception:
            pass

    def _get_wait_for(self, physical, which):
        row = next((s for s in self.mapping if s.get('physical', '').lower() == physical.lower()), None)
        if not row:
            return 1000
        if which == 'min':
            return int(row.get('cooldown_ms', 1000))
        else:
            return int(row.get('cooldown_ms', 1000)) + int(row.get('jitter_ms', 0))

    # ===== 映射管理 =====
    def open_mapping_editor(self):
        def on_save(new_mapping):
            self.mapping = new_mapping
            self._update_recorder_filter()
            self.log("✓ 映射已更新")
            self._update_status_bar()
            # 自动持久化
            self._save_internal("settings.json", new_mapping)
        MappingDialog(self.root, self.mapping, on_save)

    def _save_internal(self, name, data):
        try:
            with open(self.configs_dir / name, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"❌ {e}")

    # ===== 配置目录 =====
    def _load_config_list(self):
        self.config_listbox.delete(0, 'end')
        for p in sorted(self.configs_dir.glob("*.json")):
            self.config_listbox.insert('end', p.name)
        self._load_settings_if_exists()
        self.log(f"已加载 {self.config_listbox.size()} 个配置")

    def _load_settings_if_exists(self):
        path = self.configs_dir / "settings.json"
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list) and data:
                    self.mapping = data
                    self._update_recorder_filter()
            except Exception:
                pass

    def _load_selected_config(self):
        sel = self.config_listbox.curselection()
        if not sel:
            return
        name = self.config_listbox.get(sel[0])
        self._load_config_by_name(name)

    def _load_config_by_name(self, name):
        path = self.configs_dir / name
        if not path.exists():
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 自动识别：含 'logical' 是映射，含 'physical' + 'logicalKey' 是脚本（暂不处理脚本）
            if isinstance(data, list) and data and 'logical' in data[0]:
                self.mapping = data
                self._update_recorder_filter()
                self.active_config = name
                self.root.title(f"GameInputTester (Python) — {name}")
                self.log(f"▶ {name} ({len(data)} 键)")
                self._update_status_bar()
                self.last_config_file.write_text(name, encoding='utf-8')
            else:
                self.log(f"⚠ {name} 不是键位映射格式")
        except Exception as e:
            self.log(f"❌ {e}")

    def _restore_last_config(self):
        if self.last_config_file.exists():
            try:
                name = self.last_config_file.read_text(encoding='utf-8').strip()
                if name:
                    idx = list(self.config_listbox.get(0, 'end')).index(name) if name in self.config_listbox.get(0, 'end') else -1
                    if idx >= 0:
                        self.config_listbox.selection_set(idx)
                        self._load_config_by_name(name)
            except Exception:
                pass

    def _open_configs_dir(self):
        if os.name == 'nt':
            os.startfile(str(self.configs_dir))

    def _delete_active_config(self):
        sel = self.config_listbox.curselection()
        if not sel:
            self.log("⚠ 未选中配置")
            return
        name = self.config_listbox.get(sel[0])
        if name == 'settings.json':
            self.log("⚠ 不能删 settings.json")
            return
        if not messagebox.askyesno("确认", f"删除配置 {name}？"):
            return
        try:
            (self.configs_dir / name).unlink()
            self.log(f"🗑 {name}")
            if self.active_config == name:
                self.active_config = None
                self.root.title("GameInputTester (Python)")
            self._load_config_list()
        except Exception as e:
            self.log(f"❌ {e}")

    def _edit_selected_config(self):
        sel = self.config_listbox.curselection()
        if not sel:
            return
        name = self.config_listbox.get(sel[0])
        if name == 'settings.json':
            self.log("⚠ settings.json 由映射对话框管理")
            return
        path = self.configs_dir / name
        def on_saved(data):
            self.log(f"✓ {name} 已保存")
            # 如果是当前激活配置，重新加载
            if self.active_config == name:
                self._load_config_by_name(name)
        EditConfigDialog(self.root, str(path), on_saved)

    def _open_in_notepad(self):
        sel = self.config_listbox.curselection()
        if not sel:
            return
        name = self.config_listbox.get(sel[0])
        if os.name == 'nt':
            os.startfile(str(self.configs_dir / name))

    def save_active_config(self):
        """保存为配置（弹文件对话框）。"""
        path = filedialog.asksaveasfilename(
            parent=self.root,
            initialdir=str(self.configs_dir),
            defaultextension=".json",
            initialfile=f"script_{time.strftime('%Y%m%d_%H%M%S')}.json",
        )
        if not path:
            return
        try:
            steps = []
            with self._buffer_lock:
                buffer_snapshot = list(self._buffer)
            for logical, physical in buffer_snapshot:
                row = next((s for s in self.mapping if s.get('physical', '').lower() == physical.lower()), None)
                cd = int(row.get('cooldown_ms', 1000)) if row else 1000
                jt = int(row.get('jitter_ms', 0)) if row else 0
                steps.append({
                    'logical': logical,
                    'physical': physical,
                    'cooldown_ms': cd,
                    'jitter_ms': jt,
                    'after_min_ms': int(row.get('after_min_ms', 0)) if row else 0,
                    'after_max_ms': int(row.get('after_max_ms', 0)) if row else 0,
                    'weight': int(row.get('weight', 1)) if row else 1,
                })
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(steps, f, indent=2, ensure_ascii=False)
            self.log(f"💾 {Path(path).name}")
            self._load_config_list()
            # 自动选中新文件
            new_name = Path(path).name
            if new_name in self.config_listbox.get(0, 'end'):
                idx = list(self.config_listbox.get(0, 'end')).index(new_name)
                self.config_listbox.selection_clear(0, 'end')
                self.config_listbox.selection_set(idx)
                self._load_config_by_name(new_name)
        except Exception as e:
            self.log(f"❌ {e}")

    # ===== 生命周期 =====
    def load_default(self):
        return [
            {'logical': 'A', 'physical': 'a',     'cooldown_ms': 8000, 'jitter_ms': 1000, 'after_min_ms': 1000, 'after_max_ms': 2000, 'weight': 1},
            {'logical': 'B', 'physical': 's',     'cooldown_ms': 5000, 'jitter_ms':  500, 'after_min_ms': 1000, 'after_max_ms': 1500, 'weight': 1},
            {'logical': 'C', 'physical': 'd',     'cooldown_ms': 3000, 'jitter_ms':  300, 'after_min_ms': 1000, 'after_max_ms': 1500, 'weight': 1},
            {'logical': 'D', 'physical': 'f',     'cooldown_ms': 1000, 'jitter_ms':  200, 'after_min_ms': 1000, 'after_max_ms': 1500, 'weight': 1},
        ]

    def on_close(self):
        try:
            self._player and self._player.cancel.set()
            self._recorder.stop()
            if self._player_thread:
                self._player_thread.join(timeout=1.0)
        finally:
            self.root.destroy()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

if __name__ == "__main__":
    if os.name != 'nt':
        print("⚠ 此程序必须在 Windows 上运行（依赖 Win32 SendInput / RegisterHotKey）")
        print("  macOS / Linux 上可静态检查：python3 -m py_compile game_input_tester.py")
        import sys
        sys.exit(0)
    App().run()
