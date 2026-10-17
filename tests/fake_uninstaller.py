# -*- coding: utf-8 -*-
"""模拟卸载向导（纯 Win32 标准控件）——用于自检“操作录制与回放”。

流程：
  确认页：Static “确定要卸载打印机驱动吗？” + [是(&Y)] [否(&N)]
  进度页：Static “正在卸载…” + [完成(&F)]（禁用 1.2 秒后启用，
          并把文字改为 “卸载完成 (Uninstallation Complete)”）
标记文件（写 FAKE_MARKER 目录）：
  fake_uninstall_done.txt      —— 正常完成（点了「是」并走到「完成」）
  fake_uninstall_cancelled.txt —— 点了「否」
"""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MARKER = os.environ.get("FAKE_MARKER") or os.path.dirname(os.path.abspath(__file__))

CLS = "FakeUninstallCls"
TITLE = "打印机驱动程序的卸载 (Simulated Uninstall)"

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_TABSTOP = 0x00010000
BS_PUSHBUTTON = 0x00000000
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_SETTEXT = 0x000C
IDC_ARROW = 32512
COLOR_BTNFACE = 16

ID_YES = 1
ID_NO = 2
ID_FINISH = 3

PAGE = 0
FINISH_HWND = None
PROGRESS_LABEL = None
QUITTING = False


def write(name):
    try:
        with open(os.path.join(MARKER, name), "w", encoding="utf-8") as f:
            f.write("ok")
    except OSError:
        pass


def add_label(parent, text, x, y, w, h):
    return user32.CreateWindowExW(0, "Static", text, WS_CHILD | WS_VISIBLE,
                                  x, y, w, h, parent, None, None, None)


def add_button(parent, text, x, y, w, h, cid):
    return user32.CreateWindowExW(0, "Button", text,
                                  WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                                  x, y, w, h, parent, cid, None, None)


def build_page(hwnd):
    global FINISH_HWND, PROGRESS_LABEL
    if PAGE == 0:
        add_label(hwnd, "确定要卸载打印机驱动吗？", 30, 20, 430, 30)
        add_label(hwnd, "卸载后打印机将无法使用。", 30, 62, 430, 20)
        add_button(hwnd, "否(&N)", 300, 220, 90, 30, ID_NO)
        add_button(hwnd, "是(&Y)", 400, 220, 90, 30, ID_YES)
    elif PAGE == 1:
        PROGRESS_LABEL = add_label(hwnd, "正在卸载… (Uninstalling...)", 30, 20, 430, 30)
        FINISH_HWND = add_button(hwnd, "完成(&F)", 400, 220, 90, 30, ID_FINISH)
        user32.EnableWindow(FINISH_HWND, False)
        user32.SetTimer(hwnd, 1, 1200, None)


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


def handle_cmd(hwnd, cid):
    global PAGE, QUITTING
    try:
        _handle_cmd(hwnd, cid)
    except Exception as e:
        write("fake_uninstall_error.txt")
        try:
            with open(os.path.join(MARKER, "fake_uninstall_error.txt"), "a",
                      encoding="utf-8") as f:
                f.write(repr(e))
        except OSError:
            pass


def _handle_cmd(hwnd, cid):
    global PAGE, QUITTING
    if cid == ID_NO:
        write("fake_uninstall_cancelled.txt")
        QUITTING = True
        user32.DestroyWindow(hwnd)
        return
    if cid == ID_YES:
        PAGE = 1
        user32.DestroyWindow(hwnd)
        create_page()
        return
    if cid == ID_FINISH:
        write("fake_uninstall_done.txt")
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
        if PROGRESS_LABEL:
            _txt = ctypes.c_wchar_p("卸载完成 (Uninstallation Complete)")
            user32.SendMessageW(PROGRESS_LABEL, WM_SETTEXT, 0,
                                ctypes.cast(_txt, ctypes.c_void_p).value or 0)
        return 0
    if msg == WM_DESTROY:
        if QUITTING:
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
