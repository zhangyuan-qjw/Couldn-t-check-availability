# 📦 部署助手（Deploy Tool）

一个面向 Windows 的 **一键部署小工具**，把日常重复的部署操作（复制文件、创建快捷方式、
设置开机自启、配置打印机纸张）打包成 **可命名的配置文件**，双击即可一键完成全部步骤。
界面美观简洁，任务模块化，**后续加功能只需新增一个文件**。

---

## ✨ 功能清单

| # | 功能 | 说明 |
|---|------|------|
| 1 | 📦 复制文件 | 把指定文件夹或 zip / tar / 7z 压缩包复制到指定目录；**源是压缩包时可勾选“先复制压缩包到目标文件夹、再解压”**（单文件复制远快于大量小文件，加速部署），解压后可自动删除压缩包副本 |
| 2 | 🔗 桌面快捷方式 + 开机自启 | **支持添加多个程序**，逐个设置桌面快捷方式与开机启动（启动文件夹 / 注册表任选），开机自动运行 |
| 3 | 🔧 驱动一键安装 | 指定驱动安装程序（.exe / .msi / .bat），部署时**自动安装**：自动识别安装包类型（Inno / NSIS / InstallShield / 7z 自解压 / MSI），默认**向导模式全自动点击**「开始/继续/下一步/安装/完成」，自动勾选“接受协议”，自动填安装目录（默认 D:\），**绝不点取消**，中英文界面均支持；安装结束**等待并确认**（进程树退出或完成页关闭）后才继续下一步 |
| 3+ | ⏺ 操作录制与回放 | 对任意安装/卸载/配置程序：点「⏺ 开始录制」→ **像平时一样手动点一遍**（按钮点击、输入的文字、下拉/列表选择、回车都会被记录）→「✔ 完成并保存」自动存为脚本（记住程序路径）；**勾选脚本后点「开始执行」即自动回放**（勾选状态保存进配置文件，可多选、可调回放速度），适合通用规则点不了的定制安装器 |
| 4 | 🖨️ 打印机纸张设置 | 自动读取打印机列表（EnumPrinters + 注册表兜底，也可手动输入名称）→ 添加指定纸张模板 → 设为该打印机**默认纸张并读回校验**（写入完整 DEVMODE：纸名+宽高）→ 一键**打印测试纸**（直接用自定义纸张的 DEVMODE 打印，确保按你创建的纸张尺寸输出；测试内容按纸张大小自适应，避免“纸张小于行高”报错）；**若同时启用驱动安装，本任务一定在驱动安装成功后才执行**，并自动等待打印机出现（驱动注册有延迟时） |
| 5 | ▶ 一键执行 | 点击「开始执行」等待完成；成功弹「配置完成」，失败逐条列出失败原因 |
| 6 | 💾 多命名配置文件 | 所有设置可预先保存为多个命名配置；支持新建/另存为/重命名/删除/导入/导出；双击 exe 打开界面选配置执行，或 `-r "配置名"` 直接执行 |
| 8 | 🎨 美观界面 | customtkinter 现代界面，亮/暗/跟随系统三主题，侧边栏配置管理 + 标签页任务 + 彩色运行日志 |
| 9 | 🧩 扩展功能 | ① 覆盖前**自动备份**被替换文件；② 每次运行生成**日志文件**；③ 🚀 **一键运行快捷方式**（双击即执行指定配置）；④ 标签机 **RAW 文本打印**模式；⑤ 配置文件**导入/导出**；⑥ 崩溃自动记录日志；⑦ 任务框架化，新增模块 = 新增一个类 |

## 📁 目录结构

