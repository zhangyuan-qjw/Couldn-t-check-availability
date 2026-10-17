# -*- coding: utf-8 -*-
"""编译检查所有源码（兼容 Python 3.8）"""
import os
import py_compile
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = [
    "main.py",
    "app/__init__.py", "app/core.py", "app/gui.py", "app/config_store.py",
    "app/util.py", "app/ui_helpers.py", "app/headless.py",
    "app/tasks/__init__.py", "app/tasks/_autoclick.py", "app/tasks/driver_task.py",
    "app/tasks/printer_task.py", "app/tasks/copy_task.py",
    "app/tasks/shortcut_task.py", "app/tasks/extra_tasks.py", "app/tasks/_fsutil.py",
    "app/tasks/_recorder.py", "app/tasks/record_task.py",
    "tests/fake_installer.py", "tests/test_autoclick.py",
    "tests/fake_uninstaller.py", "tests/test_record_replay.py",
]
bad = []
for f in files:
    p = os.path.join(ROOT, f)
    try:
        py_compile.compile(p, doraise=True)
        print("OK  %s" % f)
    except Exception as e:
        bad.append((f, str(e)))
        print("ERR %s -> %s" % (f, e))
if bad:
    print("FAILED")
    sys.exit(1)
print("ALL COMPILE OK on %s" % sys.version.split()[0])
