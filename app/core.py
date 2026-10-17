# -*- coding: utf-8 -*-
"""任务框架与执行引擎。

【后续如何新增功能模块】
1. 在 app/tasks/ 下新建一个 .py 文件，写一个继承 BaseTask 的类；
2. 类上用 @register 装饰器，实现 default_cfg / run（以及界面三件套 build_tab、load_ui、collect_ui）；
3. 在 app/tasks/__init__.py 里 import 该模块。
界面会自动为它生成一个标签页，执行引擎会自动按顺序运行它。
"""
import datetime
import os
import traceback

from . import util


class TaskError(Exception):
    """任务失败，携带面向用户的失败原因"""


class BaseTask:
    """功能模块基类"""
    key = "base"          # 配置中的唯一键
    title = "未命名任务"    # 标签页标题
    icon = "⚙️"           # 标签页图标
    order = 100           # 执行顺序（越小越先）
    requires = []         # 前置任务 key：同一配置里这些任务已启用但失败时，本任务跳过

    def default_cfg(self):
        return {"enabled": True}

    def run(self, cfg, log):
        """执行任务。失败时抛 TaskError（原因会显示给用户）。"""
        raise NotImplementedError

    # ---------- 界面部分（GUI 为每个任务自动生成标签页） ----------
    def build_tab(self, tab, app):
        raise NotImplementedError

    def load_ui(self, cfg):
        """把配置填充到界面控件"""
        pass

    def collect_ui(self, cfg):
        """把界面控件值写回配置"""
        pass


_REGISTRY = []


def register(cls):
    """任务注册装饰器"""
    _REGISTRY.append(cls)
    return cls


def discover_tasks():
    """导入任务包以触发注册（静态 import，PyInstaller 打包后同样可用）"""
    import app.tasks  # noqa: F401
    _REGISTRY.sort(key=lambda c: (c.order, c.key))


def tasks():
    """返回所有任务模块实例（始终按 order 排序，与导入顺序无关）"""
    if not _REGISTRY:
        discover_tasks()
    _REGISTRY.sort(key=lambda c: (c.order, c.key))
    return [cls() for cls in _REGISTRY]


def default_cfg():
    """生成包含全部任务默认值的配置结构"""
    return {
        "name": "新配置",
        "meta": {"version": 1, "created_at": datetime.datetime.now().isoformat(timespec="seconds")},
        "tasks": {t.key: t.default_cfg() for t in tasks()},
    }


def normalize_cfg(cfg):
    """补齐缺失字段，兼容旧版本/不完整的配置文件"""
    base = default_cfg()
    base["name"] = str(cfg.get("name") or "未命名")
    base["meta"].update(cfg.get("meta") or {})
    for k, v in (cfg.get("tasks") or {}).items():
        if k in base["tasks"] and isinstance(v, dict):
            merged = dict(base["tasks"][k])
            merged.update(v)
            base["tasks"][k] = merged
    return base


class Engine:
    """顺序执行配置中已启用的任务；单个失败不中断，全部结束后统一汇报"""

    def __init__(self, log=None, status=None):
        self._log_cb = log
        self._status_cb = status
        self._fh = None

    def log(self, msg, level="info"):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        if self._fh:
            try:
                self._fh.write(f"[{now}] {msg}\n")
                self._fh.flush()
            except Exception:
                pass
        if self._log_cb:
            try:
                self._log_cb(msg, level)
            except Exception:
                pass

    def status(self, text):
        if self._status_cb:
            try:
                self._status_cb(text)
            except Exception:
                pass

    def run(self, cfg):
        """执行配置。返回 (是否全部成功, 摘要, [(失败任务, 原因), ...])"""
        os.makedirs(util.logs_dir(), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(util.logs_dir(), f"run_{stamp}.log")
        try:
            self._fh = open(log_path, "w", encoding="utf-8")
        except OSError:
            self._fh = None
        try:
            self.log(f"========== 开始执行配置「{cfg.get('name', '未命名')}」 ==========", "warn")
            pairs = []
            for t in tasks():
                tcfg = (cfg.get("tasks") or {}).get(t.key) or {}
                if tcfg.get("enabled", True):
                    pairs.append((t, tcfg))
            if not pairs:
                self.log("没有任何已启用的任务，未执行任何操作。", "warn")
                return True, "没有任何已启用的任务，未执行任何操作。", []

            done = 0
            skipped = 0
            failures = []
            failed_keys = {}  # 任务 key -> 失败原因（用于前置依赖判断）
            for i, (t, raw) in enumerate(pairs):
                tcfg = dict(raw or {})
                tcfg["_config_name"] = cfg.get("name", "")
                self.status(f"正在执行 {i + 1}/{len(pairs)}：{t.title}")

                # 前置依赖检查：依赖任务在同一配置中已启用且失败 → 跳过本任务
                blocked = []
                for req in getattr(t, "requires", []) or []:
                    rcfg = (cfg.get("tasks") or {}).get(req) or {}
                    if rcfg.get("enabled", True) and req in failed_keys:
                        blocked.append(f"{req}（{failed_keys[req]}）")
                if blocked:
                    self.log(f"【{t.title}】跳过：前置任务未成功（{'；'.join(blocked)}）", "warn")
                    skipped += 1
                    continue

                self.log(f"【{t.title}】开始")
                try:
                    t.run(tcfg, self.log)
                    self.log(f"【{t.title}】完成 ✓", "ok")
                    done += 1
                except TaskError as e:
                    self.log(f"【{t.title}】失败：{e}", "error")
                    failures.append((t.title, str(e)))
                    failed_keys[t.key] = str(e)
                except Exception as e:
                    self.log(f"【{t.title}】异常：{util.error_hint(e)}\n{traceback.format_exc()}", "error")
                    failures.append((t.title, util.error_hint(e)))
                    failed_keys[t.key] = util.error_hint(e)

            ok = not failures
            if skipped:
                summary = f"共 {len(pairs)} 项任务：成功 {done} 项，跳过 {skipped} 项，失败 {len(failures)} 项"
            else:
                summary = f"共 {len(pairs)} 项任务：成功 {done} 项，失败 {len(failures)} 项"
            if ok:
                self.log("========== 全部完成，配置成功 ✓ ==========", "ok")
            else:
                self.log("========== 执行结束，存在失败项 ==========", "error")
            return ok, summary, failures
        finally:
            if self._fh:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
