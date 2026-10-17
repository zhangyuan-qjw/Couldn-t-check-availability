# -*- coding: utf-8 -*-
"""从 repodata 中查找 win-32 的 python 3.8 / tk / tcl / pip 包"""
import bz2
import json

with bz2.open(r"win7build\repodata.json.bz2", "rt", encoding="utf-8") as f:
    repodata = json.load(f)

pkgs = repodata.get("packages", {})
want = {"python", "tk", "tcl", "pip", "setuptools", "wheel", "vc"}

print("==== python 3.8.x (win-32) ====")
for fn, meta in pkgs.items():
    if meta["name"] == "python" and meta["version"].startswith("3.8") and meta["build_number"] >= 0:
        deps = meta.get("depends", [])
        print(fn, "|", meta.get("build"), "|", meta.get("subdir"))

print("\n==== tk / tcl (win-32, 8.6.x) ====")
for fn, meta in pkgs.items():
    if meta["name"] in ("tk", "tcl") and meta["version"].startswith("8.6"):
        print(fn, "|", meta.get("build"))

print("\n==== pip / setuptools / wheel (win-32) ====")
for fn, meta in pkgs.items():
    if meta["name"] in ("pip", "setuptools", "wheel") and meta["build"].startswith("py38") and meta["version"].startswith(("21", "58", "0.36", "0.37")):
        print(fn, "|", meta.get("build"))
    if meta["name"] in ("pip", "setuptools", "wheel"):
        if fn.endswith((".tar.bz2", ".conda")):
            print("  all:", fn, "|", meta.get("build"))
            break
