# -*- coding: utf-8 -*-
"""冒烟测试：用打包后的 exe 执行一个仅含“复制”任务的配置，验证 exe 可启动、引擎可运行。"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

try:  # GBK 控制台兼容
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGETS = [
    ("win10-onefile", os.path.join(WS, "dist", "部署助手.exe"), os.path.join(WS, "dist")),
    ("win7-onefile", os.path.join(WS, "dist_win7", "部署助手_Win7.exe"), os.path.join(WS, "dist_win7")),
    ("win7-onedir", os.path.join(WS, "dist_win7", "部署助手_Win7", "部署助手_Win7.exe"),
     os.path.join(WS, "dist_win7", "部署助手_Win7")),
]


def main():
    src = os.path.join(WS, "smoke_src")
    if os.path.isdir(src):
        shutil.rmtree(src, ignore_errors=True)
    os.makedirs(os.path.join(src, "sub"))
    with open(os.path.join(src, "a.txt"), "w", encoding="utf-8") as f:
        f.write("hello")
    with open(os.path.join(src, "sub", "b.txt"), "w", encoding="utf-8") as f:
        f.write("world")

    all_ok = True
    for label, exe, exedir in TARGETS:
        if not os.path.isfile(exe):
            print("MISSING EXE: %s" % exe)
            all_ok = False
            continue
        dst = os.path.join(WS, "smoke_dst", label)
        shutil.rmtree(dst, ignore_errors=True)
        cfgdir = os.path.join(exedir, "configs")
        os.makedirs(cfgdir, exist_ok=True)
        cfg = {
            "name": "冒烟测试",
            "meta": {"version": 1},
            "tasks": {
                "copy_archive": {"enabled": True, "source": src, "dest": dst,
                                 "overwrite": True, "backup": False},
                "shortcut": {"enabled": False},
                "remove_autostart": {"enabled": False},
                "driver_install": {"enabled": False},
                "printer": {"enabled": False},
                "quick_launch": {"enabled": False},
            },
        }
        cfgpath = os.path.join(cfgdir, "冒烟测试.json")
        with open(cfgpath, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        logdir = os.path.join(exedir, "logs")
        before = set(glob.glob(os.path.join(logdir, "run_*.log")))
        print("===== %s =====" % label)
        # 沙箱/受限环境下把 TMP 指到工作区，保证 onefile 自解压可用（用户机器上不需要）
        env = dict(os.environ)
        ws_tmp = os.path.join(WS, "tmp")
        os.makedirs(ws_tmp, exist_ok=True)
        env["TMP"] = ws_tmp
        env["TEMP"] = ws_tmp
        proc = subprocess.Popen([exe, "-r", "冒烟测试"], env=env)
        deadline = time.time() + 40
        newlog = None
        copied = False
        while time.time() < deadline:
            time.sleep(1)
            logs = sorted(set(glob.glob(os.path.join(logdir, "run_*.log"))) - before)
            if logs:
                newlog = logs[-1]
            copied = os.path.isfile(os.path.join(dst, "a.txt")) and \
                os.path.isfile(os.path.join(dst, "sub", "b.txt"))
            if copied:
                break
        alive = proc.poll() is None
        if newlog:
            try:
                with open(newlog, "r", encoding="utf-8") as f:
                    content = f.read().strip()
            except OSError:
                content = "(log unreadable)"
        else:
            content = "(no log file)"
        print("log: %s" % content.replace("\n", "\n     "))
        print("copied=%s alive=%s" % (copied, alive))
        ok = copied and ("完成" in content or "成功" in content)
        print("RESULT: %s" % ("OK ✓" if ok else "FAIL ✗"))
        if alive:
            try:
                proc.terminate()
                proc.wait(5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if not ok:
            all_ok = False
    print("SMOKE ALL OK" if all_ok else "SMOKE HAS FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
