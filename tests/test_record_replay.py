# -*- coding: utf-8 -*-
"""自检：操作录制与回放。

说明：全局鼠标钩子的“安装”已验证可用；本测试把与钩子回调等价的鼠标事件
      直接喂给录制器的处理逻辑（沙箱会把注入的合成点击转成直接消息，绕过
      全局钩子链，因此这里不依赖真实输入注入），完整验证：
        录制逻辑 → 脚本生成 → 全新进程按脚本回放 → 结果校验。

流程：
  1. 启动模拟卸载向导；把用户点击「是」「完成」的鼠标事件喂给 Recorder；
  2. 保存脚本，检查脚本内容（click 步骤 ≥2，含按钮文字与相对坐标）；
  3. 再起一个全新向导进程，用 driver_task 的“回放录制脚本”模式执行；
  4. 校验向导走到完成页并写出 done 标记（且从未点「否」）。
"""
import json
import os
import sys
import tempfile
import time
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.tasks import _autoclick, _recorder, driver_task  # noqa: E402

user32 = _autoclick.user32


def _top_of(pid):
    for h, p, _t in _autoclick._enum_top_windows():
        if p == pid:
            return h
    return None


def _find_button(root, keyword, enabled_only=False):
    for ch, cls, text in _autoclick._enum_children(root):
        if cls == "Button" and keyword in text:
            if enabled_only and not user32.IsWindowEnabled(ch):
                continue
            return ch, text
    return None, ""


