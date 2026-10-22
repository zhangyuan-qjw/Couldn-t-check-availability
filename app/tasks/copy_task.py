# -*- coding: utf-8 -*-
"""任务：复制文件（文件夹 / 压缩包，可先复制压缩包再解压）"""
import datetime
import os
import shutil
import time
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
    """把文件夹或压缩包复制到目标文件夹（压缩包可先复制再解压）"""
    key = "copy_archive"
    title = "复制文件"
    icon = "📦"
    order = 10

    def default_cfg(self):
        return {"enabled": True, "source": "", "dest": "", "overwrite": True, "backup": True,
                "copy_then_extract": False, "delete_archive_after": True}

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

        # “先复制压缩包再解压”模式（加速：单文件复制远快于逐个小文件复制）
        if cfg.get("copy_then_extract", False) and os.path.isfile(src) and _fsutil.is_archive(src):
            try:
                os.makedirs(dst, exist_ok=True)
            except Exception as e:
                raise TaskError(f"无法创建目标文件夹：{util.error_hint(e)}")
            zip_name = os.path.basename(src)
            target_zip = os.path.join(dst, zip_name)
            if os.path.normcase(os.path.abspath(target_zip)) == os.path.normcase(src_abs):
                raise TaskError("源压缩包已在目标文件夹内，无需复制")
            if os.path.exists(target_zip):
                if backup_dir:
                    try:
                        os.makedirs(backup_dir, exist_ok=True)
                        bp = os.path.join(backup_dir, zip_name)
                        shutil.copy2(target_zip, bp)
                        log(f"已备份目标处同名压缩包：{bp}")
                    except Exception as e:
                        log(f"备份压缩包失败（继续覆盖）：{util.error_hint(e)}")
                log(f"目标处已有同名压缩包，直接覆盖：{target_zip}")
            # 第一步：复制压缩包本体
            t0 = time.time()
            try:
                shutil.copy2(src, target_zip)
            except Exception as e:
                raise TaskError(f"复制压缩包失败：{util.error_hint(e)}")
            size_mb = os.path.getsize(target_zip) / 1024.0 / 1024.0
            log(f"第一步完成：已复制压缩包 {zip_name}（{size_mb:.1f} MB，{time.time() - t0:.1f} 秒）")
            # 第二步：解压目标处的压缩包到目标文件夹（覆盖模式，可备份被覆盖文件）
            try:
                count, backed = _fsutil.copy_dir_or_archive(
                    target_zip, dst, backup_dir=backup_dir, log=log)
            except TaskError:
                raise
            except Exception as e:
                raise TaskError(f"解压失败：{util.error_hint(e)}")
            msg = f"第二步完成：压缩包已解压，共 {count} 个文件"
            if backed:
                msg += f"，已备份被覆盖文件 {backed} 个"
            log(msg)
            # 第三步：按需删除目标处的压缩包副本
            if cfg.get("delete_archive_after", True):
                try:
                    os.remove(target_zip)
                    log(f"已删除目标处的压缩包副本：{zip_name}")
                except OSError as e:
                    log(f"删除压缩包副本失败（可手动删除）：{util.error_hint(e)}")
            log("复制+解压完成")
            return

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
            "c2e": BooleanVar(value=False), "del": BooleanVar(value=True),
            "src": StringVar(), "dst": StringVar(),
        }
        ui.hint(tab, "文件夹或压缩包直接覆盖复制").grid(
            row=0, column=0, columnspan=5, padx=16, pady=(14, 4), sticky="w")
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
        ui.check(tab, self.v["c2e"],
                 "解压").grid(
            row=4, column=0, columnspan=5, padx=(16, 6), pady=8, sticky="w")
        ui.check(tab, self.v["del"], "删除压缩包副本").grid(
            row=5, column=0, columnspan=5, padx=(16, 6), pady=8, sticky="w")

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", True)))
        self.v["bk"].set(bool(cfg.get("backup", True)))
        self.v["c2e"].set(bool(cfg.get("copy_then_extract", False)))
        self.v["del"].set(bool(cfg.get("delete_archive_after", True)))
        self.v["src"].set(cfg.get("source", ""))
        self.v["dst"].set(cfg.get("dest", ""))

    def collect_ui(self, cfg):
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["backup"] = bool(self.v["bk"].get())
        cfg["copy_then_extract"] = bool(self.v["c2e"].get())
        cfg["delete_archive_after"] = bool(self.v["del"].get())
        cfg["source"] = self.v["src"].get().strip()
        cfg["dest"] = self.v["dst"].get().strip()
        cfg["overwrite"] = True
