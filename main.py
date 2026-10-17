# -*- coding: utf-8 -*-
"""部署助手 - 程序入口

用法：
  部署助手.exe                    打开配置界面
  部署助手.exe -r "配置名"         直接执行指定配置（弹进度窗口）
  部署助手.exe 某配置.json         直接执行该配置文件
  部署助手.exe --list             列出所有可用配置
"""
import sys


def _enable_dpi():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _setup_frozen_tcl():
    """打包后的 exe 中预设 Tcl/Tk 库路径，避免个别环境下找不到 init.tcl"""
    import os
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        tcl = os.path.join(base, "tcl", "tcl8.6")
        tk = os.path.join(base, "tcl", "tk8.6")
        if os.path.isdir(tcl):
            os.environ.setdefault("TCL_LIBRARY", tcl)
        if os.path.isdir(tk):
            os.environ.setdefault("TK_LIBRARY", tk)


def _install_excepthook():
    """未捕获异常写入崩溃日志，方便排查"""
    import datetime
    import os
    import traceback

    def hook(exc_type, exc, tb):
        try:
            from app import util
            log_dir = util.logs_dir()
            os.makedirs(log_dir, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(log_dir, f"crash_{stamp}.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
            util.show_message("程序出错",
                              f"程序发生未处理的错误，详情已保存到：\n{path}\n\n{exc}",
                              "error")
        except Exception:
            traceback.print_exception(exc_type, exc, tb)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def _parse_args(argv):
    run_arg = None
    show_list = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-r", "--run", "-c", "--config") and i + 1 < len(argv):
            run_arg = argv[i + 1]
            i += 2
            continue
        if a in ("--list", "-l"):
            show_list = True
            i += 1
            continue
        if a in ("-h", "--help", "/?"):
            from app import util
            util.show_message(
                "部署助手 - 用法",
                "用法：\n"
                "  部署助手.exe                    打开配置界面\n"
                "  部署助手.exe -r \"配置名\"         直接执行指定配置\n"
                "  部署助手.exe 配置文件.json        直接执行该配置文件\n"
                "  部署助手.exe --list              列出所有配置",
                "info")
            return None, None
        if not a.startswith("-"):
            run_arg = a
            i += 1
            continue
        i += 1
    return run_arg, show_list


def main():
    _enable_dpi()
    _setup_frozen_tcl()
    _install_excepthook()
    from app import util
    run_arg, show_list = _parse_args(sys.argv[1:])
    if run_arg is None and not show_list and sys.argv[1:]:
        return  # --help 已弹窗

    try:
        from app import gui  # noqa: F401
    except ImportError as e:
        util.show_message("缺少依赖",
                          f"缺少运行库，请先安装依赖：\n\npip install -r requirements.txt\n\n{e}",
                          "error")
        return

    if run_arg:
        from app import headless
        headless.run_config(run_arg)
    elif show_list:
        from app import headless
        headless.list_configs()
    else:
        from app import gui
        gui.run_gui()


if __name__ == "__main__":
    main()
