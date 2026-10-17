# -*- coding: utf-8 -*-
"""任务：桌面快捷方式 + 开机自启（支持多个程序）+ 取消自启"""
import os
from tkinter import BooleanVar, StringVar

import customtkinter as ctk

from ..core import BaseTask, TaskError, register
from .. import util
from .. import ui_helpers as ui

AUTOSTART_MODES = {
    "startup_folder": "启动文件夹（当前用户）",
    "common_startup": "启动文件夹（所有用户·需管理员）",
    "registry": "注册表启动项（当前用户）",
    "none": "不设置自启",
}
_MODE_KEYS = {v: k for k, v in AUTOSTART_MODES.items()}


def make_lnk(target, lnk_path, args="", workdir="", icon="", desc=""):
    """创建 .lnk 快捷方式（后台线程安全：自动初始化 COM）"""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()  # 修复：后台线程未初始化 COM 时 Dispatch 报 0x800401F0
    shell = None
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(lnk_path)
        sc.TargetPath = target
        sc.Arguments = args or ""
        sc.WorkingDirectory = workdir or os.path.dirname(target)
        sc.Description = desc or f"由 {util.APP_NAME} 创建"
        if icon:
            sc.IconLocation = icon if "," in icon else f"{icon},0"
        sc.Save()
        del sc
    finally:
        del shell
        pythoncom.CoUninitialize()


def set_registry_autostart(name, command):
    """写入 HKCU\\...\\Run 注册表启动项"""
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
    try:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
    finally:
        winreg.CloseKey(key)


def default_item():
    return {"exe": "", "name": "", "args": "", "workdir": "", "icon": "",
            "desktop": True, "autostart": True, "autostart_mode": "startup_folder"}


def normalize_items(cfg):
    """兼容旧版单程序配置：有 exe 字段而无 items 时自动转换"""
    items = cfg.get("items")
    if items:
        out = []
        for it in items:
            if isinstance(it, dict):
                d = default_item()
                d.update(it)
                out.append(d)
        return out
    if cfg.get("exe"):
        d = default_item()
        for k in ("exe", "name", "args", "workdir", "icon"):
            d[k] = cfg.get(k, "")
        d["desktop"] = bool(cfg.get("desktop", True))
        d["autostart"] = bool(cfg.get("autostart", True))
        mode = cfg.get("autostart_mode", "startup_folder")
        d["autostart_mode"] = mode if mode in AUTOSTART_MODES else "startup_folder"
        return [d]
    return []


def _apply_item(item, log):
    """处理单个程序项，返回执行摘要列表"""
    exe = (item.get("exe") or "").strip()
    if not exe:
        raise TaskError(f"第 {item.get('_idx', '?')} 个程序未指定路径")
    if not os.path.isfile(exe):
        raise TaskError(f"程序不存在：{exe}")
    name = util.sanitize_filename(
        (item.get("name") or "").strip() or os.path.splitext(os.path.basename(exe))[0])
    args = (item.get("args") or "").strip()
    workdir = (item.get("workdir") or "").strip()
    icon = (item.get("icon") or "").strip()

    created = []
    if item.get("desktop", True):
        desktop = util.get_desktop_dir()
        try:
            os.makedirs(desktop, exist_ok=True)
            p = os.path.join(desktop, name + ".lnk")
            make_lnk(exe, p, args=args, workdir=workdir, icon=icon, desc=name)
            created.append(f"桌面快捷方式：{p}")
        except Exception as e:
            raise TaskError(f"创建桌面快捷方式失败（{name}）：{util.error_hint(e)}")

    mode = item.get("autostart_mode", "startup_folder")
    if mode == "none":
        if not created:
            raise TaskError(f"程序「{name}」未启用任何创建项")
    else:
        try:
            if mode == "registry":
                cmd = f'"{exe}"' + (f" {args}" if args else "")
                set_registry_autostart(name, cmd)
                created.append(
                    f"注册表启动项：HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\{name}")
            else:
                sdir = util.get_startup_dir(common=(mode == "common_startup"))
                os.makedirs(sdir, exist_ok=True)
                p = os.path.join(sdir, name + ".lnk")
                make_lnk(exe, p, args=args, workdir=workdir, icon=icon,
                         desc=f"开机自启：{name}")
                created.append(f"开机自启快捷方式：{p}")
        except Exception as e:
            raise TaskError(f"设置开机自启失败（{name}）：{util.error_hint(e)}")
    return created


