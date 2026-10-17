# -*- coding: utf-8 -*-
"""任务：打印机纸张模板 + 默认纸张 + 测试打印"""
import datetime
import os
import tempfile
import threading
import time
from tkinter import BooleanVar, StringVar

import customtkinter as ctk

from ..core import BaseTask, TaskError, register
from .. import util
from .. import ui_helpers as ui

DMPAPER_USER = 256  # 自定义纸张


def list_printers():
    """读取本机可用的打印机列表（EnumPrinters 失败时用注册表兜底）"""
    import win32print
    names, seen = [], set()

    def add(name):
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    try:
        infos = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 1)
        for info in infos or []:
            try:
                add(info[2])
            except Exception:
                pass
    except Exception:
        pass

    if not names:
        # 兜底 1：本地打印机（注册表）
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SYSTEM\CurrentControlSet\Control\Print\Printers")
            i = 0
            while True:
                try:
                    add(winreg.EnumKey(key, i))
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass

    if not names:
        # 兜底 2：网络连接打印机（注册表，server,printer → \\server\printer）
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Printers\Connections")
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break
                add(sub.replace(",", "\\"))
            winreg.CloseKey(key)
        except OSError:
            pass

    return names


def get_default_printer():
    try:
        import win32print
        return win32print.GetDefaultPrinter()
    except Exception:
        return ""


def _open(printer, admin=False):
    import win32print
    access = win32print.PRINTER_ALL_ACCESS if admin else win32print.PRINTER_ACCESS_USE
    return win32print.OpenPrinter(printer, {"DesiredAccess": access})


def ensure_form(printer, name, width_mm, height_mm):
    """新增（或更新同名）纸张模板。返回 '新增' 或 '更新'。

    部分 Win7 驱动不支持 EnumForms（返回错误 1），因此这里对 EnumForms 失败做
    容错：直接尝试 AddForm，失败再退化为 SetForm（覆盖同名表单）。

    pywin32 的 win32print 签名：
      AddForm(hPrinter, FormInfo)        # FormInfo 为 dict
      SetForm(hPrinter, FormName, FormInfo)
    """
    import win32print
    if not name or not name.strip():
        raise TaskError("纸张名称不能为空")
    name = name.strip()[:31]  # CCHFORMNAME = 32
    size_x = int(round(width_mm * 1000))
    size_y = int(round(height_mm * 1000))
    form = {
        "Flags": 0,
        "Name": name,
        "Size": {"cx": size_x, "cy": size_y},
        "ImageableArea": {"left": 0, "top": 0, "right": size_x, "bottom": size_y},
    }

    h = _open(printer, admin=True)
    try:
        exists = False
        try:
            forms = win32print.EnumForms(h)
            exists = any(f[1] == name for f in forms)
        except Exception:
            exists = False  # Win7 部分驱动不支持枚举，忽略并直接尝试写入

        last_err = None
        if exists:
            try:
                win32print.SetForm(h, name, form)
                return "更新"
            except Exception as e:
                last_err = e
        try:
            win32print.AddForm(h, form)
            return "新增"
        except Exception as e:
            last_err = e
            # AddForm 失败：可能该名称已存在但没被枚举到 → 尝试 SetForm 覆盖
            try:
                win32print.SetForm(h, name, form)
                return "更新"
            except Exception as e2:
                last_err = e2
        raise TaskError(f"写入纸张模板失败：{util.error_hint(last_err)}")
    finally:
        win32print.ClosePrinter(h)


def set_default_form(printer, name):
    """把指定纸张模板设为该打印机的默认纸张"""
    import win32print
    import win32con
    h = _open(printer, admin=True)
    try:
        try:
            info = win32print.GetPrinter(h, 2)
        except Exception as e:
            raise TaskError(f"读取打印机设置失败：{util.error_hint(e)}")
        dm = info["pDevMode"]
        dm.PaperSize = DMPAPER_USER
        dm.FormName = name.strip()[:31]
        dm.Fields = (dm.Fields or 0) | win32con.DM_PAPERSIZE | win32con.DM_FORMNAME
        info["pDevMode"] = dm
        try:
            win32print.SetPrinter(h, 2, info, 0)
        except Exception as e:
            raise TaskError(f"设置默认纸张失败：{util.error_hint(e)}")
    finally:
        win32print.ClosePrinter(h)


