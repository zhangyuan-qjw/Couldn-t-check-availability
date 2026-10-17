# -*- coding: utf-8 -*-
"""自检：自动点击安装能否走完模拟安装向导、且绝不点「取消」。

无任何系统改动：模拟向导只在临时目录写两个标记文件。
用法：
  python tests/test_autoclick.py [fake_installer.exe 路径]
返回码：0 = 通过，1 = 失败
"""
import os
import sys
import tempfile
import traceback

try:  # GBK 控制台打印中文/符号兼容
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.tasks import driver_task  # noqa: E402


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", "fake_installer.exe")
    if not os.path.isfile(exe):
        print("未找到模拟安装程序：%s" % exe)
        return 2

    marker = tempfile.mkdtemp(prefix="fakeinst_")
    os.environ["FAKE_MARKER"] = marker

    cfg = {"enabled": True, "installer": exe, "install_dir": "C:\\Temp\\FakeInst",
           "silent_args": "", "timeout_seconds": 60, "auto_click": True,
           "verify_path": ""}

    logs = []
    task_ok = False
    print("== 启动模拟安装向导，开始自动点击自检 ==")
    try:
        driver_task.DriverInstallTask().run(cfg, lambda m: logs.append(m))
        task_ok = True
    except Exception as e:
        print("任务抛出异常：%s" % e)
        traceback.print_exc()

    for line in logs:
        print("  | " + line)

    done = os.path.exists(os.path.join(marker, "fake_install_done.txt"))
    cancelled = os.path.exists(os.path.join(marker, "fake_install_cancelled.txt"))
    captured_dir = ""
    if done:
        try:
            with open(os.path.join(marker, "fake_install_done.txt"), "r", encoding="utf-8") as f:
                captured_dir = f.read().strip()
        except OSError:
            pass
    dir_ok = captured_dir.rstrip("\\") == "C:\\Temp\\FakeInst"
    print("== 结果 ==")
    print("任务正常返回       : %s" % task_ok)
    print("完成页标记(done)   : %s" % done)
    print("取消标记(cancelled): %s（必须为 False）" % cancelled)
    print("向导捕获的安装目录: %r（应为 C:\\Temp\\FakeInst）" % captured_dir)

    if done and not cancelled and dir_ok:
        print("AUTOCLICK TEST PASSED ✓")
        return 0
    print("AUTOCLICK TEST FAILED ✗")
    return 1


if __name__ == "__main__":
    sys.exit(main())
