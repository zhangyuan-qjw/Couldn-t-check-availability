# -*- coding: utf-8 -*-
"""配置文件存取：一个 JSON 文件 = 一个命名配置"""
import datetime
import json
import os

from . import core
from . import util


class ConfigStore:
    def __init__(self):
        self.dir = util.configs_dir()
        os.makedirs(self.dir, exist_ok=True)

    def list(self):
        """列出全部配置：[{name, path, file}, ...]"""
        items = []
        try:
            files = sorted(os.listdir(self.dir))
        except OSError:
            return items
        for fn in files:
            if not fn.lower().endswith(".json"):
                continue
            path = os.path.join(self.dir, fn)
            name = fn[:-5]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("name"):
                    name = str(data["name"])
            except Exception:
                pass
            items.append({"name": name, "path": path, "file": fn})
        return items

    def _path_for(self, name):
        return os.path.join(self.dir, util.sanitize_filename(name) + ".json")

    def load(self, name_or_path):
        """按配置名或文件路径读取，返回 (归一化配置, 路径)"""
        if os.path.isfile(name_or_path):
            path = name_or_path
        elif str(name_or_path).lower().endswith(".json"):
            path = os.path.join(self.dir, name_or_path)
        else:
            path = self._path_for(name_or_path)
        if not os.path.isfile(path):
            raise ValueError(
                f"配置文件不存在：{path}\n"
                f"（可用配置见左侧列表；命令行用法：部署助手.exe -r \"配置名\"）")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件损坏（JSON 格式错误）：{path}\n{e}")
        if not isinstance(data, dict):
            raise ValueError(f"配置文件格式不正确：{path}")
        return core.normalize_cfg(data), path

    def save(self, cfg, name, path=None):
        """保存配置。path 为 None 时按名称存到配置目录（覆盖同名）"""
        name = (name or cfg.get("name") or "未命名").strip()
        out = dict(cfg)
        out["name"] = name
        out.setdefault("meta", {})
        out["meta"]["saved_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        if path is None:
            path = self._path_for(name)
        if not path.lower().endswith(".json"):
            path += ".json"
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return path

    def delete(self, name_or_path):
        if os.path.isfile(name_or_path):
            path = name_or_path
        else:
            path = self._path_for(name_or_path)
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False
