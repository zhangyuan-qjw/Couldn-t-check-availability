# -*- coding: utf-8 -*-
"""安装向导全自动点击器 v2（中英文通用、绝不点取消）。

分层点击（每层都带“取消/返回/不同意…”黑名单，命中黑名单的控件一律跳过）：
  1) Win32 标准控件：按钮文字匹配（中/英）→ BM_CLICK（标准 Button）或鼠标点击（自绘按钮）；
  2) UIA（UI Automation，pywin32 迟绑定；Win7 自带 UIAutomationCore，无需额外依赖）：
     对 DirectUI / WPF / 自绘 / 浏览器内核安装器同样有效 → Invoke / DoDefaultAction；
  3) 向导默认按钮（DM_GETDEFID，几乎总是 下一步/安装/确定）→ 点击；
  4) 回车兜底（触发默认按钮）。

安全约束（对应“不要点击取消”）：
  - 永不点击文字含 取消/Cancel/返回/Back/不同意/稍后/跳过/浏览/更改… 的控件；
  - 不做任何“盲坐标点击”（老版本按窗口比例盲点右下角，可能点中取消，已移除）；
  - 鼠标点击前校验坐标点确实落在目标窗口上（窗口被遮挡时只走消息点击，绝不乱点）；
  - 每个控件每页只操作一次，避免同一按钮被连续点两次导致跳页。

其他：
  - 自动勾选“我接受/我同意”类协议单选框/复选框（绝不动“不同意”）；
  - 自动把安装目录编辑框填为指定目录；
  - 只处理属于安装进程树、或启动后新出现且“长得像安装器”的窗口。
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
BM_GETCHECK = 0x00F0
BST_CHECKED = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_RETURN = 0x0D

# ---------------- 关键词表（顺序即优先级） ----------------
# 点击关键词：规范化文本以这些词“开头”才点击（最长优先，先中文后英文）
CLICK_PREFIXES = (
    "立即安装", "开始安装", "一键安装", "马上安装", "现在安装",
    "完成安装", "安装完成",
    "下一步", "继续安装", "继续",
    "安装", "立即", "开始", "现在", "start", "install", "next", "continue", "now",
    "我接受", "我同意", "同意协议", "接受协议", "同意", "接受", "accept", "agree",
    "完成", "结束", "finish", "done", "complete", "end",
    "确定", "确认", "ok", "yes", "是",
)
# 完成页关键词：点击到这类按钮说明向导已走完（用于完成判定）
FINISH_PREFIXES = (
    "完成", "结束", "finish", "done", "complete", "end",
    "立即体验", "立即启动", "启动应用", "启动", "launch",
)
# 永不点击（前缀匹配，优先级最高）
NEVER_PREFIXES = (
    "取消", "cancel", "quit", "退出", "abort", "中止", "中断",
    "返回", "上一步", "后退", "back",
    "不", "no", "not", "decline", "拒绝", "不同意", "不接受", "donot", "do not",
    "否",
    "跳过", "稍后", "以后", "推迟", "skip", "later", "remind",
    "浏览", "更改", "修改", "选择", "browse", "change", "choose",
    "自定义", "高级", "advanced", "custom", "option", "选项",
    "修复", "卸载", "移除", "删除", "repair", "uninstall", "remove", "delete",
    "关闭", "close",
)
# 任意位置出现即不点（强危险词子串兜底）
NEVER_SUBSTRINGS = (
    "取消", "cancel", "quit", "exit", "uninstall", "卸载", "decline", "拒绝",
    "skip", "跳过", "browse", "浏览", "删除", "remove",
)
# 窗口标题“长得像安装器”的词
INSTALLER_TITLE_WORDS = (
    "setup", "install", "wizard", "installation", "setupwizard",
    "安装", "向导", "协议", "许可", "agreement", "license", "licence",
    "欢迎", "welcome", "driver", "驱动", "printer", "打印",
    "finish", "complete", "完成", "extract", "解压", "目标", "destination",
    "update", "更新", "部署", "deploy",
)
# 勾选“接受协议”的控件文字
AGREE_PREFIXES = (
    "我接受", "我同意", "同意", "接受", "accept", "agree", "iagree", "iaccept",
)
# 页面文本命中这些 = 完成页（只有这时才允许点「完成/结束」）
COMPLETE_PAGE_WORDS = (
    "安装成功", "安装完成", "已完成", "成功安装", "恭喜",
    "completed", "successfully", "finished", "successful",
    "installation complete", "setup complete",
)
# 页面文本命中这些 = 出错/受阻（记录原因，停止点击，交由上层报失败）。
# 注意：不用“无法/不能”等过宽的词，避免把“卸载后将无法使用”这类说明误判为错误。
BLOCKER_PAGE_WORDS = (
    "安装失败", "卸载失败", "失败", "错误", "error", "fail",
    "拒绝", "denied",
    "无法安装", "无法继续", "无法完成", "无法访问", "无法启动", "无法卸载",
    "不能安装", "不能继续", "cannot install", "cannot continue", "cannot complete",
    "未检测到", "未找到", "未连接打印机", "不存在", "not found", "not detected",
    "需要管理员", "需要以管理员", "administrator", "权限不足",
    "内存不足", "磁盘空间不足", "insufficient",
)


def _normalize(s):
    out = []
    for ch in s:
        if ch in "&<>._-·…（）() \t\r\n":
            continue
        out.append(ch.lower())
    return "".join(out)


def classify_text(text):
    """返回 'click' / 'never' / 'agree' / None"""
    norm = _normalize(text)
    if not norm:
        return None
    for k in NEVER_PREFIXES:
        if norm.startswith(k):
            return "never"
    for k in NEVER_SUBSTRINGS:
        if k in norm:
            return "never"
    for k in AGREE_PREFIXES:
        if norm.startswith(k):
            return "agree"
    for k in CLICK_PREFIXES:
        if norm.startswith(k):
            return "click"
    return None


def is_finish_text(text):
    norm = _normalize(text)
    if not norm:
        return False
    for k in FINISH_PREFIXES:
        if norm.startswith(k):
            return True
    return False


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------------- 进程 ----------------
class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_wchar * 260)]


def _snapshot_processes():
    procs = {}
    try:
        TH32CS_SNAPPROCESS = 0x00000002
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap in (0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return procs
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            while True:
                procs[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile.lower())
                if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
        kernel32.CloseHandle(snap)
    except Exception:
        pass
    return procs


def process_tree(root_pid):
    """返回 root_pid 及其所有后代 pid（含 root 本身）"""
    procs = _snapshot_processes()
    pids = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _name) in procs.items():
            if ppid in pids and pid not in pids:
                pids.add(pid)
                changed = True
    return pids


def msiexec_pids():
    return {pid for pid, (_ppid, name) in _snapshot_processes().items() if name == "msiexec.exe"}


def pid_running(pid):
    """判断指定进程是否仍在运行（打不开句柄时保守视为仍在运行）"""
    try:
        SYNCHRONIZE = 0x00100000
        WAIT_TIMEOUT = 0x0102
        h = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not h:
            return True
        try:
            return kernel32.WaitForSingleObject(h, 0) == WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return True


# ---------------- 窗口 ----------------
class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


# Win32 API 原型：64 位下必须显式声明，否则 HWND 会被截断为 32 位（这正是旧版
# 在 64 位系统上 SendMessage/BM_CLICK 经常失效的原因之一）
try:
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindowEnabled.argtypes = [wintypes.HWND]
    user32.IsWindowEnabled.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_void_p]
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetDlgCtrlID.argtypes = [wintypes.HWND]
    user32.GetDlgCtrlID.restype = ctypes.c_int
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
except Exception:
    pass  # 声明失败时退回默认行为（32 位环境一般无需声明）


def snapshot_windows():
    """当前所有可见顶层窗口句柄集合（安装程序启动前调用作为基线）"""
    out = set()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd):
            out.add(int(hwnd))
        return True

    user32.EnumWindows(cb, 0)
    return out


def _window_text(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _rect(hwnd):
    r = RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return (r.left, r.top, r.right, r.bottom)
    return None


def _enum_top_windows():
    """返回 [(hwnd, pid, title)]（仅可见顶层窗口）"""
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((int(hwnd), pid.value, _window_text(hwnd)))
        return True

    user32.EnumWindows(cb, 0)
    return out


def _enum_children(hwnd):
    """返回 [(hwnd, class, text)]（全部后代控件）"""
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _lp):
        out.append((int(h), _class_name(h), _window_text(h)))
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def _looks_installer(title, hwnd=None):
    """标题命中安装器关键词，或窗口尺寸像对话框向导"""
    t = (title or "").strip()
    low = t.lower()
    if low and any(w in low for w in INSTALLER_TITLE_WORDS):
        return True
    if not t and hwnd:
        return False
    r = _rect(hwnd) if hwnd else None
    if r:
        w, h = r[2] - r[0], r[3] - r[1]
        # 典型向导窗口：宽 350~1400、高 220~900
        if 350 <= w <= 1400 and 220 <= h <= 900:
            return True
    return False


def _window_pid_ok(hwnd, pid, tree_pids, baseline, state):
    """窗口是否属于本轮安装的目标窗口集合"""
    if pid == state.get("own_pid"):
        return False
    if pid in tree_pids:
        return True
    # 启动后新出现的窗口：只有“长得像安装器”的才算（避免点错用户自己的窗口）
    if hwnd not in baseline and _looks_installer(_window_text(hwnd), hwnd):
        return True
    return False


def _point_owned_by(x, y, hwnd):
    """坐标 (x,y) 处的窗口是否就是 hwnd 或其子窗口（避免点到被遮挡的其它窗口）"""
    try:
        GA_ROOT = 2

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        w = user32.WindowFromPoint(POINT(int(x), int(y)))
        if not w:
            return False
        root = user32.GetAncestor(w, GA_ROOT)
        return int(root) == int(hwnd)
    except Exception:
        return True  # 无法判断时保守放行（仍只点安全控件）


def _mouse_click_center(hwnd):
    """鼠标点击控件中心（点击前校验坐标点确实属于目标窗口）"""
    try:
        r = _rect(hwnd)
        if not r:
            return False
        cx = (r[0] + r[2]) // 2
        cy = (r[1] + r[3]) // 2
        if not _point_owned_by(cx, cy, hwnd):
            return False
        user32.SetCursorPos(cx, cy)
        time.sleep(0.03)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return True
    except Exception:
        return False


def _click_control(hwnd, cls):
    """单次点击（不同时用两种方式，避免双击跳页）"""
    if cls == "Button":  # 标准按钮走消息点击，最可靠且不抢鼠标
        user32.SendMessageW(hwnd, BM_CLICK, 0, 0)
        return True
    return _mouse_click_center(hwnd)  # 自绘/皮肤按钮走真实鼠标点击


def _press_enter(hwnd):
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)


def _default_button(dialog_hwnd, children):
    """通过 DM_GETDEFID 找到对话框的默认按钮（向导里默认按钮=下一步/安装/确定）"""
    try:
        DM_GETDEFID = 0x0400  # WM_USER
        res = user32.SendMessageW(dialog_hwnd, DM_GETDEFID, 0, 0)
        if (res >> 16) == 0x534B:  # DC_HASDEFID
            ctrl_id = res & 0xFFFF
            for ch, cls, _text in children:
                if cls in ("Button", "TButton", "TBitBtn"):
                    if user32.GetDlgCtrlID(ch) == ctrl_id:
                        return ch, cls
    except Exception:
        pass
    return None


def _looks_like_path(text):
    t = text.strip()
    if not t:
        return False
    if ":" in t and ("\\" in t or "/" in t):
        return True
    low = t.lower()
    return low.startswith(("c:", "d:", "e:", "f:")) or low.startswith("%") or low.startswith("\\\\")


# ---------------- UIA（UI Automation，可选增强层） ----------------
UIA_ControlTypePropertyId = 30003
UIA_NamePropertyId = 30005
UIA_IsEnabledPropertyId = 30009
UIA_BoundingRectanglePropertyId = 30001
UIA_NativeWindowHandlePropertyId = 30020
UIA_InvokePatternId = 10000
UIA_ValuePatternId = 10002
UIA_TogglePatternId = 10015
UIA_LegacyIAccessiblePatternId = 10018
UIA_ButtonControlTypeId = 50000
UIA_CheckBoxControlTypeId = 50002
UIA_ComboBoxControlTypeId = 50003
UIA_EditControlTypeId = 50004
UIA_RadioButtonControlTypeId = 50013
_TreeScope_Descendants = 4

_uia_cache = {"v": None, "tried": False}


def _get_uia():
    """获取 IUIAutomation 实例（失败返回 None，自动降级为纯 Win32）"""
    if not _uia_cache["tried"]:
        _uia_cache["tried"] = True
        try:
            import pythoncom
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
            from win32com.client import Dispatch
            try:
                obj = Dispatch("UIAutomationClient.CUIAutomation")
            except Exception:
                obj = Dispatch("{FF48DBA4-60EF-4201-AA87-54103EEF594E}")
            _uia_cache["v"] = obj
        except Exception:
            _uia_cache["v"] = None
    return _uia_cache["v"]


def _uia_prop(el, pid):
    try:
        return el.GetCurrentPropertyValue(pid)
    except Exception:
        return None


def _uia_rect_center(el):
    """UIA 元素包围盒中心坐标 (x, y)"""
    try:
        r = _uia_prop(el, UIA_BoundingRectanglePropertyId)
        if r is None:
            return None
        if isinstance(r, (tuple, list)) and len(r) == 4:
            l, t, w, h = [float(v) for v in r]
        else:
            l = float(getattr(r, "left", 0) or 0)
            t = float(getattr(r, "top", 0) or 0)
            w = float(getattr(r, "width", 0) or 0)
            h = float(getattr(r, "height", 0) or 0)
        if w <= 0 or h <= 0:
            return None
        return int(l + w / 2), int(t + h / 2)
    except Exception:
        return None


def _uia_invoke(el):
    """UIA 点击：InvokePattern → LegacyIAccessible.DoDefaultAction → 坐标点击"""
    try:
        pat = el.GetCurrentPattern(UIA_InvokePatternId)
        if pat:
            pat.Invoke()
            return True
    except Exception:
        pass
    try:
        pat = el.GetCurrentPattern(UIA_LegacyIAccessiblePatternId)
        if pat:
            pat.DoDefaultAction()
            return True
    except Exception:
        pass
    try:
        hwnd = _uia_prop(el, UIA_NativeWindowHandlePropertyId)
        if hwnd and _mouse_click_center(int(hwnd)):
            return True
    except Exception:
        pass
    return False


def _uia_toggle_on(el):
    """把勾选类控件设为选中态（未选中才操作），返回是否操作了"""
    try:
        pat = el.GetCurrentPattern(UIA_TogglePatternId)
        if not pat:
            return False
        try:
            state = pat.CurrentToggleState
        except Exception:
            return False
        if state == 0:  # ToggleState_Off
            pat.Toggle()
            return True
    except Exception:
        pass
    return False


def _uia_set_value(el, text):
    try:
        pat = el.GetCurrentPattern(UIA_ValuePatternId)
        if not pat:
            return False
        pat.SetValue(text)
        return True
    except Exception:
        pass
    return False


def _uia_scan(hwnd, state, install_dir, page_complete=False):
    """对窗口做一次 UIA 扫描并执行一个动作（按钮/勾选/填目录）。返回 (动作描述, 是否完成页按钮)"""
    auto = _get_uia()
    if auto is None:
        return None, False
    try:
        root = auto.ElementFromHandle(int(hwnd))
        if root is None:
            return None, False
    except Exception:
        return None, False

    # 1) 按钮：找第一个“可点且未点过”的安全按钮（完成类按钮仅完成页可点）
    try:
        cond = auto.CreatePropertyCondition(UIA_ControlTypePropertyId, UIA_ButtonControlTypeId)
        arr = root.FindAll(_TreeScope_Descendants, cond)
        for i in range(int(arr.Length or 0)):
            el = arr.GetElement(i)
            name = (_uia_prop(el, UIA_NamePropertyId) or "").strip()
            if not name:
                continue
            kind = classify_text(name)
            if kind not in ("click", "agree"):
                continue
            if not _uia_prop(el, UIA_IsEnabledPropertyId):
                continue
            if is_finish_text(name) and not page_complete:
                continue  # 完成类按钮：只有完成页才允许点
            key = (hwnd, "uia", name)
            if key in state.setdefault("uia_clicked", set()):
                continue
            state["uia_clicked"].add(key)
            if _uia_invoke(el):
                finish = is_finish_text(name)
                return ("点击「%s」（UIA）" % name), finish
            pt = _uia_rect_center(el)
            if pt and _point_owned_by(pt[0], pt[1], hwnd):
                user32.SetCursorPos(pt[0], pt[1])
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                finish = is_finish_text(name)
                return ("点击「%s」（UIA 坐标）" % name), finish
    except Exception:
        pass

    # 2) 勾选协议（CheckBox/RadioButton，仅“同意/接受”类）
    try:
        for ctype in (UIA_CheckBoxControlTypeId, UIA_RadioButtonControlTypeId):
            cond = auto.CreatePropertyCondition(UIA_ControlTypePropertyId, ctype)
            arr = root.FindAll(_TreeScope_Descendants, cond)
            for i in range(int(arr.Length or 0)):
                el = arr.GetElement(i)
                name = (_uia_prop(el, UIA_NamePropertyId) or "").strip()
                if not name:
                    continue
                if classify_text(name) != "agree":
                    continue
                key = (hwnd, "uia_toggle", name)
                if key in state.setdefault("uia_toggled", set()):
                    continue
                state["uia_toggled"].add(key)
                if _uia_toggle_on(el):
                    return "勾选「%s」（UIA）" % name, False
    except Exception:
        pass

    # 3) 填安装目录（Edit/ComboBox，且当前值像路径或名称含目录关键词）
    if install_dir:
        try:
            for ctype in (UIA_EditControlTypeId, UIA_ComboBoxControlTypeId):
                cond = auto.CreatePropertyCondition(UIA_ControlTypePropertyId, ctype)
                arr = root.FindAll(_TreeScope_Descendants, cond)
                for i in range(int(arr.Length or 0)):
                    el = arr.GetElement(i)
                    name = (_uia_prop(el, UIA_NamePropertyId) or "")
                    val = ""
                    try:
                        pat = el.GetCurrentPattern(UIA_ValuePatternId)
                        if pat:
                            val = pat.CurrentValue or ""
                    except Exception:
                        pass
                    low = (name + " " + val).lower()
                    is_dirish = any(w in low for w in ("目录", "路径", "folder", "directory",
                                                       "path", "位置", "location", "安装到"))
                    if not (is_dirish or _looks_like_path(val)):
                        continue
                    key = (hwnd, "uia_fill", name or val)
                    if key in state.setdefault("uia_filled", set()):
                        continue
                    state["uia_filled"].add(key)
                    if _uia_set_value(el, install_dir):
                        return "安装目录已设为 %s（UIA）" % install_dir, False
        except Exception:
            pass
    return None, False


# ---------------- 主扫描 ----------------
def _page_text(hwnd, children, title):
    """当前页面的可见文本（窗口标题 + 可见的 Static 标签文本）"""
    parts = [title or ""]
    try:
        for ch, cls, text in children:
            if cls not in ("Static", "TStaticText", "TLabel", "Text", "LinkWindow",
                           "SysLink", "RICHEDIT", "RichEdit20W"):
                continue
            if not user32.IsWindowVisible(ch):
                continue
            t = (text or "").strip()
            if t:
                parts.append(t)
    except Exception:
        pass
    return " ".join(parts)


def _page_state(hwnd, children, title):
    """返回 'blocker' / 'complete' / 'normal'

    - 短标签（≤80 字）或窗口标题命中“失败/错误”类关键词 → blocker（出错页，不再点击）
    - 短标签或标题命中“安装完成/成功”类关键词 → complete（完成页，允许点「完成」）
    - 其余 → normal（正常向导页）
    """
    title_low = (title or "").lower()

    def scan(text, low):
        for w in BLOCKER_PAGE_WORDS:
            if w in low:
                return "blocker"
        for w in COMPLETE_PAGE_WORDS:
            if w in low:
                return "complete"
        return None

    r = scan(title, title_low)
    if r:
        return r
    try:
        for ch, cls, text in children:
            if cls not in ("Static", "TStaticText", "TLabel", "Text", "LinkWindow",
                           "SysLink", "RICHEDIT", "RichEdit20W"):
                continue
            if not user32.IsWindowVisible(ch):
                continue
            t = (text or "").strip()
            if not t or len(t) > 80:  # 长篇说明文字不算状态提示
                continue
            r = scan(t, t.lower())
            if r:
                return r
    except Exception:
        pass
    return "normal"


def autoclick_once(root_pids, install_dir, state):
    """扫描一次安装程序窗口并执行动作。

    返回 (动作描述列表, 是否点击了“完成/结束”类按钮)
    state 内保存各窗口/控件的操作记录，防止重复点击。
    """
    actions = []
    saw_finish = False
    baseline = state.get("baseline", set())
    tree_pids = set(root_pids)  # 只认本轮安装的进程树，不碰系统里其它 msiexec/安装进程
    now = time.time()
    win_rec = state.setdefault("windows", {})

    for hwnd, pid, title in _enum_top_windows():
        if not _window_pid_ok(hwnd, pid, tree_pids, baseline, state):
            continue
        # 注意：不做“标题命中黑名单即整窗跳过”——卸载类程序窗口标题常含“卸载”，
        # 但窗口里的「下一步/是/完成」按钮仍应正常点击（黑名单只作用于按钮文本）。

        rec = win_rec.setdefault(hwnd, {"clicked": set(), "toggled": set(),
                                        "filled": set(), "last_action": 0.0,
                                        "last_enter": 0.0, "uia_last": 0.0})
        did = False

        # ---- 第 1 层：Win32 标准控件 ----
        try:
            children = _enum_children(hwnd)
        except Exception:
            children = []

        buttons = [(ch, cls, text) for ch, cls, text in children
                   if cls in ("Button", "TButton", "TBitBtn")]

        # 翻页检测：属性表向导在同一窗口内翻页（下一步按钮是同一个控件）。
        # 页面内容变化 → 重置该窗口的点击记录，允许在新页面再次点击「下一步」等。
        sig_parts = []
        for ch, cls, text in children:
            try:
                if not user32.IsWindowVisible(ch):
                    continue
                en = 1 if user32.IsWindowEnabled(ch) else 0
            except Exception:
                en = 1
            sig_parts.append((cls, text, en))
        page_sig = tuple(sig_parts)
        if "page_sig" in rec and rec["page_sig"] != page_sig:
            rec["clicked"].clear()
            rec["toggled"].clear()
            rec["filled"].clear()
        rec["page_sig"] = page_sig

        # 页面状态判断：出错页 → 停止点击并记录原因；完成页 → 才允许点「完成」
        page_state = _page_state(hwnd, children, title)
        if page_state == "blocker":
            state["blocker"] = _page_text(hwnd, children, title).strip() or title
            continue
        page_complete = (page_state == "complete")
        if page_complete:
            state["saw_completion_text"] = True

        # 1a) 安装目录编辑框（先填目录，再点按钮翻页，避免填完前页面已跳走）
        if not did and install_dir:
            has_browse = any(
                bc in ("Button", "TButton") and
                ("browse" in _normalize(bt) or "浏览" in bt or "更改" in bt)
                for b, bc, bt in buttons)
            for ch, cls, text in children:
                if cls not in ("Edit", "TEdit", "ComboBox", "TComboBox"):
                    continue
                if ch in rec["filled"]:
                    continue
                is_path = _looks_like_path(text)
                is_empty_with_browse = (not text.strip()) and has_browse
                if is_path or is_empty_with_browse:
                    rec["filled"].add(ch)
                    buf = ctypes.c_wchar_p(install_dir)
                    user32.SendMessageW(ch, WM_SETTEXT, 0,
                                        ctypes.cast(buf, ctypes.c_void_p).value or 0)
                    actions.append("安装目录已设为 %s" % install_dir)
                    did = True
                    break

        # 1b) 非 Button 类的协议复选框（少数安装器用 CheckBox 类）
        if not did:
            for ch, cls, text in children:
                if cls not in ("CheckBox", "TCheckBox", "RadioButton"):
                    continue
                if classify_text(text) != "agree":
                    continue
                if ch in rec["toggled"]:
                    continue
                try:
                    if not user32.IsWindowEnabled(ch):
                        continue
                except Exception:
                    pass
                try:
                    if user32.SendMessageW(ch, BM_GETCHECK, 0, 0) == BST_CHECKED:
                        rec["toggled"].add(ch)
                        continue
                except Exception:
                    pass
                rec["toggled"].add(ch)
                _click_control(ch, cls)
                actions.append("勾选「%s」" % text.strip())
                did = True
                break

        # 1c) 文字匹配的按钮（含“接受协议”类按钮/单选）
        for ch, cls, text in buttons:
            if did:
                break
            kind = classify_text(text)
            if kind not in ("click", "agree"):
                continue
            if ch in rec["clicked"]:
                continue
            try:
                if not user32.IsWindowEnabled(ch):
                    continue  # 禁用按钮：不点也不记录，等它变为可用再点
            except Exception:
                pass
            # 单选/复选类协议控件：已选中就不再点
            if kind == "agree" and cls == "Button":
                try:
                    if user32.SendMessageW(ch, BM_GETCHECK, 0, 0) == BST_CHECKED:
                        rec["clicked"].add(ch)
                        continue
                except Exception:
                    pass
            # 「完成/结束」类按钮：只在完成页才允许点击（防止没装完就点“完成”退出向导）
            if is_finish_text(text) and not page_complete:
                continue
            rec["clicked"].add(ch)
            if _click_control(ch, cls):
                actions.append("点击「%s」" % text.strip())
                if is_finish_text(text):
                    saw_finish = True
                did = True
                break

        # ---- 第 2 层：UIA（DirectUI / WPF / 自绘界面） ----
        if not did:
            if now - rec["uia_last"] >= 1.2:
                rec["uia_last"] = now
                msg, finish = _uia_scan(hwnd, state, install_dir, page_complete)
                if msg:
                    actions.append(msg)
                    if finish:
                        saw_finish = True
                    did = True

        # ---- 第 3 层：默认按钮（向导的下一步/安装/确定；完成类同样受完成页约束） ----
        if not did and buttons and now - rec["last_action"] > 2.0:
            db = _default_button(hwnd, children)
            if db:
                ch, cls = db
                dtext = ""
                for b, bc, bt in buttons:
                    if b == ch:
                        dtext = bt
                        break
                try:
                    if not user32.IsWindowEnabled(ch):
                        db = None
                except Exception:
                    pass
                if db and (is_finish_text(dtext) and not page_complete):
                    db = None  # 默认按钮是「完成」但不在完成页 → 不点
                if db and (hwnd, ch, "def") not in rec["clicked"]:
                    rec["clicked"].add((hwnd, ch, "def"))
                    _click_control(ch, cls)
                    actions.append("点击默认按钮")
                    did = True

        # ---- 第 4 层：回车兜底（仅当窗口没有任何按钮时，避免误触发默认的完成/取消） ----
        if not did and not buttons and now - rec["last_action"] > 2.5 \
                and now - rec["last_enter"] > 3.0:
            rec["last_enter"] = now
            _press_enter(hwnd)
            actions.append("发送回车（默认按钮）")
            did = True

        if did:
            rec["last_action"] = now
            state["last_action"] = now
            break  # 每轮只推进一个窗口，避免多窗口同时乱点

    return actions, saw_finish


def visible_tree_windows(root_pids, baseline, state):
    """当前属于安装目标的可见顶层窗口 [(hwnd, pid, title)]（供上层做“无进展”判定）"""
    tree_pids = set(root_pids)
    return [(h, p, t) for h, p, t in _enum_top_windows()
            if _window_pid_ok(h, p, tree_pids, baseline, state)]


def scan_blocker(root_pids, state):
    """扫描目标窗口的“出错/受阻”提示文本（失败/未检测到/需要管理员等），
    返回提示文本；没有则返回 None。供回放与自动点击模式共用。"""
    baseline = state.get("baseline", set())
    tree_pids = set(root_pids)
    for hwnd, pid, title in _enum_top_windows():
        if not _window_pid_ok(hwnd, pid, tree_pids, baseline, state):
            continue
        try:
            children = _enum_children(hwnd)
        except Exception:
            children = []
        if _page_state(hwnd, children, title) == "blocker":
            return _page_text(hwnd, children, title).strip() or title
    return None
