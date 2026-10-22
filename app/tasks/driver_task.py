# -*- coding: utf-8 -*-
"""任务：驱动程序/软件一键安装（v2）。

策略（对应“点开安装程序后自动点击开始/继续/下一步，并等待确认安装完成”）：
  1. 识别安装包类型（MSI / Inno Setup / NSIS / InstallShield / 7z 自解压 / 其它）；
  2. 默认“向导驱动”模式：以最小安全参数启动安装程序，由自动点击器全程点击
     「开始/继续/下一步/安装/完成」，自动勾选“接受协议”，自动填安装目录，
     绝不点「取消」（中英文向导均支持，DirectUI/自绘界面走 UIA）；
  3. 用户自定义静默参数时先按参数静默安装，失败自动退回向导模式；
  4. 完成判定：安装进程树全部退出，或点击到「完成/结束」页且界面安静一段时间；
     残留后台进程（托盘/监视程序）不再误判为“未完成”；
  5. 全程“无活动超时”（向导卡住才报超时，长时间正常安装不会被误杀）；
  6. 安装结束后可选校验指定文件/目录是否出现，并提示打印机驱动装好后
     纸张设置任务会自动等待打印机出现。
"""
import os
import subprocess
import threading
import time
from tkinter import BooleanVar, StringVar

import customtkinter as ctk

from ..core import BaseTask, TaskError, register
from .. import util
from .. import ui_helpers as ui
from . import _autoclick
from . import _recorder

# 旧版默认参数（一堆互斥参数混在一起，很多安装器会报错/挂起）→ 现在视为“未设置”
LEGACY_COMBINED_ARGS = "/S /silent /verysilent /quiet /qn"
OK_EXIT_CODES = (0, 3010, 1641)   # 0=成功 3010/1641=成功但需重启
ERROR_ELEVATION_REQUIRED = 740    # 需要管理员权限（UAC）
FINISH_GRACE_SECONDS = 8.0        # 点击「完成」后允许界面安静的宽限时间
QUIET_LINGER_SECONDS = 15.0       # 主进程已退出但残留后台进程时的安静宽限时间
DEFAULT_TIMEOUT = 300             # 无活动超时（秒）


def _normalize_install_dir(d):
    d = (d or "D:\\").strip().strip('"')
    if not d.endswith("\\"):
        d += "\\"
    return d


def _is_msi(path):
    return path.lower().endswith(".msi")


def _file_contains(path, patterns, max_bytes=2 * 1024 * 1024):
    """在文件前 max_bytes 字节内查找 ASCII / UTF-16 特征串，返回命中集合"""
    found = set()
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes)
    except OSError:
        return found
    for pat in patterns:
        raw = pat.encode("ascii", "ignore")
        if raw in data:
            found.add(pat)
        utf16 = pat.encode("utf-16-le", "ignore")
        if utf16 in data:
            found.add(pat)
    return found


def detect_installer_type(path):
    """识别安装包类型：msi / inno / nsis / installshield / 7zsfx / unknown"""
    if _is_msi(path):
        return "msi"
    hits = _file_contains(path, ("Inno Setup", "Nullsoft", "InstallShield",
                                 "7-Zip", "7z Setup SFX", "Squirrel"))
    if "Inno Setup" in hits:
        return "inno"
    if "Nullsoft" in hits:
        return "nsis"
    if "InstallShield" in hits:
        return "installshield"
    if "7-Zip" in hits or "7z Setup SFX" in hits:
        return "7zsfx"
    if "Squirrel" in hits:
        return "squirrel"
    return "unknown"


def _minimal_args(kind):
    """向导驱动模式下附加的最小安全参数（绝不塞可能报错的静默参数）"""
    if kind == "inno":
        return ["/SP-"]  # 跳过 Inno“本程序将安装…是否继续”确认页
    return []


def _silent_args_for(kind, install_dir):
    """自动点击关闭时的静默参数（按类型给正确参数，不再一堆参数互斥混用）"""
    d = _normalize_install_dir(install_dir)
    if kind == "inno":
        return ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                "/DIR=%s" % d.rstrip("\\")]
    if kind == "nsis":
        return ["/S"]
    if kind == "squirrel":
        return ["-s", "--silent"]
    return None  # 其它类型没有可靠的通用静默参数


