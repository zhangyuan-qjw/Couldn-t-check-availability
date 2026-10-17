# -*- coding: utf-8 -*-
"""无界面执行器：命令行 -r "配置名" 时弹出一个轻量进度窗口"""
import queue
import threading
import time

import customtkinter as ctk
from tkinter import messagebox

from . import core, util, config_store


def run_config(arg):
    """按名称或路径执行配置，弹出进度窗口并汇报结果"""
    store = config_store.ConfigStore()
    try:
        cfg, _path = store.load(arg)
    except Exception as e:
        util.show_message("执行失败", f"无法读取配置「{arg}」：\n{e}", "error")
        return

    win = ctk.CTk()
    win.title(f"部署助手 - 正在执行「{cfg.get('name')}」")
    win.geometry("660x440")
    win.attributes("-topmost", True)
    q = queue.Queue()

    ctk.CTkLabel(win, text=f"🚀 正在执行配置：{cfg.get('name')}",
                 font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(18, 6))
    prog = ctk.CTkProgressBar(win, mode="indeterminate")
    prog.pack(padx=20, fill="x")
    prog.start()
    status = ctk.CTkLabel(win, text="准备中…", text_color="gray")
    status.pack(pady=(6, 6))
    box = ctk.CTkTextbox(win, wrap="word", font=ctk.CTkFont(family="Consolas", size=12),
                         fg_color="#14161c", text_color="#d7dce4")
    box.pack(padx=20, pady=(0, 16), fill="both", expand=True)
    box.configure(state="disabled")

    def push(msg, level="info"):
        q.put(("log", msg, level))

    def push_status(text):
        q.put(("status", text))

    engine = core.Engine(log=push, status=push_status)
    result = {}

    def work():
        try:
            result["v"] = engine.run(cfg)
        except Exception as e:
            result["v"] = (False, f"执行异常：{e}", [("系统", str(e))])
        q.put(("done",))

    threading.Thread(target=work, daemon=True).start()

    def drain():
        try:
            while True:
                it = q.get_nowait()
                if it[0] == "log":
                    box.configure(state="normal")
                    box.insert("end", f"[{time.strftime('%H:%M:%S')}] {it[1]}\n")
                    box.see("end")
                    box.configure(state="disabled")
                elif it[0] == "status":
                    status.configure(text=it[1])
                elif it[0] == "done":
                    ok, summary, failures = result["v"]
                    prog.stop()
                    box.configure(state="normal")
                    if ok:
                        box.insert("end", f"✅ {summary}\n")
                        box.configure(state="disabled")
                        messagebox.showinfo("配置完成",
                                            f"✅ {summary}\n\n配置「{cfg.get('name')}」执行完成！",
                                            parent=win)
                    else:
                        detail = "\n".join(f"• {t}：{r}" for t, r in failures[:6])
                        box.insert("end", f"❌ {summary}\n")
                        box.configure(state="disabled")
                        messagebox.showerror("执行失败",
                                             f"❌ {summary}\n\n失败原因：\n{detail}",
                                             parent=win)
                    win.after(500, win.destroy)
                    return
        except queue.Empty:
            pass
        win.after(100, drain)

    win.after(100, drain)
    win.mainloop()


def list_configs():
    store = config_store.ConfigStore()
    items = store.list()
    if not items:
        util.show_message("配置文件", "暂无配置文件。\n\n打开界面创建并保存配置后，"
                                       "即可用 -r 参数直接运行。", "info")
        return
    text = ("可用配置文件：\n\n"
            + "\n".join(f"• {it['name']}" for it in items)
            + "\n\n用法：部署助手.exe -r \"配置名\"")
    util.show_message("配置文件", text, "info")
