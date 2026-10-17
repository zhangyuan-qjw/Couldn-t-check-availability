# -*- coding: utf-8 -*-
"""操作录制与回放（脚本化安装器操作，v2）。

录制：用户像平时一样手动完成安装/卸载，工具通过全局鼠标/键盘钩子记录
      目标进程树窗口上的操作：
        - 按钮点击（控件类名/文字 + 相对坐标兜底）
        - 勾选/单选（记录点击后的期望状态）
        - 文本编辑（记录编辑框最终输入的文本）
        - 下拉框/列表选择（记录最终选中的项）
        - 回车按键
      钩子回调只做“入队”这一件事（绝不阻塞），事件由独立工作线程处理，
      保证录制期间鼠标流畅。

脚本（v2，可保存多个）：
      scripts/<自定义名称>_<时间戳>.json
      { "version": 2, "display_name": ..., "program": {name,size,md5头},
        "recorded_at": ..., "steps": [...] }
      按 program 三元组匹配安装程序（换机器、换路径都能对上）。

回放：按脚本逐步执行；控件匹配失败退回相对坐标点击；回放完毕后交由
      通用自动点击器兜底。
"""
import ctypes
import datetime
import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from ctypes import wintypes

from .. import util
from . import _autoclick

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012
VK_RETURN = 0x0D
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_TAB = 0x09
_KEY_NAMES = {VK_RETURN: "enter", VK_UP: "up", VK_DOWN: "down",
              VK_LEFT: "left", VK_RIGHT: "right", VK_TAB: "tab"}
_KEY_VKS = {v: k for k, v in _KEY_NAMES.items()}
GA_ROOT = 2
GW_OWNER = 4
WM_SETTEXT = 0x000C
BM_GETCHECK = 0x00F0
BM_CLICK = 0x00F5
BST_CHECKED = 0x0001
GWL_STYLE = -16
BS_TYPEMASK = 0x000F
_TOGGLE_STYLES = (0x2, 0x3, 0x4, 0x5, 0x6, 0x9)  # 勾选/单选类按钮样式
CB_SELECTSTRING = 0x014D
CB_FINDSTRINGEXACT = 0x0158
CB_SETCURSEL = 0x014E
LB_SELECTSTRING = 0x018C
LB_GETCURSEL = 0x0188
LB_GETTEXT = 0x0189
LVM_GETNEXTITEM = 0x100C
LVM_GETITEMTEXTW = 0x1073
LVNI_SELECTED = 0x0002
LVIF_TEXT = 0x0001
TVM_GETNEXTITEM = 0x110A
TVM_GETITEMW = 0x113E
TVGN_CARET = 0x0009
TVIF_TEXT = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002

SCRIPT_VERSION = 2

_DETAIL_CLASSES = ("SysListView32", "SysTreeView32", "TListView", "TTreeView")


class LVITEMW(ctypes.Structure):
    _fields_ = [("mask", wintypes.UINT), ("iItem", ctypes.c_int),
                ("iSubItem", ctypes.c_int), ("state", wintypes.UINT),
                ("stateMask", wintypes.UINT), ("pszText", wintypes.LPWSTR),
                ("cchTextMax", ctypes.c_int)]