def _run_msi(msi, install_dir, log, verify_path):
    """msiexec 静默安装（MSI 最可靠的装法）"""
    props = 'INSTALLDIR="%s" INSTALLLOCATION="%s" TARGETDIR="%s" ALLUSERS=1' % _normalize_install_dir(install_dir)
    cmd = ["msiexec", "/i", msi, "/qn", "/norestart", props]
    log("执行：%s ..." % " ".join(cmd[:4]))
    try:
        proc = subprocess.Popen(cmd)
        code = proc.wait()
    except Exception as e:
        raise TaskError("无法启动安装程序：%s" % util.error_hint(e))
    if code in OK_EXIT_CODES:
        log("MSI 安装完成（退出码 %s）" % code)
    else:
        raise TaskError("安装失败，退出码 %s。请以管理员身份运行后重试，或手动安装" % code)
    _verify_target(verify_path, log)


def _verify_target(verify_path, log):
    """安装完成后校验指定文件/目录（可选）"""
    verify_path = (verify_path or "").strip()
    if not verify_path:
        return
    if os.path.exists(verify_path):
        log("校验通过：%s 已存在" % verify_path)
    else:
        raise TaskError("安装程序已结束，但未找到校验目标：%s\n"
                        "（安装可能未真正完成，请检查安装程序）" % verify_path)


def _is_printer_driver_package(installer):
    """判断安装包是否为打印机驱动包（文件名/所在目录名/旁边是否有驱动文件）"""
    base = os.path.basename(installer).lower()
    folder = os.path.dirname(installer) or ""
    folder_low = folder.lower()
    keys = ("驱动", "driver", "printer", "打印")
    if any(k in base for k in keys):
        return True
    if folder:
        if any(k in folder_low for k in keys):
            return True
        if any(k in os.path.basename(folder).lower() for k in keys):
            return True
        # 旁边有“打印机类”驱动 INF（Class=Printer / 打印机类 GUID）才算打印驱动包
        try:
            entries = os.listdir(folder)
        except OSError:
            entries = []
        for e in entries:
            if not e.lower().endswith(".inf"):
                continue
            try:
                with open(os.path.join(folder, e), "rb") as f:
                    head = f.read(4096).decode("utf-8", "ignore").lower()
            except OSError:
                continue
            if "class=printer" in head or "4d36e979-e325-11ce-bfc1-08002be10318" in head:
                return True
    return False


def _installed_printer_drivers():
    """返回系统当前已安装的打印机驱动名称集合（无法枚举时返回 None）"""
    try:
        import win32print
        infos = win32print.EnumPrinterDrivers(None, None)
        names = set()
        for info in infos or []:
            try:
                names.add(str(info[1] or ""))
            except Exception:
                pass
        return names
    except Exception:
        return None