def _set_default_printer(printer):
    import win32print
    if hasattr(win32print, "SetDefaultPrinter"):
        win32print.SetDefaultPrinter(printer)
        return
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows NT\CurrentVersion\Windows",
                         0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, "Device", 0, winreg.REG_SZ, f"{printer},winspool,Ne00:")
    finally:
        winreg.CloseKey(key)


def _enum_jobs(printer):
    import win32print
    h = _open(printer)
    try:
        return win32print.EnumJobs(h, 0, 99, 1)
    finally:
        win32print.ClosePrinter(h)


def _wait_jobs(printer, timeout):
    """等待打印队列出现任务"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if _enum_jobs(printer):
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _wait_drained(printer, timeout):
    """等待打印队列清空"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if not _enum_jobs(printer):
                return True
        except Exception:
            return True
        time.sleep(0.5)
    return False


def build_test_text(printer, form, width_mm, height_mm):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return "\r\n".join([
        "=" * 30,
        "部署助手 · 打印机测试页",
        f"打印机：{printer}",
        f"纸张模板：{form}",
        f"纸张尺寸：{width_mm} x {height_mm} mm",
        f"打印时间：{now}",
        "=" * 30,
        "",
        "如果您能看清以上内容，说明打印机与纸张设置正常。",
        "",
    ]) + "\f"


def print_test_page(printer, text, raw_mode=False, log=None):
    """打印测试页。

    默认走“系统打印”：临时把目标打印机设为默认 -> 调用系统打印 -> 等待入队 ->
    恢复原默认打印机。raw_mode 模式直接以 RAW 文本发送（适合部分标签机）。
    """
    import win32api
    import win32print
    log = log or (lambda m: None)

    if raw_mode:
        h = _open(printer)
        try:
            try:
                win32print.StartDocPrinter(h, 1, ("部署助手测试页", None, "RAW"))
                try:
                    win32print.StartPagePrinter(h)
                    win32print.WritePrinter(h, text.encode("gbk", "replace"))
                    win32print.EndPagePrinter(h)
                finally:
                    win32print.EndDocPrinter(h)
            except Exception as e:
                raise TaskError(f"RAW 打印失败：{util.error_hint(e)}")
        finally:
            win32print.ClosePrinter(h)
        return

    tmp = tempfile.mkdtemp(prefix="deploy_test_")
    path = os.path.join(tmp, "部署助手测试页.txt")
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(text.replace("\f", ""))
    old_default = get_default_printer()
    try:
        try:
            _set_default_printer(printer)
        except Exception as e:
            raise TaskError(f"临时切换默认打印机失败：{util.error_hint(e)}")
        log(f"已临时将默认打印机切到「{printer}」以发送测试页…")
        try:
            win32api.ShellExecute(0, "print", path, None, None, 0)
        except Exception as e:
            raise TaskError(f"调用系统打印失败：{util.error_hint(e)}")
        if not _wait_jobs(printer, 15):
            raise TaskError("测试页未能提交到打印队列，请检查打印机是否在线、是否有纸")
        log("测试页已进入打印队列，等待打印完成…")
        _wait_drained(printer, 60)
    finally:
        if old_default:
            try:
                _set_default_printer(old_default)
                log(f"已恢复默认打印机为「{old_default}」")
            except Exception:
                pass
        try:
            os.remove(path)
            os.rmdir(tmp)
        except OSError:
            pass


