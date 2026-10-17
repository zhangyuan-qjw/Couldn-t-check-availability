# -*- coding: utf-8 -*-
"""任务：复制文件夹/压缩包、复制替换单个文件"""
import datetime
import os
import shutil
from tkinter import BooleanVar, StringVar

from ..core import BaseTask, TaskError, register
from .. import util
from .. import ui_helpers as ui
from . import _fsutil


def _backup_dir(suffix):
    return os.path.join(util.backups_dir(),
                        datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + suffix)


@register
class FolderArchiveTask(BaseTask):
    """把文件夹或压缩包复制到指定文件夹"""
    key = "copy_archive"
    title = "复制文件夹"
    icon = "📦"
    order = 10

    def default_cfg(self):
        return {"enabled": True, "source": "", "dest": "", "overwrite": True, "backup": True}

    def run(self, cfg, log):
        src = (cfg.get("source") or "").strip()
        dst = (cfg.get("dest") or "").strip()
        if not src:
            raise TaskError("未指定源文件夹/压缩包")
        if not dst:
            raise TaskError("未指定目标文件夹")
        src_abs = os.path.abspath(src)
        dst_abs = os.path.abspath(dst)
        if os.path.normcase(src_abs) == os.path.normcase(dst_abs):
            raise TaskError("源与目标不能是同一路径")
        if os.path.isdir(src):
            try:
                if os.path.commonpath([src_abs, dst_abs]) == src_abs:
                    raise TaskError("目标文件夹不能位于源文件夹内部，否则会无限复制")
            except ValueError:
                pass
        backup_dir = None
        if cfg.get("backup", True):
            backup_dir = _backup_dir("_copy")
        try:
            count, backed = _fsutil.copy_dir_or_archive(src, dst, backup_dir=backup_dir, log=log)
        except TaskError:
            raise
        except Exception as e:
            raise TaskError(f"复制失败：{util.error_hint(e)}")
        msg = f"复制完成：共 {count} 个文件"
        if backed:
            msg += f"，已备份被覆盖文件 {backed} 个"
        log(msg)

    # ---------------- 界面 ----------------
    def build_tab(self, tab, app):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_columnconfigure(2, weight=1)
        self.v = {
            "en": BooleanVar(value=True), "bk": BooleanVar(value=True),
            "src": StringVar(), "dst": StringVar(),
        }
        ui.hint(tab, "把整个文件夹（或 zip / tar / 7z 压缩包）复制到目标文件夹，"
                     "已存在的同名文件将被直接覆盖。").grid(
            row=0, column=0, columnspan=5, padx=16, pady=(16, 4), sticky="w")
        ui.label(tab, "源（文件夹/压缩包）").grid(row=1, column=0, padx=(16, 6), pady=8, sticky="w")
        ui.entry(tab, self.v["src"], placeholder="选择文件夹或压缩包").grid(
            row=1, column=1, columnspan=2, padx=6, pady=8, sticky="ew")
        ui.button(tab, "选文件夹", lambda: ui.browse_dir(self.v["src"], "选择源文件夹")).grid(
            row=1, column=3, padx=(6, 3), pady=8)
        ui.button(tab, "选压缩包", lambda: ui.browse_file(
            self.v["src"], "选择压缩包",
            [("压缩包", "*.zip *.tar *.gz *.tgz *.bz2 *.xz *.7z"), ("所有文件", "*.*")])).grid(
            row=1, column=4, padx=(3, 16), pady=8)
        ui.label(tab, "目标文件夹").grid(row=2, column=0, padx=(16, 6), pady=8, sticky="w")
        ui.entry(tab, self.v["dst"], placeholder="文件将复制到此文件夹").grid(
            row=2, column=1, columnspan=2, padx=6, pady=8, sticky="ew")
        ui.button(tab, "浏览…", lambda: ui.browse_dir(self.v["dst"], "选择目标文件夹")).grid(
            row=2, column=3, columnspan=2, padx=(6, 16), pady=8, sticky="w")
        ui.check(tab, self.v["en"], "启用此任务").grid(
            row=3, column=0, columnspan=2, padx=(16, 6), pady=8, sticky="w")
        ui.check(tab, self.v["bk"], "覆盖前自动备份被替换文件").grid(
            row=3, column=2, columnspan=3, padx=6, pady=8, sticky="w")

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", True)))
        self.v["bk"].set(bool(cfg.get("backup", True)))
        self.v["src"].set(cfg.get("source", ""))
        self.v["dst"].set(cfg.get("dest", ""))

    def collect_ui(self, cfg):
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["backup"] = bool(self.v["bk"].get())
        cfg["source"] = self.v["src"].get().strip()
        cfg["dest"] = self.v["dst"].get().strip()
        cfg["overwrite"] = True