@register
class ShortcutTask(BaseTask):
    """为多个程序创建桌面快捷方式，并设置开机自启"""
    key = "shortcut"
    title = "快捷方式"
    icon = "🔗"
    order = 30

    def default_cfg(self):
        return {"enabled": True, "items": [default_item()]}

    def run(self, cfg, log):
        items = normalize_items(cfg)
        if not items:
            raise TaskError("未添加任何程序（点「➕ 添加程序」填写）")
        for i, item in enumerate(items):
            item = dict(item)
            item["_idx"] = i + 1
            created = _apply_item(item, log)
            for c in created:
                log(c)

    # ---------------- 界面 ----------------
    def build_tab(self, tab, app):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        self.v = {
            "en": BooleanVar(value=True),
            "exe": StringVar(), "name": StringVar(), "args": StringVar(),
            "workdir": StringVar(), "icon": StringVar(),
            "desktop": BooleanVar(value=True), "autostart": BooleanVar(value=True),
            "mode": StringVar(value=AUTOSTART_MODES["startup_folder"]),
        }
        self.items = [default_item()]
        self.cur = 0
        self.item_buttons = []

        ui.hint(tab, "可添加多个程序：每个程序分别设置桌面快捷方式与开机自启（开机自动运行）。").grid(
            row=0, column=0, columnspan=3, padx=16, pady=(16, 4), sticky="w")

        # 左侧：程序列表
        left = ctk.CTkFrame(tab)
        left.grid(row=1, column=0, sticky="nsw", padx=(16, 8), pady=4)
        ctk.CTkLabel(left, text="程序列表", font=ctk.CTkFont(weight="bold")).pack(pady=(6, 2))
        self.list_frame = ctk.CTkScrollableFrame(left, width=230)
        self.list_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=6, pady=(0, 6))
        ctk.CTkButton(btn_row, text="➕ 添加", width=70, command=self._add_item).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="🗑 删除", width=70, command=self._del_item).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="⬆", width=34, command=lambda: self._move_item(-1)).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="⬇", width=34, command=lambda: self._move_item(1)).pack(side="left", padx=2)

        # 右侧：当前程序编辑区
        right = ctk.CTkFrame(tab)
        right.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=(8, 16), pady=4)
        right.grid_columnconfigure(1, weight=1)

        ui.label(right, "程序路径（exe）", width=110).grid(row=0, column=0, padx=(12, 6), pady=6, sticky="w")
        ui.entry(right, self.v["exe"], placeholder="选择要创建快捷方式的程序").grid(
            row=0, column=1, padx=6, pady=6, sticky="ew")
        ui.button(right, "浏览…", lambda: ui.browse_file(
            self.v["exe"], "选择程序", [("程序", "*.exe"), ("所有文件", "*.*")])).grid(
            row=0, column=2, padx=(6, 12), pady=6)
        ui.label(right, "快捷方式名称", width=110).grid(row=1, column=0, padx=(12, 6), pady=6, sticky="w")
        ui.entry(right, self.v["name"], placeholder="留空则用程序文件名").grid(
            row=1, column=1, columnspan=2, padx=6, pady=6, sticky="ew")
        ui.label(right, "启动参数（可选）", width=110).grid(row=2, column=0, padx=(12, 6), pady=6, sticky="w")
        ui.entry(right, self.v["args"], placeholder="例如：--minimized 或 /start").grid(
            row=2, column=1, columnspan=2, padx=6, pady=6, sticky="ew")
        ui.label(right, "工作目录（可选）", width=110).grid(row=3, column=0, padx=(12, 6), pady=6, sticky="w")
        ui.entry(right, self.v["workdir"], placeholder="留空则为程序所在目录").grid(
            row=3, column=1, columnspan=2, padx=6, pady=6, sticky="ew")
        ui.label(right, "图标文件（可选）", width=110).grid(row=4, column=0, padx=(12, 6), pady=6, sticky="w")
        ui.entry(right, self.v["icon"], placeholder=".ico / .exe / .dll，留空用默认图标").grid(
            row=4, column=1, padx=6, pady=6, sticky="ew")
        ui.button(right, "浏览…", lambda: ui.browse_file(
            self.v["icon"], "选择图标", [("图标", "*.ico"), ("可执行文件", "*.exe"), ("所有文件", "*.*")])).grid(
            row=4, column=2, padx=(6, 12), pady=6)
        ui.check(right, self.v["desktop"], "创建桌面快捷方式").grid(
            row=5, column=1, padx=6, pady=4, sticky="w")
        ui.check(right, self.v["autostart"], "设置开机自启").grid(
            row=5, column=2, padx=6, pady=4, sticky="w")
        ui.label(right, "自启方式", width=110).grid(row=6, column=0, padx=(12, 6), pady=6, sticky="w")
        self.mode_menu = ctk.CTkOptionMenu(right, values=list(AUTOSTART_MODES.values()),
                                           variable=self.v["mode"], width=290)
        self.mode_menu.grid(row=6, column=1, columnspan=2, padx=6, pady=6, sticky="w")
        ui.hint(right, "提示：Win+R 输入 shell:startup 可查看“启动文件夹”；"
                       "注册表项位于 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run。").grid(
            row=7, column=0, columnspan=3, padx=12, pady=(2, 4), sticky="w")

        ui.check(tab, self.v["en"], "启用此任务").grid(
            row=2, column=0, columnspan=3, padx=(16, 6), pady=6, sticky="w")
        self._refresh_list()

    # ---------- 列表与编辑器联动 ----------
    def _item_label(self, i, it):
        name = (it.get("name") or "").strip() or os.path.splitext(os.path.basename(it.get("exe", "")))[0] or "未命名"
        return f"🔗 {i + 1}. {name}"

    def _refresh_list(self, keep=None):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.item_buttons = []
        for i, it in enumerate(self.items):
            btn = ctk.CTkButton(self.list_frame, text=self._item_label(i, it), anchor="w",
                                fg_color="transparent", text_color=("gray10", "gray90"),
                                hover_color=("gray80", "gray35"),
                                command=lambda idx=i: self._select(idx))
            btn.pack(fill="x", padx=2, pady=2)
            self.item_buttons.append(btn)
        self._highlight_list()

    def _highlight_list(self):
        for i, btn in enumerate(self.item_buttons):
            if i == self.cur:
                btn.configure(fg_color="#2563eb", text_color="white", hover_color="#1d4ed8")
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"),
                              hover_color=("gray80", "gray35"))

    def _flush_editor(self):
        """把编辑器当前值写回当前项"""
        if self.cur is None or not (0 <= self.cur < len(self.items)):
            return
        it = self.items[self.cur]
        it["exe"] = self.v["exe"].get().strip()
        it["name"] = self.v["name"].get().strip()
        it["args"] = self.v["args"].get().strip()
        it["workdir"] = self.v["workdir"].get().strip()
        it["icon"] = self.v["icon"].get().strip()
        it["desktop"] = bool(self.v["desktop"].get())
        it["autostart"] = bool(self.v["autostart"].get())
        it["autostart_mode"] = _MODE_KEYS.get(self.v["mode"].get(), "startup_folder")

    def _load_editor(self):
        if self.cur is None:
            self.cur = 0
        if not self.items:
            self.items = [default_item()]
            self.cur = 0
        it = self.items[self.cur]
        self.v["exe"].set(it.get("exe", ""))
        self.v["name"].set(it.get("name", ""))
        self.v["args"].set(it.get("args", ""))
        self.v["workdir"].set(it.get("workdir", ""))
        self.v["icon"].set(it.get("icon", ""))
        self.v["desktop"].set(bool(it.get("desktop", True)))
        self.v["autostart"].set(bool(it.get("autostart", True)))
        mode = it.get("autostart_mode", "startup_folder")
        if mode not in AUTOSTART_MODES:
            mode = "startup_folder"
        self.v["mode"].set(AUTOSTART_MODES[mode])

    def _select(self, idx):
        self._flush_editor()
        self.cur = idx
        self._load_editor()
        self._highlight_list()

    def _add_item(self):
        self._flush_editor()
        self.items.append(default_item())
        self.cur = len(self.items) - 1
        self._load_editor()
        self._refresh_list()

    def _del_item(self):
        if len(self.items) <= 1:
            self.items = [default_item()]
            self.cur = 0
        else:
            if self.cur is not None and 0 <= self.cur < len(self.items):
                self.items.pop(self.cur)
            self.cur = min(self.cur or 0, len(self.items) - 1)
        self._load_editor()
        self._refresh_list()

    def _move_item(self, delta):
        if self.cur is None:
            return
        self._flush_editor()
        j = self.cur + delta
        if 0 <= j < len(self.items):
            self.items[self.cur], self.items[j] = self.items[j], self.items[self.cur]
            self.cur = j
        self._refresh_list()
        self._load_editor()

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", True)))
        self.items = normalize_items(cfg) or [default_item()]
        self.cur = 0
        self._load_editor()
        self._refresh_list()

    def collect_ui(self, cfg):
        self._flush_editor()
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["items"] = [dict(it) for it in self.items]
