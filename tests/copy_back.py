# -*- coding: utf-8 -*-
"""把修复后的源码与成品写回项目目录（用户指定：只更新 default-workspace\deploy_tool）"""
import os
import shutil
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = r"C:\Users\29215\Documents\deepseek-harness\default-workspace\deploy_tool"


def copy_files(files, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    for f in files:
        shutil.copy2(os.path.join(WS, f), os.path.join(dst_dir, os.path.basename(f)))
        print("copied file: %s -> %s" % (f, dst_dir))


def copy_tree(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    print("copied tree: %s -> %s" % (src, dst))


def main():
    print("==== project: %s ====" % PROJ)
    # 源码
    copy_files(["main.py", "README.md", "requirements.txt",
                "部署助手.spec", "build.bat", "build_win7.bat"], PROJ)
    copy_tree(os.path.join(WS, "app"), os.path.join(PROJ, "app"))
    os.makedirs(os.path.join(PROJ, "tests"), exist_ok=True)
    for t in os.listdir(os.path.join(WS, "tests")):
        if t.endswith(".py"):
            try:
                shutil.copy2(os.path.join(WS, "tests", t), os.path.join(PROJ, "tests", t))
                print("copied test: %s" % t)
            except Exception as e:
                print("WARN copy test %s failed: %s" % (t, e))
    # 成品
    copy_files(["dist/部署助手.exe"], os.path.join(PROJ, "dist"))
    copy_files(["dist_win7/部署助手_Win7.exe"], os.path.join(PROJ, "dist_win7"))
    copy_tree(os.path.join(WS, "dist_win7", "部署助手_Win7"),
              os.path.join(PROJ, "dist_win7", "部署助手_Win7"))
    print("ALL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
