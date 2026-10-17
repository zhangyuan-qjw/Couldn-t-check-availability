# -*- coding: utf-8 -*-
"""验证 Win7(32位) 版 exe：启动后应出现「部署助手 v1.0.0」主窗口，随后优雅关闭"""
import ctypes
import os
import subprocess
import sys
import time

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
user32 = ctypes.windll.user32
TITLE = "部署助手 v1.0.0"
WM_CLOSE = 0x0010


def find_window():
    return user32.FindWindowW(None, TITLE)


def dump_error_dialog():
    found = {}

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _lp):
        n = user32.GetWindowTextLengthW(h)
        if n > 0:
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            if user32.IsWindowVisible(h):
                found[h] = b.value
        return True

    user32.EnumWindows(cb, 0)
    for h, t in found.items():
        if t == "Error":
            kids = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def cb2(h2, _lp2):
                m = user32.GetWindowTextLengthW(h2)
                if m > 0:
                    b2 = ctypes.create_unicode_buffer(m + 1)
                    user32.GetWindowTextW(h2, b2, m + 1)
                    kids.append(b2.value)
                return True

            user32.EnumChildWindows(h, cb2, 0)
            print("Error 弹窗内容：", kids)


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base, "dist_win7", "部署助手_Win7", "部署助手_Win7.exe")
    print("exe:", exe, "存在:", os.path.isfile(exe))
    # 沙箱环境的临时目录受限，把 TMP 指到可写目录（真实 Win7 机器无需此步）
    tmp = os.path.join(base, "win7build", "vtmp")
    os.makedirs(tmp, exist_ok=True)
    env = dict(os.environ)
    env["TMP"] = tmp
    env["TEMP"] = tmp
    proc = subprocess.Popen([exe], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    time.sleep(9)
    print("进程存活:", proc.poll() is None)
    hwnd = find_window()
    if hwnd:
        print("PASS: 主窗口「部署助手 v1.0.0」出现，Win7 版启动成功")
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(2)
        hwnd2 = find_window()
        print("关闭后窗口残留:", bool(hwnd2))
        if hwnd2:
            user32.PostMessageW(hwnd2, WM_CLOSE, 0, 0)
            time.sleep(2)
    else:
        print("FAIL: 主窗口未出现")
        dump_error_dialog()
    subprocess.run(["taskkill", "/F", "/IM", "部署助手_Win7.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("cleaned")


if __name__ == "__main__":
    main()
