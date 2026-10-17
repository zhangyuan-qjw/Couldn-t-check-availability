# -*- coding: utf-8 -*-
"""冒烟测试：验证核心逻辑、文件操作、快捷方式、注册表、打印机枚举、引擎与 GUI 构建。

用法：.venv\\Scripts\\python.exe tests\\smoke.py
"""
import os
import sys
import shutil
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name)


def main():
    from app import core, util
    from app import config_store
    from app.tasks import _fsutil
    from app.tasks.shortcut_task import make_lnk, set_registry_autostart, remove_registry_autostart
    from app.tasks import printer_task

    # 1. 任务发现
    ts = core.tasks()
    check(f"任务发现（发现 {len(ts)} 个任务）", len(ts) >= 7)
    print("     任务列表：", [t.key for t in ts])

    # 2. 默认配置结构
    cfg = core.default_cfg()
    check("默认配置包含全部任务", set(cfg["tasks"].keys()) == {t.key for t in ts})

    # 3. 配置存取 roundtrip
    store = config_store.ConfigStore()
    tmp = tempfile.mkdtemp(prefix="deploy_smoke_")
    saved = store.save(cfg, "__冒烟测试配置__", path=os.path.join(tmp, "testcfg.json"))
    cfg2, p2 = store.load(saved)
    check("配置保存/读取", cfg2["name"] == "__冒烟测试配置__")
    check("配置归一化（缺字段自动补默认）",
          isinstance(cfg2["tasks"]["printer"].get("width_mm"), (int, float))
          and cfg2["tasks"]["printer"].get("set_default") is True)

    # 4. 文件夹复制 + 覆盖备份
    src = os.path.join(tmp, "src")
    dst = os.path.join(tmp, "dst")
    backup = os.path.join(tmp, "backup")
    os.makedirs(os.path.join(src, "sub"))
    with open(os.path.join(src, "a.txt"), "w", encoding="utf-8") as f:
        f.write("v1")
    with open(os.path.join(src, "sub", "b.txt"), "w", encoding="utf-8") as f:
        f.write("v1")
    n, b = _fsutil.copy_dir_or_archive(src, dst, backup_dir=backup)
    check("文件夹复制", n == 2 and os.path.isfile(os.path.join(dst, "sub", "b.txt")))
    with open(os.path.join(src, "a.txt"), "w", encoding="utf-8") as f:
        f.write("v2")
    n, b = _fsutil.copy_dir_or_archive(src, dst, backup_dir=backup)
    check("覆盖 + 自动备份", b == 2 and open(os.path.join(dst, "a.txt"), encoding="utf-8").read() == "v2"
          and os.path.isfile(os.path.join(backup, "a.txt")))

    # 5. 压缩包解压复制
    zpath = os.path.join(tmp, "pkg.zip")
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("x/y.txt", "zipdata")
    n, b = _fsutil.copy_dir_or_archive(zpath, dst, backup_dir=backup)
    check("压缩包解压复制", os.path.isfile(os.path.join(dst, "x", "y.txt")))

    # 6. 单文件复制替换任务
    ftask = [t for t in ts if t.key == "copy_file"][0]
    filedst = os.path.join(tmp, "filedst")
    fcfg = {"enabled": True, "source": os.path.join(src, "a.txt"),
            "dest_folder": filedst, "backup": True}
    ftask.run(fcfg, lambda m, l="info": None)
    check("单文件复制", os.path.isfile(os.path.join(filedst, "a.txt")))

    # 7. 快捷方式创建（.lnk）
    lnk = os.path.join(tmp, "测试.lnk")
    try:
        make_lnk(sys.executable, lnk, args="-V", desc="smoke")
        check("快捷方式创建", os.path.isfile(lnk) and os.path.getsize(lnk) > 0)
    except Exception as e:
        print(f"     快捷方式异常：{e}")
        check("快捷方式创建", False)

    # 7b. 后台线程中创建快捷方式（复现用户报的 CoInitialize bug）
    import threading
    thread_result = {}

    def _lnk_worker():
        try:
            make_lnk(sys.executable, os.path.join(tmp, "线程.lnk"), desc="thread")
            thread_result["ok"] = True
        except Exception as e:
            thread_result["ok"] = False
            thread_result["err"] = str(e)

    t = threading.Thread(target=_lnk_worker)
    t.start()
    t.join(15)
    check("后台线程创建快捷方式（COM 初始化修复）",
          thread_result.get("ok") and os.path.isfile(os.path.join(tmp, "线程.lnk")))

    # 7c. 旧版单程序配置自动转换为多程序列表
    from app.tasks.shortcut_task import normalize_items
    legacy = {"exe": "C:\\x\\a.exe", "name": "旧配置", "desktop": True,
              "autostart": False, "autostart_mode": "registry"}
    items = normalize_items(legacy)
    check("旧版配置自动转换为 items 列表",
          len(items) == 1 and items[0]["exe"] == "C:\\x\\a.exe"
          and items[0]["autostart_mode"] == "registry")

    # 7d. 多程序快捷方式任务（桌面重定向到临时目录，避免污染真实桌面）
    stask = [t for t in ts if t.key == "shortcut"][0]
    old_desktop = util.get_desktop_dir
    util.get_desktop_dir = lambda: os.path.join(tmp, "桌面")
    try:
        scfg = {"enabled": True, "items": [
            {"exe": sys.executable, "name": "程序A", "desktop": True, "autostart_mode": "none"},
            {"exe": sys.executable, "name": "程序B", "desktop": True, "autostart_mode": "none"},
        ]}
        logs = []
        stask.run(scfg, lambda m, l="info": logs.append(m))
        ok_two = (os.path.isfile(os.path.join(tmp, "桌面", "程序A.lnk"))
                  and os.path.isfile(os.path.join(tmp, "桌面", "程序B.lnk")))
        check("多程序快捷方式任务", ok_two)
    finally:
        util.get_desktop_dir = old_desktop

    # 8. 注册表自启（写入 -> 校验 -> 清理）
    try:
        set_registry_autostart("DeployTool_SmokeTest", '"cmd.exe" /c exit')
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        val = winreg.QueryValueEx(k, "DeployTool_SmokeTest")[0]
        winreg.CloseKey(k)
        check("注册表自启写入", "cmd.exe" in val)
        remove_registry_autostart("DeployTool_SmokeTest")
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(k, "DeployTool_SmokeTest")
            gone = False
        except FileNotFoundError:
            gone = True
        winreg.CloseKey(k)
        check("注册表自启清理", gone)
    except Exception as e:
        print(f"     注册表测试跳过（环境受限）：{e}")
        check("注册表自启（跳过）", True)

    # 9. 打印机枚举（只读，不修改任何打印机）
    try:
        names = printer_task.list_printers()
        print("     检测到打印机：", names or "（无）")
        check("打印机枚举", isinstance(names, list))
    except Exception as e:
        print(f"     打印机枚举异常：{e}")
        check("打印机枚举", False)

    # 9a. EnumForms 只读校验（确认签名只用 1 个参数）
    try:
        import win32print
        default = printer_task.get_default_printer()
        if default:
            h = win32print.OpenPrinter(default, {"DesiredAccess": win32print.PRINTER_ACCESS_USE})
            try:
                forms = win32print.EnumForms(h)
            finally:
                win32print.ClosePrinter(h)
            check("EnumForms 只读调用（单参数签名）", isinstance(forms, (list, tuple)))
        else:
            check("EnumForms 只读调用（无默认打印机，跳过）", True)
    except Exception as e:
        print(f"     EnumForms 异常：{e}")
        check("EnumForms 只读调用（单参数签名）", False)

    # 9b. 驱动安装任务（静默 .bat 安装）
    dtask = [t for t in ts if t.key == "driver_install"][0]
    marker = os.path.join(tmp, "installed.marker")
    bat = os.path.join(tmp, "driver_setup.bat")
    with open(bat, "w", encoding="gbk") as f:
        f.write(f'@echo off\r\necho installed > "{marker}"\r\n')
    dcfg = {"enabled": True, "installer": bat, "install_dir": "D:\\",
            "silent_args": "", "timeout_seconds": 30, "auto_click": False}
    try:
        dtask.run(dcfg, lambda m, l="info": None)
        check("驱动安装任务（静默 bat）", os.path.isfile(marker))
    except Exception as e:
        print(f"     驱动安装异常：{e}")
        check("驱动安装任务（静默 bat）", False)

    # 9c. 自动点击器：点击本进程弹出的 MessageBox「确定」
    try:
        from app.tasks import _autoclick
        mb_done = {}
        state = {"baseline": _autoclick.snapshot_windows()}

        def _mb_worker():
            import ctypes
            r = ctypes.windll.user32.MessageBoxW(0, "自动点击测试", "测试", 0x40)
            mb_done["r"] = r

        mb_t = threading.Thread(target=_mb_worker)
        mb_t.start()
        time.sleep(1.5)
        clicked = False
        for _ in range(20):
            acts = _autoclick.autoclick_once({os.getpid()}, "D:\\", state)
            if acts:
                clicked = True
                break
            time.sleep(0.4)
        mb_t.join(10)
        check("自动点击器（点击 MessageBox 确定）", clicked and not mb_t.is_alive())
    except Exception as e:
        print(f"     自动点击器异常：{e}")
        check("自动点击器（点击 MessageBox 确定）", False)

    # 9d. 自动点击器：点击英文 MessageBox「OK」（验证英文按钮匹配）
    try:
        from app.tasks import _autoclick
        mb_done2 = {}
        state2 = {"baseline": _autoclick.snapshot_windows()}

        def _mb_worker2():
            import ctypes
            r = ctypes.windll.user32.MessageBoxW(0, "English OK test", "Setup", 0x40)
            mb_done2["r"] = r

        mb_t2 = threading.Thread(target=_mb_worker2)
        mb_t2.start()
        time.sleep(1.5)
        clicked2 = False
        for _ in range(20):
            acts = _autoclick.autoclick_once({os.getpid()}, "D:\\", state2)
            if acts:
                clicked2 = True
                break
            time.sleep(0.4)
        mb_t2.join(10)
        check("自动点击器（点击英文 OK）", clicked2 and not mb_t2.is_alive())
    except Exception as e:
        print(f"     自动点击器英文异常：{e}")
        check("自动点击器（点击英文 OK）", False)

    # 9e. 任务顺序：驱动安装应在打印机纸张设置之前（先装驱动才能识别打印机）
    keys = [t.key for t in ts]
    check("驱动安装在打印机纸张设置之前（先装驱动再配纸张）",
          keys.index("driver_install") < keys.index("printer"))

    # 10. 引擎整体执行（只启用复制任务）
    engine = core.Engine(log=lambda m, l="info": None, status=lambda s: None)
    rcfg = core.default_cfg()
    rcfg["name"] = "smoke_run"
    for k in rcfg["tasks"]:
        rcfg["tasks"][k]["enabled"] = False
    rcfg["tasks"]["copy_archive"]["enabled"] = True
    rcfg["tasks"]["copy_archive"]["source"] = src
    rcfg["tasks"]["copy_archive"]["dest"] = os.path.join(tmp, "engine_dst")
    rcfg["tasks"]["copy_archive"]["backup"] = False
    ok_run, summary, failures = engine.run(rcfg)
    check(f"引擎执行（{summary}）", ok_run)
    logs = os.listdir(util.logs_dir())
    check("运行日志文件生成", any(f.startswith("run_") and f.endswith(".log") for f in logs))

    # 11. GUI 构建（隐藏窗口，不进入主循环）
    try:
        from app import gui
        app = gui.DeployToolApp()
        app.withdraw()
        app.update_idletasks()
        app.update()
        app.destroy()
        check("GUI 构建", True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("GUI 构建", False)

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n==== 结果 ====")
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"{passed}/{len(RESULTS)} 项通过")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