def _center(hwnd):
    r = _autoclick._rect(hwnd)
    return (r[0] + r[2]) // 2, (r[1] + r[3]) // 2


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "dist", "fake_uninstaller", "fake_uninstaller.exe")
    if not os.path.isfile(exe):
        print("未找到模拟卸载程序：%s" % exe)
        return 2
    marker = tempfile.mkdtemp(prefix="fakeuninst_")
    os.environ["FAKE_MARKER"] = marker

    print("== 阶段 1：录制（直接喂入等价鼠标事件） ==")
    logs = []
    rec = _recorder.Recorder(exe, log=lambda m: logs.append(m))
    rec.proc = None  # 不启动真实钩子线程，直接测试事件处理逻辑
    rec.tree_pids = set()
    import subprocess
    proc = subprocess.Popen([exe], cwd=os.path.dirname(exe) or None)
    rec.proc = proc
    rec.tree_pids = {proc.pid}

    deadline = time.time() + 15
    root = None
    while time.time() < deadline:
        root = _top_of(proc.pid)
        if root:
            break
        time.sleep(0.3)
    if not root:
        print("向导窗口未出现")
        return 1

    # 模拟用户点击「是(&Y)」：真实点击推进向导 + 事件喂给录制器记录
    yes, yes_text = _find_button(root, "是(&Y)")
    if not yes:
        print("未找到「是」按钮")
        return 1
    # 滚轮与方向键事件（在点「是」之前，保证回放时向导窗口仍在）
    x, y = _center(yes)
    rec._proc_wheel(x, y, 120, root, yes)
    rec._proc_wheel(x, y, 120, root, yes)   # 连续同方向 → 应合并为一步
    rec._proc_key("up", root)
    print("录制事件：滚轮上滚 ×2、按键 ↑")
    time.sleep(0.4)
    rec._proc_click(x, y, root, yes)
    user32.SendMessageW(yes, 0x00F5, 0, 0)  # BM_CLICK：沙箱里可用（消息式点击）
    print("录制事件：点击「%s」" % yes_text)
    time.sleep(0.4)

    # 等待进度页出现并启用「完成」
    deadline = time.time() + 10
    root2 = None
    fin = None
    while time.time() < deadline:
        root2 = _top_of(proc.pid)
        if root2:
            fin = _find_button(root2, "完成", enabled_only=True)[0]
            if fin:
                break
        time.sleep(0.3)
    if not root2 or not fin:
        print("进度页未出现")
        return 1
    fin, fin_text = _find_button(root2, "完成", enabled_only=True)
    x, y = _center(fin)
    rec._proc_click(x, y, root2, fin)
    user32.SendMessageW(fin, 0x00F5, 0, 0)  # BM_CLICK：真正完成卸载
    print("录制事件：点击「%s」" % fin_text)
    time.sleep(1.2)
    rec._finalize_edit()

    script_path = rec.save("模拟卸载脚本")
    rec.save("模拟卸载脚本-第二份")  # 验证可保存多个脚本
    for l in logs:
        print("  | " + l)
    print("脚本：%s" % script_path)
    if not script_path or not os.path.isfile(script_path):
        print("脚本未保存")
        return 1
    all_scripts = _recorder.find_scripts(exe)
    print("该程序已有脚本数：%s（应 ≥2）" % len(all_scripts))
    if len(all_scripts) < 2:
        print("多脚本保存失败")
        return 1
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)
    types = [s.get("type") for s in script["steps"]]
    texts = [s.get("ctrl_text", "") for s in script["steps"]]
    print("录制步骤类型：%s" % types)
    print("录制按钮文字：%s" % texts)
    if types.count("click") < 2:
        print("录制的点击步骤不足（应 ≥2）")
        return 1
    if "wheel" not in types or "key" not in types:
        print("未录制到滚轮/按键步骤")
        return 1
    wheel_steps = [s for s in script["steps"] if s.get("type") == "wheel"]
    if len(wheel_steps) != 1:
        print("连续滚轮未合并（应为 1 步，实际 %s 步）" % len(wheel_steps))
        return 1
    if not any("是" in t for t in texts) or not any("完成" in t for t in texts):
        print("录制的按钮文字不符合预期")
        return 1

    # 脚本应记住程序路径，回放能自动定位
    prog_path = (script.get("program") or {}).get("path") or ""
    print("脚本记住的程序路径：%s" % prog_path)
    if prog_path != os.path.abspath(exe):
        print("脚本未记住程序路径")
        return 1
    located = _recorder.resolve_program(script_path)
    print("回放自动定位程序：%s" % located)
    if located != os.path.abspath(exe):
        print("回放自动定位程序失败")
        return 1

    # 勾选状态保存进配置文件 → 由 RecordReplayTask 在“开始执行”时回放
    from app.tasks.record_task import RecordReplayTask
    task = RecordReplayTask()
    tcfg = task.default_cfg()
    tcfg["scripts"] = [{"script": script_path, "name": "勾选回放测试",
                        "program_path": os.path.abspath(exe)}]
    print("任务配置写入脚本勾选：%s" % tcfg["scripts"])
    try:
        proc.terminate()
        proc.wait(5)
    except Exception:
        pass

    print("== 阶段 2.5：RecordReplayTask.run（模拟点「开始执行」） ==")
    marker3 = tempfile.mkdtemp(prefix="fakeuninst_task_")
    os.environ["FAKE_MARKER"] = marker3
    logs3 = []
    try:
        task.run(tcfg, lambda m: logs3.append(m))
        task_ok3 = True
    except Exception as e:
        print("任务回放异常：%s" % e)
        task_ok3 = False
    for l in logs3:
        print("  | " + l)
    done3 = os.path.exists(os.path.join(marker3, "fake_uninstall_done.txt"))
    print("任务回放完成标记：%s" % done3)
    if not (task_ok3 and done3):
        print("RecordReplayTask 执行失败")
        return 1

    print("== 阶段 3：全新进程按脚本回放（驱动任务自动模式） ==")
    marker2 = tempfile.mkdtemp(prefix="fakeuninst_replay_")
    os.environ["FAKE_MARKER"] = marker2
    logs2 = []
    # 自动模式：不指定 mode/script_path，工具应自动找到录制脚本并回放（模拟“点击开始执行”）
    cfg = {"enabled": True, "installer": exe, "install_dir": "C:\\",
           "silent_args": "", "timeout_seconds": 60, "auto_click": True,
           "verify_path": "", "use_script": True}
    task_ok = False
    try:
        driver_task.DriverInstallTask().run(cfg, lambda m: logs2.append(m))
        task_ok = True
    except Exception as e:
        print("回放任务异常：%s" % e)
        traceback.print_exc()
    for l in logs2:
        print("  | " + l)
    done = os.path.exists(os.path.join(marker2, "fake_uninstall_done.txt"))
    cancelled = os.path.exists(os.path.join(marker2, "fake_uninstall_cancelled.txt"))
    print("== 结果 ==")
    print("任务正常返回        : %s" % task_ok)
    print("完成标记(done)      : %s" % done)
    print("取消标记(cancelled) : %s（必须为 False）" % cancelled)
    if task_ok and done and not cancelled:
        print("RECORD/REPLAY TEST PASSED ✓")
        return 0
    print("RECORD/REPLAY TEST FAILED ✗")
    return 1


if __name__ == "__main__":
    sys.exit(main())
