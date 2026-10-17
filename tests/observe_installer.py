# -*- coding: utf-8 -*-
"""观察 Install.exe 的窗口链（只记录，不点击任何控件）。

用法：python tests/observe_installer.py <安装程序路径> [观察秒数]
输出：每 0.8 秒扫描一次，打印进程树中（或新出现且疑似安装器）的顶层窗口，
     以及每个窗口的子控件（类名/文本/是否启用）。
"""
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.tasks import _autoclick  # noqa: E402

user32 = _autoclick.user32


def main():
    exe = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    redirect_tmp = "--no-tmp-redirect" not in sys.argv
    env = dict(os.environ)
    if redirect_tmp:
        ws_tmp = os.path.join(ROOT, "tmp")
        os.makedirs(ws_tmp, exist_ok=True)
        env["TMP"] = ws_tmp
        env["TEMP"] = ws_tmp
    print("launching: %s (tmp_redirect=%s)" % (exe, redirect_tmp))
    p = subprocess.Popen([exe], cwd=os.path.dirname(exe), env=env)
    baseline = _autoclick.snapshot_windows()
    seen = set()
    end = time.time() + seconds
    while time.time() < end:
        tree = _autoclick.process_tree(p.pid)
        procs = _autoclick._snapshot_processes()
        names = {pid: procs.get(pid, ("", "?"))[1] for pid in tree if pid in procs}
        for h, pid, title in _autoclick._enum_top_windows():
            if pid in tree or (h not in baseline and _autoclick._looks_installer(title, h)):
                if h not in seen:
                    seen.add(h)
                    print("[NEW WIN] hwnd=%s pid=%s exe=%s title=%r cls=%s" %
                          (h, pid, names.get(pid, "?"), title, _autoclick._class_name(h)))
                    kids = _autoclick._enum_children(h)
                    print("    children: %d" % len(kids))
                    for ch, cls, text in kids[:50]:
                        try:
                            enabled = bool(user32.IsWindowEnabled(ch))
                        except Exception:
                            enabled = "?"
                        print("      %-16s %-30r enabled=%s" % (cls, text, enabled))
        if p.poll() is not None:
            print("root exited, code=%s" % p.poll())
        time.sleep(0.8)
    print("final poll:", p.poll())
    if p.poll() is None:
        print("(installer chain still running, terminating...)")
        try:
            p.terminate()
            p.wait(5)
        except Exception:
            pass


if __name__ == "__main__":
    main()
