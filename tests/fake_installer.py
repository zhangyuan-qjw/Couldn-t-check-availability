# -*- coding: utf-8 -*-
"""模拟安装向导（纯 Win32 标准控件版）——仅供自检部署助手的“自动点击安装”逻辑。

不安装任何东西、不改动系统。流程：
  英文欢迎页 -> 英文协议页(必须勾选 I accept 才能下一步) -> 中文目录页(编辑框) ->
  中文就绪页 -> 进度页(1.5 秒后启用「完成」) -> 点击完成退出。

标记文件（写在环境变量 FAKE_MARKER 指定目录，默认本文件目录）：
  fake_install_done.txt        —— 正常走到完成页（内容 = 目录页填写的安装目录）
  fake_install_cancelled.txt   —— 被点了「取消/Cancel」（自检要求：绝不应出现）
"""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MARKER = os.environ.get("FAKE_MARKER") or os.path.dirname(os.path.abspath(__file__))

CLS = "TestSetupWizardCls"
TITLE = "TestSetup 安装向导 (Simulated Setup)"

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_TABSTOP = 0x00010000
WS_BORDER = 0x00800000
BS_PUSHBUTTON = 0x00000000
BS_AUTORADIOBUTTON = 0x00000009
ES_AUTOHSCROLL = 0x0080
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
BM_SETCHECK = 0x00F1
BM_GETCHECK = 0x00F0
BST_CHECKED = 0x0001
IDC_ARROW = 32512
COLOR_BTNFACE = 16

ID_NEXT = 1
ID_CANCEL = 2
ID_BACK = 3
ID_ACCEPT = 4
ID_DECLINE = 5
ID_EDIT = 6
ID_BROWSE = 7
ID_FINISH = 8

PAGE = 0
ACCEPT_HWND = None
EDIT_HWND = None
FINISH_HWND = None
PROGRESS_LABEL = None
QUITTING = False
CAPTURED_DIR = ""