def _run_exe(installer, kind, silent_args, install_dir, timeout, auto_click,
             verify_path, log, script_steps=None, replay_speed=1.0):
    """exe 安装主流程：向导驱动优先 + 静默回退 + 双重完成确认 + 无活动超时。

    script_steps：录制脚本步骤。非空时先按脚本回放用户录制的操作，
    回放完毕后再交由通用自动点击器兜底。replay_speed：回放速度倍数。
    """
    custom_args = [a for a in (silent_args or "").split() if a]
    if silent_args and silent_args.strip() == LEGACY_COMBINED_ARGS:
        custom_args = []  # 旧版默认互斥参数视为未设置
    is_bat = installer.lower().endswith((".bat", ".cmd"))
    cwd = os.path.dirname(installer) or None

    def _cmd(extra):
        if is_bat:
            return ["cmd", "/c", installer] + list(extra)
        return [installer] + list(extra)

    # ---- 决定启动方式 ----
    if custom_args:
        first_cmd = _cmd(custom_args)
        first_desc = "（静默参数：%s）" % " ".join(custom_args)
    elif not auto_click:
        sa = _silent_args_for(kind, install_dir)
        if sa is None:
            raise TaskError("该安装程序类型无法可靠静默安装，请勾选「自动点击安装向导」，"
                            "或自行填写静默参数后重试。")
        first_cmd = _cmd(sa)
        first_desc = "（静默安装：%s）" % " ".join(sa)
    else:
        first_cmd = _cmd(_minimal_args(kind))
        first_desc = "（向导模式，自动点击）"

    state = {"baseline": _autoclick.snapshot_windows(), "own_pid": os.getpid(),
             "windows": {}, "clicked": set(), "set_edits": set(),
             "ok_sent": set(), "uia_clicked": set(), "uia_toggled": set(),
             "uia_filled": set()}

    def _launch(command):
        return subprocess.Popen(command, cwd=cwd)

    log("启动安装程序：%s%s" % (os.path.basename(installer), first_desc))
    try:
        proc = _launch(first_cmd)
    except Exception as e:
        raise TaskError("无法启动安装程序：%s" % util.error_hint(e))

    # 进程树观察线程：高频记录安装程序的所有子进程 pid（含短命子进程）
    seen_pids = {proc.pid}
    stop_watch = threading.Event()

    def _watch():
        while not stop_watch.is_set():
            try:
                seen_pids |= _autoclick.process_tree(proc.pid)
            except Exception:
                pass
            time.sleep(0.25)

    threading.Thread(target=_watch, daemon=True).start()

    inactivity_limit = max(30, int(timeout or DEFAULT_TIMEOUT))
    hard_cap = inactivity_limit * 6
    start = time.time()
    last_event = time.time()
    finish_clicked_at = None   # 点过「完成」的时刻（尚未确认向导关闭）
    finish_hwnds = set()       # 点「完成」时正在显示的向导窗口（须确认它们关闭）
    done_latch = False         # 已确认完成页关闭，进入收尾等待，不再点击任何控件
    window_ids = set()   # 见过的目标窗口集合（出现新窗口 = 有进展）
    retried = bool(custom_args)  # 带参数启动过一次，失败后允许退回纯向导
    replay_runner = _recorder.ReplayRunner(script_steps, log, speed=replay_speed) if script_steps else None
    replay_done = False

    def _target_hwnds():
        return set(h for h, _p, _t in
                   _autoclick.visible_tree_windows(seen_pids, state["baseline"], state))

    log("等待安装完成（无活动超过 %s 秒判定超时；总时长上限 %s 分钟）…"
        % (inactivity_limit, int(hard_cap / 60)))
    try:
        while True:
            now = time.time()
            code = proc.poll()

            # 主进程已退出且退出码异常 → 若带过参数且未重试过，退回纯向导再试
            if code is not None and code not in OK_EXIT_CODES:
                if retried and code != ERROR_ELEVATION_REQUIRED:
                    retried = False
                    state["baseline"] = _autoclick.snapshot_windows()
                    log("带参数运行失败（退出码 %s），改为直接运行安装向导并自动点击…" % code)
                    try:
                        proc = _launch(_cmd(_minimal_args(kind)))
                    except Exception as e:
                        raise TaskError("无法重新启动安装程序：%s" % util.error_hint(e))
                    seen_pids |= {proc.pid}
                    last_event = now
                    finish_clicked_at = None
                    done_latch = False
                    continue
                if code == ERROR_ELEVATION_REQUIRED:
                    raise TaskError("安装程序需要管理员权限（UAC）。请【右键以管理员身份运行】"
                                    "本工具后重试。")
                raise TaskError("安装失败，退出码 %s。请以管理员身份运行后重试，或手动安装" % code)

            # 安装程序报错/受阻（页面出现“失败/未检测到/需要管理员”等提示）→ 立即如实报告
            blocker = _autoclick.scan_blocker(seen_pids, state)
            if blocker:
                state["blocker"] = blocker
            if state.get("blocker"):
                blocker = str(state["blocker"]).strip()
                log("安装程序提示：%s" % blocker)
                raise TaskError("安装程序报告：%s\n（安装未完成，请按提示处理）" % blocker)

            # ---- 自动点击状态机 ----
            # active：正常点击推进向导
            # finish_wait：点过「完成」，等待向导窗口真正关闭（没关掉说明点击未生效 → 重试）
            # done_latch：已确认完成页关闭，之后绝不再点击（避免点到“安装完自动启动”的应用窗口）
            if not done_latch and finish_clicked_at is None and (auto_click or script_steps is not None):
                if script_steps is not None and not replay_done:
                    # 先回放录制的操作，回放完毕自动切换为通用自动点击兜底
                    acts = replay_runner.tick(seen_pids, state)
                    for a in acts:
                        log(a)
                    if acts:
                        last_event = now
                    if replay_runner.done:
                        replay_done = True
                        log("回放完毕，剩余页面交由通用自动点击器兜底…")
                elif auto_click:
                    actions, saw_finish = _autoclick.autoclick_once(
                        seen_pids, install_dir, state)
                    for a in actions:
                        log(a)
                    if actions:
                        last_event = now
                    if saw_finish:
                        finish_clicked_at = now
                        finish_hwnds = _target_hwnds()
                        log("已点击「完成/结束」：确认向导窗口关闭中…")
            elif finish_clicked_at is not None and not done_latch:
                remaining = finish_hwnds & _target_hwnds()
                if not remaining:
                    done_latch = True
                    last_event = now
                    log("安装向导已关闭 ✓，等待后台进程收尾…")
                elif now - finish_clicked_at > 5.0:
                    # 「完成」点击未生效（例如按钮当时未启用）→ 重置点击记录重试
                    for h in remaining:
                        rec = state["windows"].get(h)
                        if rec:
                            rec["clicked"].clear()
                            rec["toggled"].clear()
                            rec["last_action"] = 0.0
                    finish_clicked_at = None
                    log("「完成」点击未生效（向导未关闭），重试…")

            # 新窗口/新子进程 = 有进展
            cur_windows = _autoclick.visible_tree_windows(seen_pids, state["baseline"], state)
            cur_ids = set(h for h, _p, _t in cur_windows)
            if cur_ids - window_ids:
                window_ids |= cur_ids
                last_event = now
                if not done_latch:
                    finish_clicked_at = None  # 又出现了新页面，取消“完成”判定
            new_pids = _autoclick.process_tree(proc.pid) - seen_pids
            if new_pids:
                seen_pids |= new_pids
                last_event = now

            children_alive = [p for p in seen_pids if p != proc.pid and _autoclick.pid_running(p)]

            # ---- 完成判定 ----
            if code is not None and not children_alive:
                log("安装程序及其子进程均已结束（退出码 %s）✓" % code)
                break
            if done_latch and now - last_event > FINISH_GRACE_SECONDS:
                # 完成页已关闭且界面安静：无论主进程/后台进程是否残留都视为完成
                if code is not None:
                    log("安装向导已关闭且界面安静（主进程退出码 %s），视为安装完成 ✓" % code)
                else:
                    log("安装向导已关闭且界面安静，视为安装完成 ✓")
                break
            if code is not None and not cur_windows and now - last_event > QUIET_LINGER_SECONDS:
                # 主进程已退出、子进程残留且无任何窗口：视为完成
                log("安装主进程已结束（退出码 %s）；仍有后台进程运行"
                    "（可能是托盘/监视程序），视为安装完成。" % code)
                break

            # ---- 超时判定（无活动超时 + 总时长硬上限） ----
            if now - last_event > inactivity_limit:
                raise TaskError(
                    "安装超时：向导 %s 秒内没有任何进展（未出现新窗口、未点击到按钮）。\n"
                    "可能原因：安装程序界面特殊、或正在等待输入/下载/连接设备。\n"
                    "建议：检查安装程序是否需要手动操作，或调整「高级选项-超时」。" % inactivity_limit)
            if now - start > hard_cap:
                raise TaskError("安装超过最长时限 %s 分钟仍未完成，已停止等待。" % int(hard_cap / 60))

            time.sleep(0.5)
    finally:
        stop_watch.set()

    _verify_target(verify_path, log)
    # 返回是否出现“安装完成”页（供打印驱动包校验使用）
    return {"saw_completion": bool(state.get("saw_completion_text"))}