@register
class FileReplaceTask(BaseTask):
    """把单个文件复制/替换到指定文件夹（替换不弹框）"""
    key = "copy_file"
    title = "复制文件"
    icon = "📄"
    order = 20

    def default_cfg(self):
        return {"enabled": True, "source": "", "dest_folder": "", "backup": True}

    def run(self, cfg, log):
        src = (cfg.get("source") or "").strip()
        dst_dir = (cfg.get("dest_folder") or "").strip()
        if not src:
            raise TaskError("未指定要复制的文件")
        if not dst_dir:
            raise TaskError("未指定目标文件夹")
        if not os.path.isfile(src):
            raise TaskError(f"源文件不存在：{src}")
        try:
            os.makedirs(dst_dir, exist_ok=True)
        except Exception as e:
            raise TaskError(f"无法创建目标文件夹：{util.error_hint(e)}")
        target = os.path.join(dst_dir, os.path.basename(src))
        if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(target)):
            raise TaskError("源文件与目标文件是同一个文件，无需复制")
        if os.path.exists(target):
            if os.path.isdir(target):
                raise TaskError(f"目标处存在同名文件夹，无法替换为文件：{target}")
            if cfg.get("backup", True):
                bdir = _backup_dir("_file")
                os.makedirs(bdir, exist_ok=True)
                bp = os.path.join(bdir, os.path.basename(target))
                shutil.copy2(target, bp)
                log(f"已备份原文件：{bp}")
            log(f"目标文件已存在，直接替换（不弹框）：{target}")
        shutil.copy2(src, target)
        log(f"复制完成：{src} -> {target}")

    # ---------------- 界面 ----------------
    def build_tab(self, tab, app):
        tab.grid_columnconfigure(1, weight=1)
        self.v = {
            "en": BooleanVar(value=True), "bk": BooleanVar(value=True),
            "src": StringVar(), "dst": StringVar(),
        }
        ui.hint(tab, "把一个文件复制到指定文件夹；若目标已有同名文件则直接替换，全程不弹框。").grid(
            row=0, column=0, columnspan=3, padx=16, pady=(16, 4), sticky="w")
        ui.label(tab, "源文件").grid(row=1, column=0, padx=(16, 6), pady=8, sticky="w")
        ui.entry(tab, self.v["src"], placeholder="选择要复制/替换的文件").grid(
            row=1, column=1, padx=6, pady=8, sticky="ew")
        ui.button(tab, "浏览…", lambda: ui.browse_file(self.v["src"], "选择源文件")).grid(
            row=1, column=2, padx=(6, 16), pady=8)
        ui.label(tab, "目标文件夹").grid(row=2, column=0, padx=(16, 6), pady=8, sticky="w")
        ui.entry(tab, self.v["dst"], placeholder="文件将被放入此文件夹").grid(
            row=2, column=1, padx=6, pady=8, sticky="ew")
        ui.button(tab, "浏览…", lambda: ui.browse_dir(self.v["dst"], "选择目标文件夹")).grid(
            row=2, column=2, padx=(6, 16), pady=8)
        ui.check(tab, self.v["en"], "启用此任务").grid(
            row=3, column=0, columnspan=2, padx=(16, 6), pady=8, sticky="w")
        ui.check(tab, self.v["bk"], "替换前自动备份原文件").grid(
            row=3, column=2, padx=6, pady=8, sticky="w")

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", True)))
        self.v["bk"].set(bool(cfg.get("backup", True)))
        self.v["src"].set(cfg.get("source", ""))
        self.v["dst"].set(cfg.get("dest_folder", ""))

    def collect_ui(self, cfg):
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["backup"] = bool(self.v["bk"].get())
        cfg["source"] = self.v["src"].get().strip()
        cfg["dest_folder"] = self.v["dst"].get().strip()
