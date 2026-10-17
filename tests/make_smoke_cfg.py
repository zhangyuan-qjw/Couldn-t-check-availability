# -*- coding: utf-8 -*-
"""生成仅启用“复制文件夹”任务的冒烟配置（用于验证打包后的 exe 能启动并执行引擎）"""
import json
import os
import sys


def make(dst_config_dir, src, dest):
    os.makedirs(dst_config_dir, exist_ok=True)
    cfg = {
        "name": "冒烟测试",
        "meta": {"version": 1},
        "tasks": {
            "copy_archive": {"enabled": True, "source": src, "dest": dest,
                             "overwrite": True, "backup": False},
            "copy_file": {"enabled": False},
            "shortcut": {"enabled": False},
            "remove_autostart": {"enabled": False},
            "driver_install": {"enabled": False},
            "printer": {"enabled": False},
            "quick_launch": {"enabled": False},
        },
    }
    path = os.path.join(dst_config_dir, "冒烟测试.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    print(make(sys.argv[1], sys.argv[2], sys.argv[3]))