@register
class PrinterTask(BaseTask):
    """打印机纸张设置"""
    key = "printer"
    title = "打印机"
    icon = "🖨️"
    order = 40
    requires = ["driver_install"]  # 驱动安装失败时本任务自动跳过；顺序上驱动安装(38)先于本任务(40)

    def default_cfg(self):
        return {"enabled": True, "printer": "", "form_name": "",
                "width_mm": 100.0, "height_mm": 150.0,
                "set_default": True, "test_print": False, "raw_mode": False}

    def _wait_printer(self, printer, log, timeout=60):
        """等待指定打印机出现（刚装完驱动时系统注册打印机可能延迟）"""
        end = time.time() + timeout
        names = list_printers()
        if printer in names:
            return
        log(f"打印机「{printer}」暂未出现：等待驱动完成注册（最多 {timeout} 秒）…")
        while time.time() < end:
            time.sleep(2)
            try:
                names = list_printers()
            except Exception:
                names = []
            if printer in names:
                log(f"打印机「{printer}」已出现（等待 {int(time.time() - (end - timeout))} 秒）")
                return
        raise TaskError(f"未找到打印机「{printer}」。当前可用打印机：{', '.join(names) or '（无）'}\n"
                        f"请确认打印机已连接并开机，且打印驱动安装成功。")

    def run(self, cfg, log):
        printer = (cfg.get("printer") or "").strip()
        form = (cfg.get("form_name") or "").strip()
        if not printer:
            raise TaskError("未选择打印机")
        if not form:
            raise TaskError("未填写纸张名称")
        try:
            width = float(cfg.get("width_mm", 0))
            height = float(cfg.get("height_mm", 0))
        except (TypeError, ValueError):
            raise TaskError("纸张尺寸必须是数字（单位：毫米）")
        if width <= 0 or height <= 0 or width > 10000 or height > 10000:
            raise TaskError("纸张尺寸不合理，请输入 0~10000 之间的毫米数")
        if printer in list_printers():
            self._wait_printer(printer, log)
        else:
            log(f"打印机「{printer}」不在检测列表中：按手动输入的名称直接尝试操作…")
        action = ensure_form(printer, form, width, height)
        log(f"纸张模板「{form}」{action}成功（{width:g} x {height:g} mm）")
        if cfg.get("set_default", True):
            set_default_form(printer, form)
            log(f"已将「{form}」设为打印机「{printer}」的默认纸张")
        if cfg.get("test_print", False):
            log("开始打印测试纸…")
            self.print_test_now(cfg, log)
            log("测试纸打印完成")

    def print_test_now(self, cfg, log):
        """按当前设置打印测试纸（供任务与界面按钮共用）"""
        printer = (cfg.get("printer") or "").strip()
        form = (cfg.get("form_name") or "").strip() or "测试页"
        if not printer:
            raise TaskError("未选择打印机")
        try:
            width = float(cfg.get("width_mm", 100))
            height = float(cfg.get("height_mm", 150))
        except (TypeError, ValueError):
            raise TaskError("纸张尺寸必须是数字（单位：毫米）")
        if printer in list_printers():
            self._wait_printer(printer, log)
        else:
            log(f"打印机「{printer}」不在检测列表中：按手动输入的名称直接尝试…")
        text = build_test_text(printer, form, width, height)
        print_test_page(printer, text, raw_mode=bool(cfg.get("raw_mode", False)), log=log)

    # ---------------- 界面 ----------------
    def build_tab(self, tab, app):
        self.app = app
        tab.grid_columnconfigure(4, weight=1)
        self.v = {
            "en": BooleanVar(value=True), "setdefault": BooleanVar(value=True),
            "autotest": BooleanVar(value=False), "raw": BooleanVar(value=False),
            "printer": StringVar(), "form": StringVar(),
            "w": StringVar(value="100"), "h": StringVar(value="150"),
        }
        ui.hint(tab, "打印机可从下拉列表选择系统中的打印机，也可以直接手动输入打印机名称。"
                     "执行时为所选打印机添加纸张模板并设为默认纸张；"
                     "若同时启用驱动安装，本任务一定在驱动安装成功后执行，并自动等待打印机出现。").grid(
            row=0, column=0, columnspan=5, padx=16, pady=(14, 4), sticky="w")
        ui.label(tab, "打印机（可选/可输入）").grid(row=1, column=0, padx=(16, 6), pady=8, sticky="w")
        self.menu = ctk.CTkComboBox(tab, values=["（未检测到打印机）"],
                                    variable=self.v["printer"], width=360)
        self.menu.grid(row=1, column=1, columnspan=2, padx=6, pady=8, sticky="w")
        ui.button(tab, "🔄 刷新", self.refresh_printers).grid(row=1, column=3, padx=6, pady=8, sticky="w")
        self.def_label = ui.hint(tab, "")
        self.def_label.grid(row=2, column=1, columnspan=3, padx=6, sticky="w")
        ui.label(tab, "纸张名称").grid(row=3, column=0, padx=(16, 6), pady=8, sticky="w")
        ui.entry(tab, self.v["form"], placeholder="如：标签纸 100x150").grid(
            row=3, column=1, columnspan=3, padx=6, pady=8, sticky="ew")
        ui.label(tab, "纸张尺寸").grid(row=4, column=0, padx=(16, 6), pady=8, sticky="w")
        ctk.CTkEntry(tab, textvariable=self.v["w"], width=100).grid(
            row=4, column=1, padx=6, pady=8, sticky="w")
        ctk.CTkLabel(tab, text="宽 (mm)  ×").grid(row=4, column=2, padx=(0, 6), pady=8, sticky="w")
        ctk.CTkEntry(tab, textvariable=self.v["h"], width=100).grid(
            row=4, column=3, padx=6, pady=8, sticky="w")
        ctk.CTkLabel(tab, text="高 (mm)").grid(row=4, column=4, padx=(0, 16), pady=8, sticky="w")
        ui.check(tab, self.v["en"], "启用此任务").grid(
            row=5, column=0, columnspan=2, padx=(16, 6), pady=8, sticky="w")
        ui.check(tab, self.v["setdefault"], "将该纸张设为默认纸张").grid(
            row=5, column=2, columnspan=2, padx=6, pady=8, sticky="w")
        ui.check(tab, self.v["autotest"], "执行任务时自动打印测试纸").grid(
            row=6, column=0, columnspan=3, padx=(16, 6), pady=8, sticky="w")
        ui.check(tab, self.v["raw"], "标签机 RAW 文本模式（不走系统渲染）").grid(
            row=6, column=3, columnspan=2, padx=6, pady=8, sticky="w")
        ctk.CTkButton(tab, text="🖨  打印测试纸（使用当前设置）", width=300, height=40,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color="#2563eb", hover_color="#1d4ed8",
                      command=lambda: self._on_test(app)).grid(
            row=7, column=0, columnspan=5, padx=16, pady=(10, 8), sticky="w")
        self.refresh_printers()

    def refresh_printers(self, keep=None):
        try:
            names = list_printers()
        except Exception:
            names = []
        if not names:
            names = ["（未检测到打印机）"]
        current = keep or self.v["printer"].get()
        # 手动输入的打印机名不在列表中时，保留在选项最前面（不清空用户输入）
        if current and current.strip() and current not in names \
                and current != "（未检测到打印机）":
            names = [current] + names
        self.menu.configure(values=names)
        self.menu.set(current if current in names else names[0])
        default = get_default_printer()
        if not default:
            self.def_label.configure(
                text="当前系统默认打印机：无 ｜ 未检测到打印机：请确认打印机已连接并开机、"
                     "驱动已安装（刚装好驱动可点「🔄 刷新」重试），或直接在输入框填写打印机名称。")
        else:
            self.def_label.configure(text=f"当前系统默认打印机：{default}")

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", True)))
        self.v["setdefault"].set(bool(cfg.get("set_default", True)))
        self.v["autotest"].set(bool(cfg.get("test_print", False)))
        self.v["raw"].set(bool(cfg.get("raw_mode", False)))
        self.v["form"].set(cfg.get("form_name", ""))
        self.v["w"].set(str(cfg.get("width_mm", 100)))
        self.v["h"].set(str(cfg.get("height_mm", 150)))
        self.v["printer"].set(cfg.get("printer", ""))
        self.refresh_printers(keep=cfg.get("printer", ""))

    def collect_ui(self, cfg):
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["set_default"] = bool(self.v["setdefault"].get())
        cfg["test_print"] = bool(self.v["autotest"].get())
        cfg["raw_mode"] = bool(self.v["raw"].get())
        cfg["printer"] = self.v["printer"].get().strip()
        cfg["form_name"] = self.v["form"].get().strip()
        try:
            cfg["width_mm"] = float(self.v["w"].get().strip())
            cfg["height_mm"] = float(self.v["h"].get().strip())
        except ValueError:
            cfg["width_mm"] = 100.0
            cfg["height_mm"] = 150.0

    def _on_test(self, app):
        if getattr(app, "running", False):
            app._add_log("任务正在执行，请稍后再试", "warn")
            return
        cfg = self.default_cfg()
        self.collect_ui(cfg)

        def work():
            app.msg_queue.put(("status", "正在打印测试纸…"))
            try:
                self.print_test_now(cfg, lambda m, l="info": app.msg_queue.put(("log", m, l)))
                app.msg_queue.put(("log", "✅ 测试纸已打印完成", "ok"))
            except Exception as e:
                app.msg_queue.put(("log", f"测试纸打印失败：{util.error_hint(e)}", "error"))
            finally:
                app.msg_queue.put(("status", "就绪"))

        threading.Thread(target=work, daemon=True).start()