```
deploy_tool/
├── main.py                  # 入口：GUI / -r 直接执行 / --list
├── app/
│   ├── core.py              # 任务框架（BaseTask）+ 执行引擎 Engine
│   ├── config_store.py      # 命名配置的存取（JSON）
│   ├── util.py              # 路径/桌面/启动文件夹/错误提示翻译
│   ├── ui_helpers.py        # 界面小组件封装
│   ├── gui.py               # 主界面（customtkinter）
│   ├── headless.py          # -r 无界面执行器（轻量进度窗口）
│   └── tasks/               # ★ 功能模块目录（新增功能放这里）
│       ├── copy_task.py     #   复制文件（文件夹/压缩包，可先复制再解压）
│       ├── driver_task.py   #   驱动一键安装（自动点击 / 脚本回放 / 静默安装）
│       ├── _autoclick.py    #   安装向导自动点击器（下一步/安装/填目录）
│       ├── _recorder.py     #   操作录制（全局鼠标/键盘钩子）与脚本回放
│       ├── record_task.py   #   「操作录制」标签页（录制/勾选随配置执行/回放）
│       ├── shortcut_task.py #   快捷方式、开机自启（多程序）
│       ├── printer_task.py  #   打印机纸张模板/默认纸张/测试打印
│       ├── extra_tasks.py   #   一键运行快捷方式
│       └── _fsutil.py       #   复制/解压/备份底层实现
├── tests/smoke.py           # 冒烟测试
├── tests/fake_installer.py  # 模拟安装向导（纯 Win32，自检自动点击用，不改系统）
├── tests/test_autoclick.py  # 自动点击回归自检（无需真实安装包）
├── make_icon.py             # 生成 icon.ico（可跳过）
├── requirements.txt
├── build.bat                # ★ 一键打包 exe（主版本，Win8.1+）
├── build_win7.bat           # ★ 一键打包 Win7 专用版（Python 3.8 / 32 位）
├── win7build/py38/          # Win7 版构建环境（Python 3.8.10 32 位，conda 包组装）
├── dist/                    # 主版本产物（部署助手.exe）
├── dist_win7/               # Win7 专用版产物（部署助手_Win7.exe + UCRT 运行库）
└── README.md
```

## 🚀 快速开始（源码运行）

```bat
:: 1. 安装依赖（需要 Python 3.8+）
pip install -r requirements.txt

:: 2. 运行
python main.py
```

## 📦 打包成 EXE（两种方式）

### 方式一：一键打包（推荐）

双击运行 `build.bat`，等待 1~3 分钟，产物在 **`dist\部署助手.exe`**。
把该 exe 复制到任何文件夹即可使用（配置文件会生成在 exe 旁边的 `configs\` 目录）。

### 方式二：手动命令

```bat
pip install -r requirements.txt pyinstaller
python make_icon.py          :: 可选，生成图标

:: 单文件版（双击即用，启动稍慢）
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name "部署助手" --icon icon.ico ^
  --collect-all customtkinter ^
  --hidden-import win32com --hidden-import win32com.client ^
  --hidden-import win32print --hidden-import win32api --hidden-import win32con ^
  main.py

:: 目录版（启动更快、更不容易被杀软误报；整个 dist\部署助手 文件夹一起分发）
python -m PyInstaller --noconfirm --clean --noconsole ^
  --name "部署助手" --icon icon.ico ^
  --collect-all customtkinter main.py
