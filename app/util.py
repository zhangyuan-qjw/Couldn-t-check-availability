# -*- coding: utf-8 -*-
"""通用工具：路径解析、消息框、错误提示翻译"""
import os
import re
import sys

from . import APP_NAME

_DIR_NAME = "DeployTool"


def is_frozen():
    """是否运行在 PyInstaller 打包后的 exe 中"""
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """程序所在目录（开发模式为项目根目录）"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir(sub):
    """数据子目录：优先放在程序旁边（便携），不可写则回退到 %APPDATA%"""
    candidate = os.path.join(app_dir(), sub)
    try:
        os.makedirs(candidate, exist_ok=True)
        probe = os.path.join(candidate, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return candidate
    except OSError:
        fallback = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), _DIR_NAME, sub)
        os.makedirs(fallback, exist_ok=True)
        return fallback


def configs_dir():
    return data_dir("configs")


def logs_dir():
    return data_dir("logs")


def backups_dir():
    return data_dir("backups")


def scripts_dir():
    """操作录制脚本目录（录制回放功能）"""
    return data_dir("scripts")


def sanitize_filename(name):
    """去掉文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(name)).strip().strip(".")
    return name or "未命名"


def get_desktop_dir():
    """获取桌面目录（兼容 OneDrive 重定向）；后台线程调用时自动初始化 COM"""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()  # 后台线程必须显式初始化 COM，否则 Dispatch 报 0x800401F0
        shell = None
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            p = shell.Namespace(0x10).Self.Path
        finally:
            del shell
            pythoncom.CoUninitialize()
        if p and os.path.isdir(p):
            return p
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def get_startup_dir(common=False):
    """开机自启“启动文件夹”路径"""
    if common:
        base = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "StartUp")
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def error_hint(exc):
    """把 Windows / pywin32 错误翻译成可读的中文提示"""
    try:
        import pywintypes
        if isinstance(exc, pywintypes.error):
            hints = {
                5: "拒绝访问（权限不足）。请尝试【以管理员身份运行】本工具。",
                2: "系统找不到指定的文件或打印机。",
                123: "名称无效，请检查是否包含非法字符。",
                1801: "打印机名称无效。",
                1802: "打印机不存在。",
            }
            code = getattr(exc, "winerror", 0)
            if code in hints:
                return f"{hints[code]}（错误码 {code}）"
    except Exception:
        pass
    s = str(exc)
    low = s.lower()
    if "access is denied" in low or "拒绝访问" in s or "error(5," in low.replace(" ", ""):
        return "权限不足，请尝试【以管理员身份运行】本工具。"
    return s


def show_message(title, text, kind="info"):
    """无控制台环境下也能弹出消息（tkinter 失败时回退 Win32 MessageBox）"""
    try:
        import tkinter.messagebox as mb
        fn = {"info": mb.showinfo, "error": mb.showerror, "warn": mb.showwarning}.get(kind, mb.showinfo)
        fn(title, text)
    except Exception:
        try:
            import ctypes
            flags = 0x10 if kind == "error" else 0x40
            ctypes.windll.user32.MessageBoxW(0, str(text), str(title), flags)
        except Exception:
            try:
                sys.stderr.write(f"[{title}] {text}\n")
            except Exception:
                pass
