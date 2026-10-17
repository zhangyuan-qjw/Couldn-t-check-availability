# -*- coding: utf-8 -*-
"""扩展任务：一键运行快捷方式"""
import os
import sys
from tkinter import BooleanVar, StringVar

from ..core import BaseTask, TaskError, register
from .. import util
from .. import ui_helpers as ui


def tool_command(config_name):
    """返回 (目标程序, 启动参数)：双击即可直接执行指定配置"""
    config_name = str(config_name).replace('"', "")
    if getattr(sys, "frozen", False):
        return sys.executable, f'-r "{config_name}"'
    main_py = os.path.join(util.app_dir(), "main.py")
    return sys.executable, f'"{main_py}" -r "{config_name}"'


@register
class QuickLaunchTask(BaseTask):
    """为当前配置生成“一键运行”快捷方式"""
    key = "quick_launch"
    title = "一键运行"
    icon = "🚀"
    order = 90

    def default_cfg(self):
        return {"enabled": False, "lnk_name": "", "desktop": True}

    def run(self, cfg, log):
        config_name = cfg.get("_config_name") or cfg.get("config_name") or ""
        if not config_name:
            raise TaskError("未获取到配置名称（请先保存配置）")
        name = util.sanitize_filename(
            (cfg.get("lnk_name") or "").strip() or f"{config_name}·一键运行")
        target, args = tool_command(config_name)
        dest = util.get_desktop_dir() if cfg.get("desktop", True) else util.get_startup_dir()
        try:
            os.makedirs(dest, exist_ok=True)
            p = os.path.join(dest, name + ".lnk")
            from .shortcut_task import make_lnk
            make_lnk(target, p, args=args, workdir=os.path.dirname(target),
                     desc=f"一键运行配置：{config_name}")
        except Exception as e:
            raise TaskError(f"创建一键运行快捷方式失败：{util.error_hint(e)}")
        log(f"已创建一键运行快捷方式：{p}")
        log(f"双击它即可自动执行配置「{config_name}」，无需打开界面")

    # ---------------- 界面 ----------------
    def build_tab(self, tab, app):
        tab.grid_columnconfigure(1, weight=1)
        self.v = {
            "en": BooleanVar(value=False), "desktop": BooleanVar(value=True),
            "name": StringVar(),
        }
        ui.hint(tab, "为“当前配置”生成一个快捷方式：双击它直接执行该配置，"
                     "无需打开界面再点按钮。").grid(
            row=0, column=0, columnspan=3, padx=16, pady=(16, 4), sticky="w")
        ui.check(tab, self.v["en"], "启用此任务（生成一键运行快捷方式）").grid(
            row=1, column=0, columnspan=3, padx=(16, 6), pady=8, sticky="w")
        ui.label(tab, "快捷方式名称").grid(row=2, column=0, padx=(16, 6), pady=8, sticky="w")
        ui.entry(tab, self.v["name"], placeholder="留空则为「配置名·一键运行」").grid(
            row=2, column=1, columnspan=2, padx=6, pady=8, sticky="ew")
        ui.check(tab, self.v["desktop"], "创建到桌面（取消勾选则创建到启动文件夹）").grid(
            row=3, column=0, columnspan=3, padx=(16, 6), pady=8, sticky="w")
        ui.hint(tab, "提示：先保存配置再执行，快捷方式才能指向正确的配置；"
                     "配置改名后需重新生成。").grid(
            row=4, column=0, columnspan=3, padx=16, pady=(2, 8), sticky="w")

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", False)))
        self.v["desktop"].set(bool(cfg.get("desktop", True)))
        self.v["name"].set(cfg.get("lnk_name", ""))

    def collect_ui(self, cfg):
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["desktop"] = bool(self.v["desktop"].get())
        cfg["lnk_name"] = self.v["name"].get().strip()