```

打包说明：

- `--noconsole`：不显示黑色控制台窗口（本工具全部通过弹窗反馈）。
- `--onefile`：打包成单个 exe；`--onedir` 模式启动更快。
- 图标可用 `make_icon.py` 生成，也可以换成你自己的 `icon.ico`。

## 🖱️ 使用说明

### 图形界面

1. 双击 `部署助手.exe` 打开主界面；
2. 左侧点「➕ 新建」，顶部输入配置名称（如 `打印机店部署A`）；
3. 在标签页里填写任务，例如：
   - **📦 复制文件**：选源（文件夹/压缩包）和目标目录 → 勾选“覆盖前自动备份”；源是压缩包时还可勾选
     **“先复制压缩包到目标文件夹、再解压到该文件夹”**（加速大量小文件复制），并可选择解压后
     是否删除目标处的压缩包副本；
   - **🔗 快捷方式与开机自启**：点「➕ 添加」可加入**多个程序**，在左侧列表切换，
     逐个设置 exe、快捷方式名称、启动参数、图标，以及是否创建桌面快捷方式/开机自启；
   - **🔧 驱动一键安装**：勾选启用 → 选安装程序（.exe / .msi / .bat）→ 安装目录默认
     `D:\`（向导中出现目录选择时自动填入）。执行时自动识别安装包类型并**全自动点击向导**
     （下一步/开始安装/继续/完成、自动勾选“接受协议”、绝不点「取消」），安装结束后
     **等待并确认安装完成**才继续后面的任务。**若该程序有录制脚本，执行时会自动回放脚本**
     （回放完毕自动点击兜底；可在「高级选项」关闭）。静默参数、超时、完成校验也在
     「高级选项」里（默认收起，一般不用改）；
   - **⏺ 操作录制与回放**（「操作录制」标签页）：对任意安装/卸载/配置程序，
     ① 选目标程序（仅录制时需要，会记住上次选择的程序）→ ② 点「⏺ 开始录制」→
     ③ **像平时一样手动把流程完整点一遍**（点击、输入、下拉选择都会被记录，
     只记录该程序的窗口，不影响其它操作）→ ④ 点「✔ 完成并保存」**自动保存脚本**
     （脚本记住程序路径，回放时自动定位该程序）；
     脚本列表可「▶ 回放」（可选 1x/2x/5x 速度）、「🗑 删除」，并支持**勾选多个脚本**——
     **勾选状态保存进配置文件**，点「▶ 开始执行」时按顺序自动回放所有勾选的脚本；
     脚本存在 `scripts\` 目录，按程序内容自动匹配（换机器也能对上）；
   - **🖨️ 打印机纸张设置**：下拉选打印机（自动读取，也可手动输入名称）→ 填纸张名称与宽高（mm）→ 勾选“设为默认纸张”→ 点「🖨 打印测试纸」试打（测试纸按你创建的纸张尺寸打印，内容会自适应纸张大小）；
     若同一配置里也启用了驱动安装，本任务**一定在驱动安装成功后执行**，并自动等待打印机出现（最多 60 秒）；
4. 点「💾 保存」，配置出现在左侧列表；
5. 点右上角「▶ 开始执行」，进度条结束后弹窗提示 **配置完成** 或 **失败原因**；
6. 运行日志显示在底部，并同步保存到 `logs\` 目录。

> 💡 驱动安装一般需要管理员权限：请**右键以管理员身份运行**本工具，
> 否则安装程序可能弹 UAC 提示或直接失败。

### 命令行 / 直接执行

```
部署助手.exe                        打开配置界面
部署助手.exe -r "配置名"             直接执行该配置（弹进度窗口，完成后弹结果）
部署助手.exe 某配置文件.json         直接执行指定配置文件
部署助手.exe --list                 弹窗列出所有配置
```

### 一键运行

在「🚀 一键运行快捷方式」标签页勾选启用，执行后桌面上会生成
「配置名·一键运行」快捷方式——以后**双击它就自动执行整个配置**，
完全不用打开界面。

## 📂 数据存放位置

- 配置文件：`exe 所在目录\configs\*.json`（目录不可写时自动回退到 `%APPDATA%\DeployTool\configs`）
- 运行日志：`exe 所在目录\logs\run_时间.log`
- 覆盖备份：`exe 所在目录\backups\时间戳_xx\`

## 🪟 Windows 7 专用版

主版本 `dist\部署助手.exe` 用 Python 3.14 打包，**不支持 Windows 7**（Python 3.9 起
官方不再支持 Win7，3.8 是最后支持 Win7 的版本）。Win7 上运行主版本会报：

```
Failed to load Python DLL python314.dll / LoadLibrary: 找不到指定的模块
```

所以项目里用 **Python 3.8.10（32 位）** 单独打包了 Win7 专用版（32 位 exe 在
32 位和 64 位 Win7 上都能运行），位于 **`dist_win7\`**，与主版本互不影响：

| 文件 | 说明 |
|------|------|
| `dist_win7\部署助手_Win7.exe` | 单文件版 |
| `dist_win7\部署助手_Win7\` | 目录版（Win7 上建议优先用它，启动快、不易误报） |
| `dist_win7\Windows7通用C运行库_ucrt.msi` | Win7 运行库补丁（见下） |

### Win7 上使用前的准备

1. **Service Pack 1**：Win7 需已安装 SP1；
2. **通用 C 运行库（UCRT）**：若双击 exe 报缺少 `api-ms-win-crt-*.dll`，
   双击安装 `dist_win7\Windows7通用C运行库_ucrt.msi`（需管理员），重启后再运行；
3. 打印机纸张设置等需要管理员权限的操作，请**右键以管理员身份运行**。

> 💡 Win7 版已内置 `api-ms-win-core-sysinfo-l1-2-0.dll` 兼容存根
> （把新版 API 转发到 Win7 上存在的 kernel32 函数），
> 启动时不会再弹「找不到 api-ms-win-core-sysinfo-l1-2-0.dll」。

### 重新打包 Win7 版

双击 **`build_win7.bat`**（使用 `win7build\py38` 里的 Python 3.8 32 位构建环境，
环境由 conda 包组装而成、不依赖系统安装；输出到 `dist_win7\`，不覆盖主版本）。
注意：Win7 版未内置 7z 解压（zip/tar/gz/bz2/xz 均可正常使用，选 7z 时会提示原因）。

## ❓ 常见问题

| 问题 | 解决 |
|------|------|
| 添加纸张模板/设默认纸张报“拒绝访问” | 打印机管理需要权限，**右键以管理员身份运行**本工具 |
| 杀毒软件误报 / SmartScreen 提示 | PyInstaller 单文件版常见现象：添加信任即可；介意的话改用 `--onedir` 打包或对 exe 做代码签名 |
| Win7 报 python314.dll 找不到 | 请使用 `dist_win7\` 里的 **Win7 专用版**；主版本仅支持 Win8.1+ |
| Win7 报 api-ms-win-crt-*.dll 缺失 | 安装 `dist_win7\Windows7通用C运行库_ucrt.msi` 并重启 |
| Win7 报 api-ms-win-core-sysinfo-l1-2-0.dll 缺失 | 新版 Win7 专用版已内置兼容存根，直接换用最新的 `dist_win7` 产物即可 |
| 驱动安装弹 UAC / 安装失败 | 驱动安装需要管理员权限，请**右键以管理员身份运行**本工具；安装目录不存在时（如无 D 盘）工具会改用系统盘 |
| 驱动安装向导没被自动点击 | 自动点击已支持中英文标准控件与 UIA（DirectUI/WPF/自绘界面），同一窗口翻多页的“属性表向导”也会逐页点击。若个别安装程序仍无法自动点击，日志会提示超时与原因；可在「高级选项」里填该安装器支持的静默参数，或手动安装 |
| 没装完就报“完成” | 新版只在页面出现“安装完成/成功”字样时才点「完成」；禁用的按钮会等待其变为可用；页面出现“失败/未检测到/需要管理员”等提示时如实报告失败原因，绝不假报成功 |
| 安装已完成但工具报“未完成” | 完成判定 = 安装进程树全部退出 **或** 点击「完成」后向导窗口确实关闭（若「完成」点击未生效会自动重试）。若安装器残留托盘/监视进程，工具会在界面安静后判定完成并在日志注明 |
| 刚装完打印驱动却找不到打印机 | 打印机纸张设置任务会**在驱动安装成功后**才执行，并自动等待打印机出现（最多 60 秒）；若仍找不到，请确认打印机已连接并开机。驱动安装失败时纸张设置任务会**自动跳过**并说明原因。打印驱动包装完后工具还会校验系统中是否出现新的打印驱动（没有且无完成页 → 判定安装失败） |
| 在受限沙箱里 `pip install` 报 Permission denied | 部分沙箱与 Python 3.14 的目录权限（mkdir mode 0o700）冲突；可用带 `--system-site-packages` 的 venv，并在 venv 的 site-packages 放一个把 `tempfile.mkdtemp` 改为默认 mode 的 `sitecustomize.py`（本项目开发时的 `.venv` 即如此处理）。普通用户机器不受影响 |
| 打开 7z 压缩包报缺少 py7zr | 执行 `pip install py7zr`（requirements 已包含；Win7 版未内置，请用 zip/tar） |
| RAR 压缩包 | 暂不支持，请先解压或转为 zip |
| 开机自启没生效 | 按 `Win+R` 输入 `shell:startup` 检查启动文件夹里是否有快捷方式；注册表方式在 `HKCU\...\Run` 查看 |
| 打印测试纸打到别的打印机 | 工具会临时切换默认打印机并自动恢复；若打印期间被其他程序抢占，可改用「标签机 RAW 文本模式」 |
| 想同时配置多台机器 | 把配置 `📤 导出` 为 json，带到目标机器 `📥 导入` 即可 |

## 🧩 二次开发：新增一个功能模块（三步）

1. 在 `app/tasks/` 下新建文件（如 `app/tasks/clean_task.py`）：

```python
# -*- coding: utf-8 -*-
"""任务：清理临时文件"""
import os
from tkinter import BooleanVar, StringVar