class TVITEMW(ctypes.Structure):
    _fields_ = [("mask", wintypes.UINT), ("hItem", wintypes.HANDLE),
                ("state", wintypes.UINT), ("stateMask", wintypes.UINT),
                ("pszText", wintypes.LPWSTR), ("cchTextMax", ctypes.c_int)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

try:
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
    user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_longlong
    user32.WindowFromPoint.argtypes = [POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
except Exception:
    pass


# ---------------- 脚本存取 ----------------
def program_key(installer):
    """安装程序识别键：(名称, 大小, 头部 md5)。换机器、换路径也能匹配。"""
    try:
        st = os.stat(installer)
        with open(installer, "rb") as f:
            head = f.read(65536)
        return (os.path.basename(installer), st.st_size, hashlib.md5(head).hexdigest()[:8])
    except OSError:
        return (os.path.basename(installer), 0, "")


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def find_scripts(installer):
    """返回该安装程序的所有录制脚本路径（新的在前）"""
    key = program_key(installer)
    out = []
    d = util.scripts_dir()
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for fn in names:
        if not fn.lower().endswith(".json"):
            continue
        p = os.path.join(d, fn)
        data = _load(p)
        if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or not data["steps"]:
            continue
        prog = data.get("program")
        if isinstance(prog, dict):
            if (prog.get("name") == key[0] and prog.get("size") == key[1]
                    and prog.get("md5") == key[2]):
                out.append(p)
        else:
            # 兼容 v1：文件名里带内容键
            if fn.startswith(util.sanitize_filename(key[0]) + "_%d_%s" % (key[1], key[2])):
                out.append(p)
    out.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return out


def find_script(installer):
    """返回该安装程序最新的录制脚本路径（不存在则 None）"""
    scripts = find_scripts(installer)
    return scripts[0] if scripts else None


def load_script(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def script_summary(path):
    """脚本列表展示信息 (display_name, program_name, steps, recorded_at)"""
    data = _load(path)
    if not data:
        return (os.path.basename(path)[:-5], "", 0, "")
    return (str(data.get("display_name") or os.path.basename(path)[:-5]),
            str((data.get("program") or {}).get("name") or ""),
            len(data.get("steps") or []),
            str(data.get("recorded_at") or ""))


def resolve_program(script_path, fallback_path=""):
    """定位脚本对应的程序文件（回放用）：优先脚本记住的路径，
    其次目标程序入口（内容匹配），最后脚本同目录同名文件。"""
    data = _load(script_path)
    if not data:
        return ""
    prog = data.get("program") or {}
    p = (prog.get("path") or "").strip()
    if p and os.path.isfile(p):
        return p
    key = (prog.get("name"), prog.get("size"), prog.get("md5"))
    fb = (fallback_path or "").strip()
    if fb and os.path.isfile(fb) and program_key(fb) == key:
        return fb
    cand = os.path.join(os.path.dirname(script_path), prog.get("name") or "")
    if os.path.isfile(cand):
        return cand
    return ""


# ---------------- 录制器 ----------------
class Recorder:
    """全局钩子录制器：记录目标进程树窗口上的用户操作。

    架构：钩子线程只负责泵消息（回调仅入队）；工作线程处理事件；
          保证录制期间鼠标/键盘输入流畅。
    """

    def __init__(self, installer, log=None, on_status=None):
        self.installer = installer
        self.log = log or (lambda m: None)
        self.on_status = on_status or (lambda s: None)
        self.steps = []
        self._steps_lock = threading.Lock()
        self._stop = threading.Event()
        self._evq = queue.Queue()
        self.proc = None
        self.tree_pids = set()
        self._thread_id = None
        self._exited_notified = False
        self._active_edit = None
        self._active_edit_win = None
        self._active_edit_before = ""
        self._last_step_time = time.time()
        self._pending_selects = []   # [(deadline, control_hwnd)]
        self._pending_details = []   # 列表/树控件明细选择延迟捕获
        self._last_select = None

    # ---- 生命周期 ----
    def start(self):
        self.proc = subprocess.Popen([self.installer],
                                     cwd=os.path.dirname(self.installer) or None)
        self.tree_pids = {self.proc.pid}
        threading.Thread(target=self._watch_tree, daemon=True).start()
        threading.Thread(target=self._hook_loop, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        self.log("已开始录制：请像平时一样手动完成安装/卸载操作"
                 "（只记录该程序窗口上的操作，其它窗口不受影响）")
        self.on_status("录制中… 已记录 0 步")

    def stop(self):
        """停止录制（不保存）"""
        self._stop.set()
        tid = self._thread_id
        if tid:
            try:
                user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        self.log("录制已停止")
        self.on_status("录制已停止")

    def save(self, display_name=None):
        """保存脚本（可继续录制），返回脚本路径"""
        name = (display_name or "").strip() or os.path.splitext(os.path.basename(self.installer))[0]
        key = program_key(self.installer)
        data = {
            "version": SCRIPT_VERSION,
            "display_name": name,
            "program": {"name": key[0], "size": key[1], "md5": key[2],
                        "path": os.path.abspath(self.installer)},
            "recorded_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "steps": list(self.steps),
        }
        d = util.scripts_dir()
        os.makedirs(d, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(d, "%s_%s.json" % (util.sanitize_filename(name), stamp))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.log("脚本已保存：%s（%s 个操作）" % (path, len(self.steps)))
        self.on_status("已保存脚本：%s" % name)
        return path

    def is_recording(self):
        return self.proc is not None and not self._stop.is_set()

    # ---- 内部：线程 ----
    def _watch_tree(self):
        while not self._stop.is_set():
            try:
                if self.proc is not None:
                    self.tree_pids |= _autoclick.process_tree(self.proc.pid)
            except Exception:
                pass
            time.sleep(0.3)
        if self.proc is not None and not self._exited_notified:
            pass

    def _hook_loop(self):
        """钩子线程：只泵消息，回调里只入队，保证输入流畅"""
        try:
            hmod = kernel32.GetModuleHandleW(None)
            self._cb_mouse = HOOKPROC(self._on_mouse)
            self._cb_key = HOOKPROC(self._on_key)
            hm = user32.SetWindowsHookExW(WH_MOUSE_LL, self._cb_mouse, hmod, 0)
            hk = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._cb_key, hmod, 0)
            if not hm or not hk:
                err = kernel32.GetLastError()
                self._stop.set()
                self.log("录制钩子安装失败（错误码 %s），本机无法进行全局输入录制。" % err)
                self.on_status("录制失败：钩子安装失败")
                return
            self._thread_id = kernel32.GetCurrentThreadId()
            msg = MSG()
            while True:
                r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if hm:
                user32.UnhookWindowsHookEx(hm)
            if hk:
                user32.UnhookWindowsHookEx(hk)
        except Exception as e:
            self.log("录制钩子异常：%s" % e)
            self.on_status("录制异常：%s" % e)

    def _on_mouse(self, wcode, wparam, lparam):
        try:
            s = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if wparam == WM_LBUTTONUP:
                self._evq.put(("click", s.pt.x, s.pt.y))
            elif wparam == WM_MOUSEWHEEL:
                delta = ctypes.c_int16((s.mouseData >> 16) & 0xFFFF).value
                self._evq.put(("wheel", s.pt.x, s.pt.y, delta))
        except Exception:
            pass
        return user32.CallNextHookEx(None, wcode, wparam, lparam)

    def _on_key(self, wcode, wparam, lparam):
        try:
            if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                ks = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                name = _KEY_NAMES.get(ks.vkCode)
                if name and not (ks.flags & 0x80):  # 跳过重复按键
                    self._evq.put(("key", name))
        except Exception:
            pass
        return user32.CallNextHookEx(None, wcode, wparam, lparam)

    def _worker(self):
        """工作线程：处理入队事件 + 延迟捕获 + 程序退出提醒"""
        try:
            while not self._stop.is_set() or not self._evq.empty():
                try:
                    ev = self._evq.get(timeout=0.2)
                except queue.Empty:
                    self._process_pending()
                    continue
                if ev[0] == "click":
                    x, y = ev[1], ev[2]
                    w = user32.WindowFromPoint(POINT(x, y))
                    if w:
                        pid, root = self._pid_of_root(w)
                        if pid and pid in self.tree_pids:
                            self._proc_click(x, y, root, w)
                elif ev[0] == "wheel":
                    x, y, delta = ev[1], ev[2], ev[3]
                    w = user32.WindowFromPoint(POINT(x, y))
                    if w:
                        pid, root = self._pid_of_root(w)
                        if pid and pid in self.tree_pids:
                            self._proc_wheel(x, y, delta, root, w)
                elif ev[0] == "key":
                    fg = user32.GetForegroundWindow()
                    if fg:
                        pid, _root = self._pid_of_root(fg)
                        if pid and pid in self.tree_pids:
                            self._proc_key(ev[1], fg)
                self._process_pending()
                self._notify_exit()
            self._finalize_edit()
        except Exception as e:
            self.log("录制处理异常：%s" % e)

    def _process_pending(self):
        now = time.time()
        remaining = []
        for deadline, ctrl in self._pending_selects:
            if now >= deadline:
                self._capture_select(ctrl)
            else:
                remaining.append((deadline, ctrl))
        self._pending_selects = remaining
        remaining = []
        for deadline, ctrl in self._pending_details:
            if now >= deadline:
                self._capture_detail(ctrl)
            else:
                remaining.append((deadline, ctrl))
        self._pending_details = remaining

    def _notify_exit(self):
        if self._exited_notified:
            return
        if self.proc is not None and self.proc.poll() is not None:
            self._exited_notified = True
            self.on_status("程序已退出，可保存脚本（已记录 %s 步）" % len(self.steps))

    # ---- 内部：记录逻辑 ----
    def _pid_of_root(self, hwnd):
        try:
            root = user32.GetAncestor(hwnd, GA_ROOT)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
            return pid.value, root
        except Exception:
            return None, None

    def _append(self, step):
        step["wait_after"] = round(min(max(time.time() - self._last_step_time, 0.3), 15.0), 2)
        self._last_step_time = time.time()
        with self._steps_lock:
            self.steps.append(step)
            n = len(self.steps)
        self.on_status("录制中… 已记录 %s 步" % n)

    def _win_info(self, root):
        return {"win_title": _autoclick._window_text(root)[:80],
                "win_class": _autoclick._class_name(root)}

    def _ctrl_info(self, root, ctrl):
        idx = 0
        cls = _autoclick._class_name(ctrl)
        try:
            for ch, ccls, _t in _autoclick._enum_children(root):
                if ccls == cls:
                    if ch == ctrl:
                        break
                    idx += 1
        except Exception:
            pass
        return {"ctrl_class": cls, "ctrl_text": _autoclick._window_text(ctrl)[:80],
                "ctrl_index": idx}

    def _rel_point(self, root, x, y):
        r = _autoclick._rect(root)
        if r and (r[2] - r[0]) > 0 and (r[3] - r[1]) > 0:
            return round((x - r[0]) / float(r[2] - r[0]), 3), round((y - r[1]) / float(r[3] - r[1]), 3)
        return None

    def _finalize_edit(self):
        if not self._active_edit:
            return
        try:
            value = _autoclick._window_text(self._active_edit)
            if value != self._active_edit_before and value.strip():
                step = {"type": "set_text",
                        "ctrl_class": _autoclick._class_name(self._active_edit),
                        "ctrl_text_before": self._active_edit_before[:80],
                        "value": value[:500]}
                if self._active_edit_win:
                    step.update(self._ctrl_info(self._active_edit_win, self._active_edit))
                self._append(step)
        except Exception:
            pass
        self._active_edit = None
        self._active_edit_win = None

    def _proc_click(self, x, y, root, w):
        cls = _autoclick._class_name(w)
        text = _autoclick._window_text(w)
        rel = self._rel_point(root, x, y) or (0.5, 0.5)

        if cls == "ComboLBox":  # 下拉列表弹出项 → 记录所属下拉框的选择
            owner = user32.GetWindow(w, GW_OWNER)
            if owner:
                self._pending_selects.append((time.time() + 0.25, owner))
            return

        if cls in ("Edit", "TEdit"):  # 文本编辑框：离开时记录最终文本
            self._finalize_edit()
            self._active_edit = w
            self._active_edit_win = root
            self._active_edit_before = text
            return

        self._finalize_edit()

        if cls in ("ComboBox", "TComboBox", "ListBox", "TListBox", "TCheckListBox"):
            self._pending_selects.append((time.time() + 0.25, w))
            return

        # 列表/树控件：点击选择明细 → 延迟捕获选中项文本（不回放通用点击）
        if cls in _DETAIL_CLASSES:
            step = {"type": "select_detail", "ctrl_class": cls}
            step.update(self._win_info(root))
            step.update(self._ctrl_info(root, w))
            step["rel_x"], step["rel_y"] = rel
            self._append(step)
            self._pending_details.append((time.time() + 0.25, w))
            return

        step = {"type": "click"}
        step.update(self._win_info(root))
        step.update(self._ctrl_info(root, w))
        step["rel_x"], step["rel_y"] = rel
        if cls in ("CheckBox", "TCheckBox", "RadioButton", "TRadioButton") or \
                (cls == "Button" and self._is_toggle_style(w)):
            try:
                time.sleep(0.12)
                step["state"] = 1 if user32.SendMessageW(w, BM_GETCHECK, 0, 0) == BST_CHECKED else 0
            except Exception:
                pass
        self._append(step)

    @staticmethod
    def _is_toggle_style(hwnd):
        try:
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            return (style & BS_TYPEMASK) in _TOGGLE_STYLES
        except Exception:
            return False

    def _proc_wheel(self, x, y, delta, root, w):
        """滚轮：连续同方向滚动合并成一步"""
        self._finalize_edit()
        sign = 1 if delta > 0 else -1
        now = time.time()
        if self.steps:
            last = self.steps[-1]
            if last.get("type") == "wheel" and last.get("sign") == sign \
                    and now - self._last_step_time < 0.8:
                last["delta"] = int(last.get("delta") or 0) + delta
                self._last_step_time = now
                return
        step = {"type": "wheel", "delta": int(delta), "sign": sign}
        step.update(self._win_info(root))
        step.update(self._ctrl_info(root, w))
        step["rel_x"], step["rel_y"] = self._rel_point(root, x, y) or (0.5, 0.5)
        self._append(step)

    def _proc_key(self, name, fg):
        self._finalize_edit()
        step = {"type": "key", "key": name}
        step.update(self._win_info(fg))
        self._append(step)

    def _capture_select(self, ctrl):
        cls = _autoclick._class_name(ctrl)
        value = ""
        try:
            if cls in ("ComboBox", "TComboBox"):
                value = _autoclick._window_text(ctrl)
            elif cls in ("ListBox", "TListBox", "TCheckListBox"):
                cur = user32.SendMessageW(ctrl, LB_GETCURSEL, 0, 0)
                if cur != 0xFFFFFFFF:
                    n = user32.SendMessageW(ctrl, LB_GETTEXTLEN, cur, 0)
                    buf = ctypes.create_unicode_buffer(n + 2)
                    user32.SendMessageW(ctrl, LB_GETTEXT, cur,
                                        ctypes.cast(buf, ctypes.c_void_p).value or 0)
                    value = buf.value
        except Exception:
            pass
        if not value:
            return
        if self._last_select and self._last_select[0] == ctrl and self._last_select[1] == value:
            return  # 同一下拉框连续重复事件，去重
        self._finalize_edit()
        step = {"type": "select", "ctrl_class": cls, "value": value[:200]}
        root = user32.GetAncestor(ctrl, GA_ROOT)
        if root:
            step.update(self._ctrl_info(root, ctrl))
        self._last_select = (ctrl, value)
        self._append(step)

    def _capture_detail(self, ctrl):
        """列表/树控件：捕获当前选中项的文本，回填到最近一步 select_detail"""
        cls = _autoclick._class_name(ctrl)
        value = ""
        try:
            if cls in ("SysListView32", "TListView"):
                idx = user32.SendMessageW(ctrl, LVM_GETNEXTITEM, 0xFFFFFFFF, LVNI_SELECTED)
                if idx not in (-1, 0xFFFFFFFF):
                    item = LVITEMW()
                    item.mask = LVIF_TEXT
                    item.iItem = idx
                    item.iSubItem = 0
                    item.pszText = ctypes.create_unicode_buffer(512)
                    item.cchTextMax = 512
                    user32.SendMessageW(ctrl, LVM_GETITEMTEXTW, idx, ctypes.byref(item))
                    value = item.pszText.value or ""
            elif cls in ("SysTreeView32", "TTreeView"):
                hitem = user32.SendMessageW(ctrl, TVM_GETNEXTITEM, TVGN_CARET, 0)
                if hitem:
                    item = TVITEMW()
                    item.mask = TVIF_TEXT
                    item.hItem = hitem
                    item.pszText = ctypes.create_unicode_buffer(512)
                    item.cchTextMax = 512
                    user32.SendMessageW(ctrl, TVM_GETITEMW, 0, ctypes.byref(item))
                    value = item.pszText.value or ""
        except Exception:
            pass
        if not value:
            return
        for step in reversed(self.steps):
            if step.get("type") == "select_detail" and step.get("ctrl_class") == cls \
                    and not step.get("value"):
                step["value"] = value[:200]
                self.on_status("录制中… 已记录 %s 步" % len(self.steps))
                return


# ---------------- 回放器 ----------------
class ReplayRunner:
    """按录制脚本逐步回放操作；控件匹配失败时退回相对坐标点击"""

    def __init__(self, steps, log=None, speed=1.0):
        self.steps = list(steps or [])
        self.log = log or (lambda m: None)
        self.speed = max(float(speed or 1.0), 0.2)
        self.i = 0
        self.step_time = time.time()
        self.done = not self.steps

    def tick(self, root_pids, state):
        """每个轮询周期调用一次；返回本周期执行的动作描述列表"""
        if self.done:
            return []
        acts = []
        step = self.steps[self.i]
        wait = min(max(float(step.get("wait_after") or 0.5) / self.speed, 0.2), 10.0)
        now = time.time()
        if now - self.step_time < wait:
            return []
        try:
            acts.extend(self._exec(step, root_pids, state))
            executed = True
        except _WindowMissing:
            if now - self.step_time > 30.0:
                acts.append("回放：目标窗口迟迟未出现，跳过步骤 %s" % (self.i + 1))
                executed = True
            else:
                executed = False
        if executed:
            acts.insert(0, "回放 %s/%s 步" % (self.i + 1, len(self.steps)))
            self.i += 1
            self.step_time = now
            if self.i >= len(self.steps):
                self.done = True
                acts.append("录制脚本已全部回放完毕 ✓")
        return acts

    def _exec(self, step, root_pids, state):
        wins = _autoclick.visible_tree_windows(root_pids, state.get("baseline", set()), state)
        win = self._find_window(wins, step)
        if not win:
            raise _WindowMissing()
        stype = step.get("type")
        if stype == "click":
            return self._exec_click(win, step)
        if stype == "set_text":
            return self._exec_set_text(win, step)
        if stype == "select":
            return self._exec_select(win, step)
        if stype == "select_detail":
            return self._exec_select_detail(win, step)
        if stype == "wheel":
            return self._exec_wheel(win, step)
        if stype == "key":
            return self._exec_key(win, step)
        return ["回放：跳过未知步骤类型 %s" % stype]

    def _find_window(self, wins, step):
        title = (step.get("win_title") or "").strip()
        cls = (step.get("win_class") or "").strip()
        if title:
            nt = _autoclick._normalize(title)
            for h, _p, t in wins:
                if nt and nt in _autoclick._normalize(t):
                    return h
        if cls:
            for h, _p, t in wins:
                if cls == _autoclick._class_name(h):
                    return h
        return wins[0][0] if wins else None

    def _find_control(self, win, step):
        """按（类名+文字）匹配控件。只做文字匹配：匹配失败返回 None（由调用方
        退化为相对坐标点击），绝不用“序号”猜控件（可能点错按钮）。"""
        children = _autoclick._enum_children(win)
        cls = step.get("ctrl_class") or ""
        text = (step.get("ctrl_text") or "").strip()
        if not text:
            return None
        same = [c for c in children if c[1] == cls]
        nt = _autoclick._normalize(text)
        for ch, _cls, t in same:
            if nt and nt == _autoclick._normalize(t):
                return ch, _cls, t
        for ch, _cls, t in same:
            if nt and nt in _autoclick._normalize(t):
                return ch, _cls, t
        return None

    @staticmethod
    def _is_toggle_style(hwnd):
        try:
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            return (style & BS_TYPEMASK) in _TOGGLE_STYLES
        except Exception:
            return False

    def _exec_click(self, win, step):
        ctrl = self._find_control(win, step)
        want = step.get("state")
        if ctrl:
            ch, cls, text = ctrl
            is_toggle = cls in ("CheckBox", "TCheckBox", "RadioButton", "TRadioButton") \
                or (cls == "Button" and self._is_toggle_style(ch))
            if want is not None and is_toggle:
                try:
                    cur = 1 if user32.SendMessageW(ch, BM_GETCHECK, 0, 0) == BST_CHECKED else 0
                    if cur == want:
                        return ["回放：勾选状态已一致，跳过「%s」" % text.strip()]
                    user32.SendMessageW(ch, BM_CLICK, 0, 0)
                    return ["回放：点击「%s」（设定勾选状态）" % text.strip()]
                except Exception:
                    pass
            _autoclick._click_control(ch, cls)
            return ["回放：点击「%s」" % text.strip()]
        # 控件没匹配到 → 按录制的相对坐标点击
        rx, ry = float(step.get("rel_x", 0.5)), float(step.get("rel_y", 0.5))
        r = _autoclick._rect(win)
        if r:
            x = int(r[0] + (r[2] - r[0]) * rx)
            y = int(r[1] + (r[3] - r[1]) * ry)
            if _autoclick._point_owned_by(x, y, win):
                user32.SetCursorPos(x, y)
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                return ["回放：按录制坐标点击窗口位置 (%.0f%%, %.0f%%)" % (rx * 100, ry * 100)]
        return ["回放：未找到控件，跳过该步骤"]

    def _exec_set_text(self, win, step):
        ctrl = self._find_control(win, step)
        if not ctrl:
            return ["回放：未找到输入框，跳过填写"]
        ch, _cls, _t = ctrl
        value = step.get("value") or ""
        buf = ctypes.c_wchar_p(value)
        user32.SendMessageW(ch, WM_SETTEXT, 0, ctypes.cast(buf, ctypes.c_void_p).value or 0)
        return ["回放：输入文本「%s」" % value]

    def _exec_select(self, win, step):
        ctrl = self._find_control(win, step)
        if not ctrl:
            return ["回放：未找到选择控件，跳过"]
        ch, cls, _t = ctrl
        value = step.get("value") or ""
        vb = ctypes.c_wchar_p(value)
        vptr = ctypes.cast(vb, ctypes.c_void_p).value or 0
        try:
            if cls in ("ComboBox", "TComboBox"):
                if user32.SendMessageW(ch, CB_SELECTSTRING, 0xFFFFFFFF, vptr) == 0xFFFFFFFF:
                    idx = user32.SendMessageW(ch, CB_FINDSTRINGEXACT, 0xFFFFFFFF, vptr)
                    if idx != 0xFFFFFFFF:
                        user32.SendMessageW(ch, CB_SETCURSEL, idx, 0)
                    else:
                        user32.SendMessageW(ch, WM_SETTEXT, 0, vptr)
            elif cls in ("ListBox", "TListBox", "TCheckListBox"):
                user32.SendMessageW(ch, LB_SELECTSTRING, 0xFFFFFFFF, vptr)
            return ["回放：选择「%s」" % value]
        except Exception as e:
            return ["回放：选择「%s」失败（%s）" % (value, e)]

    def _exec_select_detail(self, win, step):
        """列表/树明细选择：优先按控件类定位后点击录制的相对坐标"""
        cls = step.get("ctrl_class") or ""
        target = win
        ctrl = self._find_control(win, step)
        if not ctrl:
            for ch, ccls, _t in _autoclick._enum_children(win):
                if ccls == cls:
                    ctrl = (ch, ccls, "")
                    target = ch
                    break
        rx, ry = float(step.get("rel_x", 0.5)), float(step.get("rel_y", 0.5))
        r = _autoclick._rect(target)
        if r:
            x = int(r[0] + (r[2] - r[0]) * rx)
            y = int(r[1] + (r[3] - r[1]) * ry)
            if _autoclick._point_owned_by(x, y, win):
                user32.SetCursorPos(x, y)
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                value = step.get("value") or ""
                if value:
                    return ["回放：选择明细「%s」" % value]
                return ["回放：按录制位置选择明细"]
        return ["回放：未找到明细控件，跳过该步骤"]

    def _exec_wheel(self, win, step):
        """滚轮：鼠标移到录制位置后滚动对应方向"""
        rx, ry = float(step.get("rel_x", 0.5)), float(step.get("rel_y", 0.5))
        r = _autoclick._rect(win)
        if r:
            x = int(r[0] + (r[2] - r[0]) * rx)
            y = int(r[1] + (r[3] - r[1]) * ry)
            if _autoclick._point_owned_by(x, y, win):
                user32.SetCursorPos(x, y)
                delta = int(step.get("delta") or 120)
                user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
                return ["回放：滚动滚轮（%s %s）" % (delta, "上" if delta > 0 else "下")]
        return ["回放：未找到滚动目标，跳过该步骤"]

    def _exec_key(self, win, step):
        vk = _KEY_VKS.get(str(step.get("key") or ""))
        if not vk:
            return ["回放：跳过未知按键 %s" % step.get("key")]
        try:
            user32.SetForegroundWindow(win)
        except Exception:
            pass
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        names = {"enter": "回车", "up": "↑", "down": "↓", "left": "←",
                 "right": "→", "tab": "Tab"}
        return ["回放：按键 %s" % names.get(str(step.get("key")), step.get("key"))]


class _WindowMissing(Exception):
    pass