def write(name, content=""):
    try:
        with open(os.path.join(MARKER, name), "w", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        pass


def add_label(parent, text, x, y, w, h):
    return user32.CreateWindowExW(0, "Static", text, WS_CHILD | WS_VISIBLE,
                                  x, y, w, h, parent, None, None, None)


def add_button(parent, text, x, y, w, h, cid):
    return user32.CreateWindowExW(0, "Button", text,
                                  WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                                  x, y, w, h, parent, cid, None, None)


def add_radio(parent, text, x, y, w, h, cid, checked=False):
    hwnd = user32.CreateWindowExW(0, "Button", text,
                                  WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTORADIOBUTTON,
                                  x, y, w, h, parent, cid, None, None)
    if checked:
        user32.SendMessageW(hwnd, BM_SETCHECK, BST_CHECKED, 0)
    return hwnd


def add_edit(parent, text, x, y, w, h):
    return user32.CreateWindowExW(0, "Edit", text,
                                  WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_BORDER | ES_AUTOHSCROLL,
                                  x, y, w, h, parent, None, None, None)


def build_page(hwnd):
    global ACCEPT_HWND, EDIT_HWND, FINISH_HWND, PROGRESS_LABEL
    if PAGE == 0:
        add_label(hwnd, "Welcome to the TestSetup Wizard", 30, 20, 430, 30)
        add_label(hwnd, "This simulated wizard only verifies auto-click.", 30, 62, 430, 20)
        add_button(hwnd, "Cancel", 300, 225, 90, 30, ID_CANCEL)
        add_button(hwnd, "Next >", 400, 225, 90, 30, ID_NEXT)
    elif PAGE == 1:
        add_label(hwnd, "End User License Agreement", 30, 20, 430, 30)
        ACCEPT_HWND = add_radio(hwnd, "I accept the license agreement", 30, 70, 300, 22, ID_ACCEPT)
        add_radio(hwnd, "I do not accept the agreement", 30, 102, 300, 22, ID_DECLINE)
        add_button(hwnd, "Cancel", 300, 225, 90, 30, ID_CANCEL)
        add_button(hwnd, "Next >", 400, 225, 90, 30, ID_NEXT)
    elif PAGE == 2:
        add_label(hwnd, "选择安装位置 (Destination Folder)", 30, 20, 430, 30)
        add_label(hwnd, "安装目录:", 30, 76, 80, 22)
        EDIT_HWND = add_edit(hwnd, "", 112, 72, 262, 24)
        add_button(hwnd, "浏览...", 384, 70, 86, 28, ID_BROWSE)
        add_button(hwnd, "取消", 300, 225, 90, 30, ID_CANCEL)
        add_button(hwnd, "上一步(&B) <", 206, 225, 90, 30, ID_BACK)
        add_button(hwnd, "下一步(&N) >", 400, 225, 90, 30, ID_NEXT)
    elif PAGE == 3:
        add_label(hwnd, "准备安装 (Ready to Install)", 30, 20, 430, 30)
        add_label(hwnd, "Click Install to begin.", 30, 72, 300, 22)
        add_button(hwnd, "取消", 300, 225, 90, 30, ID_CANCEL)
        add_button(hwnd, "上一步(&B) <", 206, 225, 90, 30, ID_BACK)
        add_button(hwnd, "开始安装(&I)", 400, 225, 90, 30, ID_NEXT)
    elif PAGE == 4:
        PROGRESS_LABEL = add_label(hwnd, "正在安装… (Installing...)", 30, 20, 430, 30)
        FINISH_HWND = add_button(hwnd, "完成(&F)", 400, 225, 90, 30, ID_FINISH)
        user32.EnableWindow(FINISH_HWND, False)
        user32.SetTimer(hwnd, 1, 1500, None)


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


def handle_cmd(hwnd, cid):
    global PAGE, QUITTING
    write("fake_install_cmd.txt", "cid=%s" % cid)  # 诊断：记录收到的控件命令
    try:
        _handle_cmd(hwnd, cid)
    except Exception as e:  # 诊断：任何异常都写错误标记
        write("fake_install_error.txt", repr(e))


def _handle_cmd(hwnd, cid):
    global PAGE, QUITTING, CAPTURED_DIR
    if cid == ID_CANCEL:
        write("fake_install_cancelled.txt")
        QUITTING = True
        user32.DestroyWindow(hwnd)
        return
    if cid == ID_BACK:
        PAGE = max(PAGE - 1, 0)
        user32.DestroyWindow(hwnd)
        create_page()
        return
    if cid == ID_BROWSE:
        return  # “浏览…”不做任何事（点击器不应点它）
    if cid == ID_NEXT:
        if PAGE == 1:
            # 必须勾选“I accept”才能继续（测试协议勾选逻辑）
            if ACCEPT_HWND and user32.SendMessageW(ACCEPT_HWND, BM_GETCHECK, 0, 0) != BST_CHECKED:
                user32.MessageBeep(0)
                return
        if PAGE == 2:
            # 离开目录页前捕获安装目录（验证自动填目录是否生效）
            try:
                buf = ctypes.create_unicode_buffer(512)
                if EDIT_HWND:
                    user32.SendMessageW(EDIT_HWND, WM_GETTEXT, 512,
                                        ctypes.cast(buf, ctypes.c_void_p).value or 0)
                CAPTURED_DIR = buf.value.strip()
            except Exception:
                CAPTURED_DIR = ""
        PAGE += 1
        user32.DestroyWindow(hwnd)
        create_page()
        return
    if cid == ID_FINISH:
        write("fake_install_done.txt", CAPTURED_DIR)
        QUITTING = True
        user32.DestroyWindow(hwnd)
        return


@WNDPROC
def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_COMMAND:
        handle_cmd(hwnd, wparam & 0xFFFF)
        return 0
    if msg == WM_TIMER:
        if FINISH_HWND:
            user32.EnableWindow(FINISH_HWND, True)
        if PROGRESS_LABEL:  # 进度完成 → 显示“安装完成”文本（模拟真实完成页）
            _txt = ctypes.c_wchar_p("安装完成 (Installation Complete)")
            user32.SendMessageW(PROGRESS_LABEL, WM_SETTEXT, 0,
                                ctypes.cast(_txt, ctypes.c_void_p).value or 0)
        return 0
    if msg == WM_DESTROY:
        if QUITTING:  # 翻页销毁窗口时不退出进程
            user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def create_page():
    hwnd = user32.CreateWindowExW(
        0, CLS, TITLE,
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_VISIBLE,
        120, 120, 520, 300, None, None, None, None)
    build_page(hwnd)
    return hwnd


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]


# Win32 API 原型（64 位下必须显式声明，否则 HWND 会被截断为 32 位）
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.DefWindowProcW.restype = wintypes.LPARAM
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = wintypes.LPARAM
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.MessageBeep.argtypes = [wintypes.UINT]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


def main():
    wc = WNDCLASSW()
    wc.lpfnWndProc = wnd_proc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.hCursor = user32.LoadCursorW(None, ctypes.cast(ctypes.c_void_p(IDC_ARROW), wintypes.LPCWSTR))
    wc.hbrBackground = COLOR_BTNFACE + 1
    wc.lpszClassName = CLS
    if not user32.RegisterClassW(ctypes.byref(wc)):
        return 1
    create_page()
    msg = MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
