# -*- coding: utf-8 -*-
"""部署助手 - 主界面（customtkinter）"""
import os
import queue
import threading
from tkinter import filedialog, messagebox, StringVar

import customtkinter as ctk

from . import APP_NAME, APP_VERSION
from . import core, util, config_store

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

LOG_COLORS = {
    "info": "#8b95a5",
    "ok": "#4ade80",
    "error": "#f87171",
    "warn": "#fbbf24",
}


class DeployToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1240x740")
        self.minsize(1080, 640)

        self.store = config_store.ConfigStore()
        self.current_file = None          # 当前配置文件完整路径
        self.running = False
        self.msg_queue = queue.Queue()
        self.task_objs = core.tasks()

        self._build()
        self.after(60, self.refresh_config_list)
        self._new_config()
        self.after(120, self._drain)
        self._add_log("👋 欢迎使用部署助手：左侧选择配置，右侧填写任务，点「开始执行」一键完成。", "warn")

    # ================= 界面构建 =================
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ----- 左侧栏 -----
        sidebar = ctk.CTkFrame(self, width=272, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        self.sidebar = sidebar

        ctk.CTkLabel(sidebar, text="📦 " + APP_NAME,
                     font=ctk.CTkFont(size=23, weight="bold")).pack(pady=(22, 2))
        ctk.CTkLabel(sidebar, text=f"v{APP_VERSION} · 一键部署小工具",
                     text_color="gray").pack()

        seg = ctk.CTkSegmentedButton(sidebar, values=["亮色", "暗色", "跟随系统"],
                                     command=self._set_theme)
        seg.set("跟随系统")
        seg.pack(padx=14, pady=(14, 10), fill="x")

        ctk.CTkLabel(sidebar, text="配置文件", anchor="w",
                     font=ctk.CTkFont(weight="bold")).pack(padx=16, anchor="w")
        self.config_frame = ctk.CTkScrollableFrame(sidebar)
        self.config_frame.pack(padx=10, pady=(6, 8), fill="both", expand=True)

        btn_defs = [
            ("➕ 新建", self._new_config), ("💾 保存", lambda: self._save(False)),
            ("📑 另存为", lambda: self._save(True)), ("🗑 删除", self._delete),
            ("✏️ 重命名", self._rename), ("📥 导入", self._import),
            ("📤 导出", self._export),
        ]
        for r in range(0, len(btn_defs), 2):
            row = ctk.CTkFrame(sidebar, fg_color="transparent")
            row.pack(padx=10, pady=2, fill="x")
            for c in range(2):
                idx = r + c
                if idx >= len(btn_defs):
                    break
                text, cmd = btn_defs[idx]
                ctk.CTkButton(row, text=text, command=cmd, height=30,
                              font=ctk.CTkFont(size=12)).pack(
                    side="left", expand=True, fill="x",
                    padx=(0, 5) if c == 0 else (5, 0))

        # 底部状态栏 + 目录快捷入口（更简洁）
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.pack(padx=14, pady=(6, 14), fill="x")
        self.side_status = ctk.CTkLabel(footer, text="状态：就绪",
                                        text_color="gray", anchor="w")
        self.side_status.pack(side="left")
        ctk.CTkButton(footer, text="📂 配置目录", width=74, height=24,
                      font=ctk.CTkFont(size=11), fg_color="#475569",
                      command=self._open_configs_dir).pack(side="right", padx=(4, 0))
        ctk.CTkButton(footer, text="📄 日志", width=56, height=24,
                      font=ctk.CTkFont(size=11), fg_color="#475569",
                      command=self._open_logs_dir).pack(side="right", padx=4)

        # ----- 右侧主区 -----
        main = ctk.CTkFrame(self, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="配置名称：").grid(row=0, column=0, sticky="w")
        self.name_var = StringVar()
        self.name_entry = ctk.CTkEntry(top, textvariable=self.name_var, width=340,
                                       placeholder_text="输入配置名称")
        self.name_entry.grid(row=0, column=1, sticky="w", padx=(8, 20))

        self.run_btn = ctk.CTkButton(top, text="▶  开始执行", width=190, height=42,
                                     font=ctk.CTkFont(size=16, weight="bold"),
                                     fg_color="#16a34a", hover_color="#15803d",
                                     command=self.start_run)
        self.run_btn.grid(row=0, column=2, sticky="e")

        self.progress = ctk.CTkProgressBar(main, mode="indeterminate")
        self.progress.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))
        self.progress.grid_remove()

        # 每个任务一个标签页（标题已精简，保证 TAB 栏放得下）
        self.tabview = ctk.CTkTabview(main)
        self.tabview.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 8))
        for t in self.task_objs:
            tab = self.tabview.add(t.title)
            t.build_tab(tab, self)
        try:
            self.tabview._segmented_button.configure(font=ctk.CTkFont(size=13))
        except Exception:
            pass

        # 日志区
        logf = ctk.CTkFrame(main)
        logf.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        logf.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(logf, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(head, text="运行日志（按标签页顺序执行）",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="清空", width=56, height=26, fg_color="#475569",
                      command=self._clear_log).pack(side="right", padx=4)

        self.log_box = ctk.CTkTextbox(logf, height=130, wrap="word",
                                      font=ctk.CTkFont(family="Consolas", size=12),
                                      fg_color="#14161c", text_color="#d7dce4")
        self.log_box.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.log_box.configure(state="disabled")
        for tag, color in LOG_COLORS.items():
            self.log_box.tag_config(tag, foreground=color)

    # ================= 通用方法 =================
    def _set_theme(self, value):
        ctk.set_appearance_mode({"亮色": "light", "暗色": "dark"}.get(value, "system"))

    def _add_log(self, msg, level="info"):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n", level)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _open_logs_dir(self):
        try:
            os.startfile(util.logs_dir())
        except Exception as e:
            messagebox.showerror("打开失败", str(e), parent=self)

    def _open_configs_dir(self):
        try:
            os.startfile(self.store.dir)
        except Exception as e:
            messagebox.showerror("打开失败", str(e), parent=self)

    def _highlight(self, path):
        for p, (btn, _) in getattr(self, "config_rows", {}).items():
            if p == path:
                btn.configure(fg_color="#2563eb", text_color="white", hover_color="#1d4ed8")
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"),
                              hover_color=("gray80", "gray35"))

    # ================= 配置管理 =================
    def refresh_config_list(self, select_name=None):
        for w in self.config_frame.winfo_children():
            w.destroy()
        self.config_rows = {}
        items = self.store.list()
        if not items:
            ctk.CTkLabel(self.config_frame, text="暂无配置文件\n点击「新建」开始",
                         text_color="gray").pack(pady=30)
            return
        for it in items:
            btn = ctk.CTkButton(self.config_frame, text=f"📄 {it['name']}", anchor="w",
                                fg_color="transparent", text_color=("gray10", "gray90"),
                                hover_color=("gray80", "gray35"),
                                command=lambda p=it["path"]: self._select_config(p))
            btn.pack(fill="x", padx=2, pady=2)
            self.config_rows[it["path"]] = (btn, it["name"])
        if select_name:
            for path, (btn, name) in self.config_rows.items():
                if name == select_name:
                    self._select_config(path)
                    break
        elif self.current_file and self.current_file in self.config_rows:
            self._highlight(self.current_file)

    def _select_config(self, path):
        try:
            cfg, loaded = self.store.load(path)
        except Exception as e:
            self._add_log(f"读取配置失败：{e}", "error")
            return
        self.current_file = loaded
        self.name_var.set(cfg.get("name", ""))
        for t in self.task_objs:
            try:
                t.load_ui(cfg["tasks"].get(t.key, t.default_cfg()))
            except Exception:
                pass
        self._highlight(loaded)
        self._add_log(f"已加载配置「{cfg.get('name')}」", "info")

    def _new_config(self):
        self.current_file = None
        self.name_var.set("新配置")
        cfg = core.default_cfg()
        for t in self.task_objs:
            try:
                t.load_ui(cfg["tasks"][t.key])
            except Exception:
                pass
        self._highlight(None)

    def _collect(self):
        cfg = core.default_cfg()
        cfg["name"] = self.name_var.get().strip() or "未命名"
        for t in self.task_objs:
            try:
                t.collect_ui(cfg["tasks"][t.key])
            except Exception:
                pass
        return cfg

    def _persist(self, name):
        """按名称保存并处理“改名=移动文件”的语义，返回保存路径"""
        cfg = self._collect()
        path = self.store.save(cfg, name)
        if self.current_file and os.path.normcase(os.path.abspath(path)) != \
                os.path.normcase(os.path.abspath(self.current_file)):
            try:
                os.remove(self.current_file)
            except OSError:
                pass
        self.current_file = path
        return cfg

    def _save(self, as_copy=False):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请先输入配置名称", parent=self)
            return
        if as_copy:
            new_name = ctk.CTkInputDialog(text="请输入新配置名称：", title="另存为").get_input()
            if not new_name:
                return
            name = new_name.strip()
            if not name:
                return
        try:
            self._persist(name)
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return
        self.name_var.set(name)
        self.refresh_config_list(select_name=name)
        self._add_log(f"配置已保存：{self.current_file}", "ok")

    def _delete(self):
        if not self.current_file:
            messagebox.showinfo("提示", "当前配置尚未保存", parent=self)
            return
        if not messagebox.askyesno("确认删除",
                                   f"确定删除配置「{self.name_var.get().strip()}」吗？",
                                   parent=self):
            return
        try:
            self.store.delete(self.current_file)
        except Exception as e:
            messagebox.showerror("删除失败", str(e), parent=self)
            return
        self.current_file = None
        self.refresh_config_list()
        self._new_config()
        self._add_log("配置已删除", "warn")

    def _rename(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请先输入配置名称", parent=self)
            return
        new_name = ctk.CTkInputDialog(text="请输入新配置名称：", title="重命名").get_input()
        if not new_name or new_name.strip() == name:
            return
        new_name = new_name.strip()
        try:
            self._persist(new_name)
        except Exception as e:
            messagebox.showerror("重命名失败", str(e), parent=self)
            return
        self.name_var.set(new_name)
        self.refresh_config_list(select_name=new_name)
        self._add_log(f"配置已重命名为「{new_name}」", "ok")

    def _import(self):
        p = filedialog.askopenfilename(title="导入配置",
                                       filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            cfg, _ = self.store.load(p)
            saved = self.store.save(cfg, cfg.get("name", "导入的配置"))
        except Exception as e:
            messagebox.showerror("导入失败", str(e), parent=self)
            return
        self.refresh_config_list(select_name=cfg.get("name"))
        self._add_log(f"已导入配置：{saved}", "ok")

    def _export(self):
        name = self.name_var.get().strip() or "配置"
        p = filedialog.asksaveasfilename(
            title="导出配置", defaultextension=".json",
            initialfile=util.sanitize_filename(name) + ".json",
            filetypes=[("JSON 配置", "*.json")])
        if not p:
            return
        cfg = self._collect()
        try:
            self.store.save(cfg, name, path=p)
            self._add_log(f"配置已导出：{p}", "ok")
        except Exception as e:
            messagebox.showerror("导出失败", str(e), parent=self)

    # ================= 执行 =================
    def start_run(self):
        if self.running:
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请先输入配置名称", parent=self)
            return
        try:
            cfg = self._persist(name)   # 执行前自动保存
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return
        self.refresh_config_list(select_name=name)

        self.running = True
        self.run_btn.configure(state="disabled", text="⏳ 执行中…")
        self.progress.grid()
        self.progress.start()
        self._add_log(f"========== 开始执行配置「{name}」 ==========", "warn")

        engine = core.Engine(log=self._push_log, status=self._push_status)

        def work():
            ok, summary, failures = engine.run(cfg)
            self.msg_queue.put(("done", ok, summary, failures))

        threading.Thread(target=work, daemon=True).start()

    def _push_log(self, msg, level="info"):
        self.msg_queue.put(("log", msg, level))

    def _push_status(self, text):
        self.msg_queue.put(("status", text))

    def _drain(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._add_log(item[1], item[2])
                elif kind == "status":
                    self.side_status.configure(text=f"状态：{item[1]}")
                elif kind == "done":
                    _, ok, summary, failures = item
                    self.progress.stop()
                    self.progress.grid_remove()
                    self.run_btn.configure(state="normal", text="▶  开始执行")
                    self.running = False
                    self.side_status.configure(text="状态：就绪")
                    if ok:
                        self._add_log("✅ " + summary, "ok")
                        messagebox.showinfo("配置完成",
                                            f"✅ {summary}\n\n配置执行成功，全部任务完成！",
                                            parent=self)
                    else:
                        detail = "\n".join(f"• {t}：{r}" for t, r in failures[:6])
                        if len(failures) > 6:
                            detail += "\n• ……（详见日志）"
                        self._add_log("❌ " + summary, "error")
                        messagebox.showerror("执行失败",
                                             f"❌ {summary}\n\n失败原因：\n{detail}",
                                             parent=self)
        except queue.Empty:
            pass
        self.after(120, self._drain)


def run_gui():
    app = DeployToolApp()
    app.mainloop()
