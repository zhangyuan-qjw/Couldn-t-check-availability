# -*- coding: utf-8 -*-
"""任务：操作录制与回放（「操作录制」标签页）。

- 录制：开始录制 → 手动操作一遍 → 完成并保存（脚本记住程序路径）；
- 勾选脚本 = 该配置「开始执行」时自动回放对应脚本（勾选状态保存进配置文件）；
- 回放：按脚本自动定位程序、逐步回放，完成后由通用自动点击器兜底。
"""
import json
import os
import threading
from tkinter import BooleanVar, StringVar, messagebox

import customtkinter as ctk

from ..core import BaseTask, TaskError, register
from .. import util
from .. import ui_helpers as ui
from . import _recorder, driver_task

SPEED_MAP = {"1x 原速": 1, "2x 快速": 2, "5x 极速": 5}


@register
class RecordReplayTask(BaseTask):
    """操作录制与回放"""
    key = "record_replay"
    title = "操作录制"
    icon = "⏺"
    order = 36  # 在驱动安装(38)之前：录制的安装/卸载脚本先执行

    def default_cfg(self):
        return {"enabled": True, "scripts": [], "speed": "1x 原速"}

    # ---------------- 执行（点击「开始执行」时） ----------------
    def run(self, cfg, log):
        entries = [e for e in (cfg.get("scripts") or [])
                   if isinstance(e, dict) and e.get("script")]
        if not entries:
            log("未勾选任何录制脚本，跳过。")
            return
        speed = SPEED_MAP.get(str(cfg.get("speed") or "1x 原速"), 1)
        ok = 0
        fails = []
        for e in entries:
            sp = e.get("script") or ""
            name = e.get("name") or os.path.basename(sp)
            # 脚本路径失效时（换机器/移目录），按程序内容重新匹配
            if not os.path.isfile(sp):
                if e.get("program_path"):
                    matched = _recorder.find_scripts(e["program_path"])
                    if matched:
                        sp = matched[0]
            if not os.path.isfile(sp):
                fails.append("「%s」：脚本文件不存在（%s）" % (name, sp))
                continue
            try:
                data = _recorder.load_script(sp)
                steps = list(data.get("steps") or [])
            except Exception as ex:
                fails.append("「%s」：脚本读取失败（%s）" % (name, ex))
                continue
            prog = _recorder.resolve_program(sp, e.get("program_path") or "")
            if not prog:
                fails.append("「%s」：找不到对应的程序文件" % name)
                continue
            log("========== 回放脚本「%s」（%s 步，程序：%s） ==========" %
                (name, len(steps), prog))
            try:
                driver_task.run_installer_replay(prog, steps, 300, log, speed=speed)
                log("✅ 脚本「%s」回放完成" % name)
                ok += 1
            except TaskError as ex:
                log("❌ 脚本「%s」失败：%s" % (name, ex), "error")
                fails.append("「%s」：%s" % (name, ex))
            except Exception as ex:
                log("❌ 脚本「%s」异常：%s" % (name, util.error_hint(ex)), "error")
                fails.append("「%s」：%s" % (name, util.error_hint(ex)))
        log("录制脚本回放结束：成功 %s 个，失败 %s 个" % (ok, len(fails)))
        if fails:
            raise TaskError("录制脚本回放失败：\n" + "\n".join(fails))

    # ---------------- 界面 ----------------
    def build_tab(self, tab, app):
        self.app = app
        tab.grid_columnconfigure(1, weight=1)
        self.v = {
            "prog": StringVar(),
            "speed": StringVar(value="1x 原速"),
        }
        self.rec = None
        self._selected = set()   # 勾选“开始执行时回放”的脚本路径

        ui.hint(tab, "把任意安装/卸载/配置程序的手动操作录制成脚本；"
                     "勾选的脚本会在点「开始执行」时自动回放（勾选状态保存进配置文件）。").grid(
            row=0, column=0, columnspan=3, padx=16, pady=(14, 4), sticky="w")

        # 目标程序（仅录制时使用；回放会自动定位脚本对应的程序）
        ui.label(tab, "目标程序（录制时用）").grid(row=1, column=0, padx=(16, 6), pady=6, sticky="w")
        ui.entry(tab, self.v["prog"], placeholder="选择要录制的程序（.exe / 安装包 / 卸载程序）").grid(
            row=1, column=1, padx=6, pady=6, sticky="ew")
        ui.button(tab, "浏览…", lambda: ui.browse_file(
            self.v["prog"], "选择程序",
            [("程序", "*.exe *.msi *.bat *.cmd"), ("所有文件", "*.*")])).grid(
            row=1, column=2, padx=(6, 16), pady=6)
        try:
            self.v["prog"].trace_add("write", lambda *_a: self._save_state())
        except Exception:
            pass

        # 操作按钮行
        btns = ctk.CTkFrame(tab, fg_color="transparent")
        btns.grid(row=2, column=0, columnspan=3, padx=16, pady=(8, 4), sticky="w")
        self.start_btn = ctk.CTkButton(btns, text="⏺ 开始录制", width=150, height=36,
                                       font=ctk.CTkFont(size=14, weight="bold"),
                                       fg_color="#7c3aed", hover_color="#6d28d9",
                                       command=self._start)
        self.start_btn.pack(side="left", padx=(0, 10))
        self.finish_btn = ctk.CTkButton(btns, text="✔ 完成并保存", width=150, height=36,
                                        fg_color="#16a34a", hover_color="#15803d",
                                        state="disabled", command=self._finish)
        self.finish_btn.pack(side="left")

        self.status_label = ui.hint(tab, "状态：就绪")
        self.status_label.grid(row=3, column=0, columnspan=3, padx=(16, 6), pady=(2, 6), sticky="w")

        # 已保存脚本列表
        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.grid(row=4, column=0, columnspan=3, padx=16, pady=(8, 2), sticky="ew")
        ctk.CTkLabel(head, text="已保存的脚本（勾选 = 开始执行时回放）",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(head, text="回放速度", text_color="gray").pack(side="right", padx=(8, 4))
        ctk.CTkSegmentedButton(head, values=["1x 原速", "2x 快速", "5x 极速"],
                               variable=self.v["speed"], width=210, height=24,
                               font=ctk.CTkFont(size=12)).pack(side="right", padx=4)
        ctk.CTkButton(head, text="🔄 刷新", width=72, height=26, fg_color="#475569",
                      command=self._refresh_list).pack(side="right", padx=4)

        self.list_frame = ctk.CTkScrollableFrame(tab, height=150)
        self.list_frame.grid(row=5, column=0, columnspan=3, padx=16, pady=(0, 10), sticky="ew")

        self.v["prog"].set(self._load_state())
        self._refresh_list()

    # ---------------- 状态持久化（记住上次打开的程序） ----------------
    def _state_path(self):
        return os.path.join(util.scripts_dir(), "_state.json")

    def _load_state(self):
        try:
            with open(self._state_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get("program") or "")
        except Exception:
            return ""

    def _save_state(self):
        try:
            d = util.scripts_dir()
            os.makedirs(d, exist_ok=True)
            with open(self._state_path(), "w", encoding="utf-8") as f:
                json.dump({"program": self.v["prog"].get().strip()}, f, ensure_ascii=False)
        except Exception:
            pass

    # ---------------- 脚本列表 ----------------
    def _all_scripts(self):
        out = []
        d = util.scripts_dir()
        try:
            for fn in sorted(os.listdir(d)):
                if not fn.lower().endswith(".json") or fn.startswith((".", "_")):
                    continue
                p = os.path.join(d, fn)
                if os.path.isfile(p):
                    out.append(p)
        except OSError:
            pass
        out.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return out

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        scripts = self._all_scripts()
        if not scripts:
            ctk.CTkLabel(self.list_frame, text="还没有录制脚本。选择程序后点「⏺ 开始录制」录一遍吧。",
                         text_color="gray").pack(pady=14)
            return
        for path in scripts:
            name, prog, n, when = _recorder.script_summary(path)
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = BooleanVar(value=path in self._selected)
            ctk.CTkCheckBox(row, text="", variable=var, width=28,
                            command=lambda p=path, v=var: self._on_check(p, v)).pack(side="left")
            ctk.CTkLabel(row, text="📄 %s" % name, width=170, anchor="w",
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(row, text="%s · %s 步 · %s" % (prog, n, when),
                         text_color="gray", anchor="w").pack(side="left", padx=6, fill="x", expand=True)
            ctk.CTkButton(row, text="▶ 回放", width=70, height=26,
                          command=lambda p=path: self._replay(p)).pack(side="right", padx=3)
            ctk.CTkButton(row, text="🗑 删除", width=60, height=26, fg_color="#b91c1c",
                          hover_color="#991b1b",
                          command=lambda p=path: self._delete(p)).pack(side="right", padx=3)

    def _on_check(self, path, var):
        if var.get():
            self._selected.add(path)
        else:
            self._selected.discard(path)
        self.status_label.configure(
            text="状态：已勾选 %s 个脚本（点「开始执行」时依次回放；记得💾保存配置）" % len(self._selected))

    # ---------------- 录制流程 ----------------
    def _start(self):
        if self.rec and self.rec.is_recording():
            messagebox.showinfo("提示", "已在录制中，请先点「✔ 完成并保存」结束本次录制。", parent=self.app)
            return
        prog = self.v["prog"].get().strip()
        if not prog or not os.path.isfile(prog):
            messagebox.showwarning("提示", "请先选择要录制的程序。", parent=self.app)
            return
        self._save_state()
        self.rec = _recorder.Recorder(prog, log=self._log, on_status=self._status)
        try:
            self.rec.start()
        except Exception as e:
            self.rec = None
            self._log("无法启动录制：%s" % e, "error")
            return
        self.start_btn.configure(state="disabled", text="⏺ 录制中…")
        self.finish_btn.configure(state="normal")

    def _finish(self):
        """完成录制：弹出名称输入框，确认则保存脚本，取消则不记录本次录制"""
        if self.rec:
            saved = False
            if self.rec.steps:
                default = os.path.splitext(os.path.basename(self.v["prog"].get().strip() or "脚本"))[0]
                dialog = ctk.CTkInputDialog(text="请输入脚本名称：", title="保存录制脚本")
                name = dialog.get_input()          # 取消返回 None
                if name is None:
                    self._log("已取消保存：本次录制脚本未记录。", "warn")
                else:
                    name = name.strip() or default
                    try:
                        path = self.rec.save(name)
                        self._log("✅ 录制脚本已保存：%s（%s 个操作）"
                                  % (path, len(self.rec.steps)), "ok")
                        saved = True
                    except Exception as e:
                        self._log("保存脚本失败：%s" % e, "error")
            else:
                self._log("本次没有录制到操作，未保存脚本。", "warn")
            try:
                self.rec.stop()
            except Exception:
                pass
            self.rec = None
            if saved:
                self._refresh_list()
        self.start_btn.configure(state="normal", text="⏺ 开始录制")
        self.finish_btn.configure(state="disabled")
        self._status("状态：就绪")

    def _status(self, text):
        try:
            self.status_label.configure(text="状态：" + text)
        except Exception:
            pass

    def _log(self, msg, level="info"):
        self.app.msg_queue.put(("log", msg, level))

    # ---------------- 回放（手动点「▶ 回放」） ----------------
    def _replay(self, script_path):
        if self.rec and self.rec.is_recording():
            messagebox.showinfo("提示", "请先点「✔ 完成并保存」结束录制，再回放脚本。", parent=self.app)
            return
        if getattr(self.app, "running", False):
            self.app._add_log("任务正在执行，请稍后再试", "warn")
            return
        prog = _recorder.resolve_program(script_path, self.v["prog"].get().strip())
        if not prog:
            messagebox.showwarning(
                "提示", "找不到该脚本对应的程序文件。\n"
                        "请在「目标程序」里重新选择该程序后，再点回放。", parent=self.app)
            return
        try:
            data = _recorder.load_script(script_path)
            steps = list(data.get("steps") or [])
        except Exception as e:
            self._log("脚本读取失败：%s" % e, "error")
            return
        if not steps:
            self._log("脚本为空，无法回放", "warn")
            return
        name = data.get("display_name") or os.path.basename(script_path)
        speed = SPEED_MAP.get(self.v["speed"].get(), 1)
        self._log("========== 开始回放脚本「%s」（%s 步，%s，程序：%s） ==========" %
                  (name, len(steps), self.v["speed"].get(), prog), "warn")

        def work():
            self.app.msg_queue.put(("status", "正在回放脚本…"))
            try:
                driver_task.run_installer_replay(
                    prog, steps, 300,
                    lambda m, l="info": self.app.msg_queue.put(("log", m, l)),
                    speed=speed)
                self.app.msg_queue.put(("log", "✅ 脚本回放完成", "ok"))
            except TaskError as e:
                self.app.msg_queue.put(("log", "❌ 回放失败：%s" % e, "error"))
            except Exception as e:
                self.app.msg_queue.put(("log", "❌ 回放异常：%s" % util.error_hint(e), "error"))
            finally:
                self.app.msg_queue.put(("status", "就绪"))

        threading.Thread(target=work, daemon=True).start()

    # ---------------- 删除 ----------------
    def _delete(self, script_path):
        if not messagebox.askyesno("确认删除", "确定删除脚本「%s」吗？" % os.path.basename(script_path),
                                   parent=self.app):
            return
        try:
            os.remove(script_path)
        except OSError as e:
            self._log("删除失败：%s" % e, "error")
            return
        self._selected.discard(script_path)
        self._refresh_list()
        self._log("已删除脚本：%s" % os.path.basename(script_path), "warn")

    # ---------------- 配置存取（勾选状态保存进配置文件） ----------------
    def load_ui(self, cfg):
        self._selected = set()
        for e in (cfg.get("scripts") or []):
            if isinstance(e, dict) and e.get("script"):
                self._selected.add(e["script"])
        self.v["speed"].set(str(cfg.get("speed") or "1x 原速"))
        self._refresh_list()
        if self._selected:
            self.status_label.configure(
                text="状态：已勾选 %s 个脚本（点「开始执行」时依次回放）" % len(self._selected))

    def collect_ui(self, cfg):
        entries = []
        for p in self._selected:
            data = _recorder.load_script(p) or {}
            prog = data.get("program") or {}
            entries.append({"script": p,
                            "name": data.get("display_name") or os.path.basename(p)[:-5],
                            "program_path": prog.get("path", "")})
        cfg["scripts"] = entries
        cfg["speed"] = self.v["speed"].get().strip() or "1x 原速"