from ..core import BaseTask, TaskError, register
from .. import util
from .. import ui_helpers as ui


@register
class CleanTask(BaseTask):
    key = "clean_temp"          # 配置里的唯一键
    title = "清理临时文件"        # 标签页标题
    icon = "🧽"                 # 标签页图标
    order = 95                  # 执行顺序（越小越先）

    def default_cfg(self):
        return {"enabled": False, "folder": ""}

    def run(self, cfg, log):
        folder = (cfg.get("folder") or "").strip()
        if not folder:
            raise TaskError("未指定要清理的文件夹")
        if not os.path.isdir(folder):
            raise TaskError(f"文件夹不存在：{folder}")
        count = 0
        for root, _dirs, files in os.walk(folder):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                    count += 1
                except OSError:
                    pass
        log(f"已清理 {count} 个文件")

    # ---- 界面三件套：build_tab / load_ui / collect_ui ----
    def build_tab(self, tab, app):
        tab.grid_columnconfigure(1, weight=1)
        self.v = {"en": BooleanVar(value=False), "folder": StringVar()}
        ui.hint(tab, "清空指定文件夹内的所有文件（慎用）。").grid(
            row=0, column=0, columnspan=3, padx=16, pady=(16, 4), sticky="w")
        ui.check(tab, self.v["en"], "启用此任务").grid(
            row=1, column=0, columnspan=3, padx=(16, 6), pady=8, sticky="w")
        ui.label(tab, "目标文件夹").grid(row=2, column=0, padx=(16, 6), pady=8, sticky="w")
        ui.entry(tab, self.v["folder"]).grid(row=2, column=1, padx=6, pady=8, sticky="ew")
        ui.button(tab, "浏览…", lambda: ui.browse_dir(self.v["folder"])).grid(
            row=2, column=2, padx=(6, 16), pady=8)

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", False)))
        self.v["folder"].set(cfg.get("folder", ""))

    def collect_ui(self, cfg):
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["folder"] = self.v["folder"].get().strip()
```

2. 在 `app/tasks/__init__.py` 加一行：

```python
from . import clean_task   # 清理临时文件
```

3. 重新打包。界面会自动多出一个「🧽 清理临时文件」标签页，执行引擎自动按 `order` 顺序运行它。

## 🔧 技术要点

- **UI**：customtkinter（现代扁平风，零图片资源）；
- **打印机**：pywin32（`AddForm`/`SetForm` 增改纸张模板，`SetPrinter` 写入 `pDevMode.dmFormName`
  设默认纸张，`DMPAPER_USER` 自定义纸张）；
- **测试打印**：临时切默认打印机 → 系统打印 → 等队列入队/清空 → 自动恢复原默认打印机；
  另有 RAW 直写模式适配标签机；
- **快捷方式**：WScript.Shell COM 写 `.lnk`；启动文件夹（当前用户/所有用户）与
  `HKCU\...\Run` 注册表两种自启方式；
- **自动安装（v2）**：安装包类型识别（文件特征串）→ 向导驱动模式为主：
  ① Win32 标准控件文字匹配（中/英黑名单与白名单，前缀匹配 + 危险词子串兜底，绝不点取消）
  ② UIA（UI Automation，pywin32 迟绑定，Win7 自带 UIAutomationCore）覆盖 DirectUI/WPF/自绘
  ③ DM_GETDEFID 默认按钮 ④ 回车兜底；每个控件每页只操作一次（避免双击跳页），
  鼠标点击前校验坐标归属窗口（不盲点）。完成判定 = 进程树退出 或 “完成页点击后向导窗口确认关闭”
  （未生效自动重试），残留托盘进程不再误判失败；超时改为“无活动超时”（长时间正常安装不误杀）；
- **任务依赖**：`BaseTask.requires` 声明前置任务；前置任务失败时本任务自动跳过并注明原因
  （打印机纸张设置依赖驱动安装）；
- **执行引擎**：任务顺序执行、失败不中断、统一汇报；每次运行落盘日志；
- **打包**：PyInstaller `--onefile --noconsole`，`--collect-all customtkinter` 保证主题资源齐全；
  Win7 版用 Python 3.8 32 位 + `win7build\py38` 内置构建环境（`build_win7.bat`）；
- **操作录制与回放**：`WH_MOUSE_LL` / `WH_KEYBOARD_LL` 全局钩子只记录目标进程树窗口上的
  用户操作（按钮点击+期望勾选状态、编辑框最终文本、下拉/列表选中项、回车），保存为
  `scripts\<安装包名>_<大小>_<哈希>.json`；回放按（窗口标题 → 控件类名+文字）逐步匹配，
  匹配失败退回录制的相对坐标点击，回放完毕自动切换通用自动点击器兜底；
- **自检**：`tests/fake_installer.py`（纯 Win32 模拟安装向导）+ `tests/test_autoclick.py`
  一键回归自动点击逻辑；`tests/fake_uninstaller.py` + `tests/test_record_replay.py`
  一键回归“录制 → 保存脚本 → 全新进程回放”（均不产生系统改动）。
