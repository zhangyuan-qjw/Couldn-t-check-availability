# -*- coding: utf-8 -*-
"""界面小组件封装（供各任务模块构建标签页）"""
from tkinter import filedialog

import customtkinter as ctk


def label(parent, text, width=130):
    return ctk.CTkLabel(parent, text=text, width=width, anchor="w")


def hint(parent, text):
    return ctk.CTkLabel(parent, text=text, text_color="gray", anchor="w", justify="left")


def entry(parent, var, placeholder=""):
    return ctk.CTkEntry(parent, textvariable=var, placeholder_text=placeholder)


def button(parent, text, command, width=96):
    return ctk.CTkButton(parent, text=text, command=command, width=96 if width is None else width)


def check(parent, var, text):
    return ctk.CTkCheckBox(parent, text=text, variable=var)


def browse_file(var, title="选择文件", filetypes=None):
    p = filedialog.askopenfilename(title=title,
                                   filetypes=filetypes or [("所有文件", "*.*")])
    if p:
        var.set(p)


def browse_dir(var, title="选择文件夹"):
    p = filedialog.askdirectory(title=title)
    if p:
        var.set(p)
