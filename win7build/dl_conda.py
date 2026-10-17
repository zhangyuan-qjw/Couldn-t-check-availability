# -*- coding: utf-8 -*-
"""下载 conda win-32 包：python 3.8.10 / tk 8.6.10 / pip / setuptools / vc"""
import os
import sys
import urllib.request

BASE = "https://repo.anaconda.com/pkgs/main/win-32/"
FILES = [
    "python-3.8.10-hf3be9b6_7.tar.bz2",
    "tk-8.6.10-he774522_0.tar.bz2",
    "pip-21.2.4-py38h9f7ea03_0.tar.bz2",
    "setuptools-61.2.0-py38h9f7ea03_0.tar.bz2",
    "vc-14.2-h21ff451_1.tar.bz2",
]
os.makedirs("win7build\\pkg", exist_ok=True)
for fn in FILES:
    dest = os.path.join("win7build", "pkg", fn)
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        print("已存在:", fn)
        continue
    url = BASE + fn
    print("下载:", url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    print("  完成:", os.path.getsize(dest))
print("全部完成")