def run_installer_replay(installer, steps, timeout, log, install_dir="C:\\",
                         auto_click=True, speed=1.0):
    """按录制脚本启动程序并回放（供「操作录制」标签页使用）。

    复用驱动安装主流程：回放完脚本后交由通用自动点击器兜底，
    完成后同样等待并确认进程退出。speed：回放速度倍数（1/2/5）。
    """
    if _is_msi(installer):
        raise TaskError("MSI 安装包没有交互界面，不支持录制回放，请直接使用静默安装。")
    kind = detect_installer_type(installer)
    _run_exe(installer, kind, "", install_dir, int(timeout or DEFAULT_TIMEOUT),
             auto_click, "", log, list(steps), replay_speed=speed)


@register
class DriverInstallTask(BaseTask):
    """驱动/软件一键安装"""
    key = "driver_install"
    title = "驱动安装"
    icon = "🔧"
    order = 38  # 在打印机纸张设置(40)之前执行：先装驱动，打印机才能被识别

    def default_cfg(self):
        return {"enabled": False, "installer": "", "install_dir": "D:\\",
                "silent_args": "", "timeout_seconds": DEFAULT_TIMEOUT,
                "auto_click": True, "verify_path": "",
                "use_script": True, "script_path": ""}

    def run(self, cfg, log):
        installer = (cfg.get("installer") or "").strip()
        if not installer:
            raise TaskError("未指定驱动安装程序")
        if not os.path.isfile(installer):
            raise TaskError("安装程序不存在：%s" % installer)
        install_dir = _normalize_install_dir(cfg.get("install_dir") or "D:\\")
        silent_args = (cfg.get("silent_args") or "").strip()
        try:
            timeout = int(cfg.get("timeout_seconds") or DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        auto_click = bool(cfg.get("auto_click", True))
        verify_path = (cfg.get("verify_path") or "").strip()

        if not os.path.isdir(install_dir):
            log("安装目录 %s 不存在（可能无 D 盘），将使用 %s\\"
                % (install_dir, os.environ.get("SystemDrive", "C:")))

        if not _autoclick.is_admin():
            log("⚠ 当前未以管理员身份运行：安装程序可能弹 UAC 或直接失败，"
                "建议【右键以管理员身份运行】本工具。")

        kind = detect_installer_type(installer)
        is_printer_pkg = _is_printer_driver_package(installer)
        if is_printer_pkg:
            log("安装包类型：%s（打印机驱动包：安装完成后会校验驱动并等待打印机出现）" % kind)
        else:
            log("安装包类型：%s" % kind)

        # ---- 录制脚本：执行时自动回放（有脚本且未关闭时） ----
        mode = (cfg.get("mode") or "").strip()          # 兼容旧配置的“回放录制脚本”模式
        use_script = bool(cfg.get("use_script", True))
        script_steps = None
        if mode == "replay" or use_script:
            sp = (cfg.get("script_path") or "").strip() or _recorder.find_script(installer)
            if sp:
                try:
                    script = _recorder.load_script(sp)
                    script_steps = list(script.get("steps") or [])
                except Exception as e:
                    if mode == "replay":
                        raise TaskError("录制脚本读取失败：%s（%s）" % (sp, util.error_hint(e)))
                    log("录制脚本读取失败（忽略）：%s" % e)
                    script_steps = None
                if script_steps:
                    name = script.get("display_name") or os.path.basename(sp)
                    log("检测到录制脚本「%s」（%s 个操作），将自动回放；"
                        "回放完毕后由通用自动点击器兜底。" % (name, len(script_steps)))
        if mode == "replay" and not script_steps:
            raise TaskError("回放模式需要录制脚本：请先到「操作录制」标签页录制并保存"
                            "该程序的操作脚本；或取消“自动回放”改用通用自动点击。")

        before_drivers = _installed_printer_drivers() if is_printer_pkg else None

        if kind == "msi":
            _run_msi(installer, install_dir, log, verify_path)
            saw_completion = True
        else:
            result = _run_exe(installer, kind, silent_args, install_dir, timeout,
                              auto_click, verify_path, log, script_steps)
            saw_completion = bool(result.get("saw_completion"))

        if is_printer_pkg:
            after_drivers = _installed_printer_drivers()
            if after_drivers is None:
                log("无法枚举系统打印驱动（跳过驱动校验）")
            else:
                added = after_drivers - before_drivers
                if added:
                    shown = "、".join(sorted(added)[:10])
                    if len(added) > 10:
                        shown += " 等 %s 个" % len(added)
                    log("检测到新安装的打印驱动：%s ✓" % shown)
                else:
                    if saw_completion:
                        log("未检测到新增打印驱动（可能此前已安装同名驱动），按安装流程正常完成处理。")
                    else:
                        raise TaskError(
                            "安装向导已结束，但未检测到新安装的打印驱动，也没有出现"
                            "“安装完成”页面。\n"
                            "驱动可能没有真正装上，请检查安装程序是否有额外提示，"
                            "或重新运行并观察向导页面。")
            log("打印驱动安装流程结束：打印机纸张设置任务将在其后执行，"
                "并自动等待打印机出现（最多 60 秒）。")
        log("驱动安装任务完成 ✓")

    # ---------------- 界面 ----------------
    def build_tab(self, tab, app):
        tab.grid_columnconfigure(1, weight=1)
        self.app = app
        self.v = {
            "en": BooleanVar(value=False), "auto": BooleanVar(value=True),
            "use_script": BooleanVar(value=True),
            "installer": StringVar(), "dir": StringVar(value="D:\\"),
            "args": StringVar(), "timeout": StringVar(value=str(DEFAULT_TIMEOUT)),
            "verify": StringVar(),
        }
        ui.hint(tab, "自动点击安装向导。").grid(
            row=0, column=0, columnspan=3, padx=16, pady=(14, 4), sticky="w")
        ui.check(tab, self.v["en"], "启用此任务（部署时自动安装）").grid(
            row=1, column=0, columnspan=3, padx=(16, 6), pady=6, sticky="w")

        ui.label(tab, "安装程序").grid(row=2, column=0, padx=(16, 6), pady=6, sticky="w")
        ui.entry(tab, self.v["installer"], placeholder="选择安装程序（.exe / .msi / .bat）").grid(
            row=2, column=1, padx=6, pady=6, sticky="ew")
        ui.button(tab, "浏览…", lambda: ui.browse_file(
            self.v["installer"], "选择安装程序",
            [("安装程序", "*.exe *.msi *.bat *.cmd"), ("所有文件", "*.*")])).grid(
            row=2, column=2, padx=(6, 16), pady=6)

        ui.label(tab, "安装目录").grid(row=3, column=0, padx=(16, 6), pady=6, sticky="w")
        ui.entry(tab, self.v["dir"], placeholder="默认 D:\\（出现目录选择时自动填入）").grid(
            row=3, column=1, columnspan=2, padx=6, pady=6, sticky="ew")

        ui.check(tab, self.v["auto"],
                 "自动点击安装向导").grid(
            row=4, column=0, columnspan=3, padx=(16, 6), pady=6, sticky="w")

        # 录制脚本状态提示（执行时自动回放）
        self.script_hint = ui.hint(tab, "")
        self.script_hint.grid(row=5, column=0, columnspan=3, padx=(16, 16), pady=(0, 4), sticky="w")

        # ---- 高级选项（默认收起，保持界面简洁） ----
        self.adv_btn = ctk.CTkButton(tab, text="▸ 高级选项", width=110, height=26,
                                     fg_color="transparent", border_width=1,
                                     border_color=("gray60", "gray40"),
                                     text_color=("gray10", "gray90"),
                                     hover_color=("gray80", "gray35"),
                                     command=self._toggle_adv)
        self.adv_btn.grid(row=6, column=0, padx=(16, 6), pady=2, sticky="w")

        self.adv = ctk.CTkFrame(tab, fg_color="transparent")
        self.adv.grid_columnconfigure(1, weight=1)
        ui.check(self.adv, self.v["use_script"],
                 "检测到录制脚本时自动回放（推荐；回放完毕自动点击兜底）").grid(
            row=0, column=0, columnspan=3, padx=(16, 6), pady=4, sticky="w")
        ui.label(self.adv, "静默参数（可选）").grid(row=1, column=0, padx=(16, 6), pady=4, sticky="w")
        ui.entry(self.adv, self.v["args"], placeholder="留空 = 自动处理；自定义参数失败会自动退回向导").grid(
            row=1, column=1, columnspan=2, padx=6, pady=4, sticky="ew")
        ui.label(self.adv, "超时（秒）").grid(row=2, column=0, padx=(16, 6), pady=4, sticky="w")
        ui.entry(self.adv, self.v["timeout"], placeholder=str(DEFAULT_TIMEOUT)).grid(
            row=2, column=1, padx=6, pady=4, sticky="w")
        ui.hint(self.adv, "无进展多少秒后判定超时。").grid(
            row=2, column=2, padx=6, pady=4, sticky="w")
        ui.label(self.adv, "完成校验（可选）").grid(row=3, column=0, padx=(16, 6), pady=4, sticky="w")
        ui.entry(self.adv, self.v["verify"], placeholder="安装结束后必须存在的文件/文件夹，留空不校验").grid(
            row=3, column=1, padx=6, pady=4, sticky="ew")
        ui.button(self.adv, "浏览…", lambda: ui.browse_file(
            self.v["verify"], "选择校验目标", [("所有文件", "*.*")])).grid(
            row=3, column=2, padx=(6, 16), pady=4)

        ui.hint(tab, "安装需要管理员权限：请右键以管理员身份运行。").grid(
            row=7, column=0, columnspan=3, padx=16, pady=(4, 10), sticky="w")

        # 安装程序变化时刷新“已有录制脚本”提示
        try:
            self.v["installer"].trace_add("write", lambda *_a: self._refresh_script_hint())
        except Exception:
            pass

    def _refresh_script_hint(self):
        installer = self.v["installer"].get().strip()
        if installer and os.path.isfile(installer):
            scripts = _recorder.find_scripts(installer)
            if scripts:
                name = _recorder.script_summary(scripts[0])[0]
                self.script_hint.configure(
                    text="✅ 已有 %s 个录制脚本，执行时自动回放「%s」。" % (len(scripts), name))
                return
        self.script_hint.configure(text="无录制脚本：使用通用自动点击。")

    def _toggle_adv(self):
        if self.adv.winfo_ismapped():
            self.adv.grid_remove()
            self.adv_btn.configure(text="▸ 高级选项")
        else:
            self.adv.grid(row=6, column=0, columnspan=3, sticky="ew", padx=4, pady=(4, 2))
            self.adv_btn.configure(text="▾ 高级选项")

    def load_ui(self, cfg):
        self.v["en"].set(bool(cfg.get("enabled", False)))
        self.v["auto"].set(bool(cfg.get("auto_click", True)))
        self.v["use_script"].set(bool(cfg.get("use_script", True)))
        self.v["installer"].set(cfg.get("installer", ""))
        self.v["dir"].set(cfg.get("install_dir", "D:\\"))
        self.v["args"].set(cfg.get("silent_args", ""))
        self.v["timeout"].set(str(cfg.get("timeout_seconds", DEFAULT_TIMEOUT)))
        self.v["verify"].set(cfg.get("verify_path", ""))
        self.adv.grid_remove()
        self._refresh_script_hint()

    def collect_ui(self, cfg):
        cfg["enabled"] = bool(self.v["en"].get())
        cfg["auto_click"] = bool(self.v["auto"].get())
        cfg["use_script"] = bool(self.v["use_script"].get())
        cfg["installer"] = self.v["installer"].get().strip()
        cfg["install_dir"] = self.v["dir"].get().strip() or "D:\\"
        cfg["silent_args"] = self.v["args"].get().strip()
        cfg["verify_path"] = self.v["verify"].get().strip()
        try:
            cfg["timeout_seconds"] = int(float(self.v["timeout"].get().strip()))
        except ValueError:
            cfg["timeout_seconds"] = DEFAULT_TIMEOUT
