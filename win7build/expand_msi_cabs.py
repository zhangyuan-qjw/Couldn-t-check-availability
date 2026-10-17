# -*- coding: utf-8 -*-
"""从每个 MSI 中导出内嵌 CAB 流，再用 expand.exe 解出文件"""
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ole_parse import parse_ole

out_root = os.path.join("win7build", "msi_expanded")
os.makedirs(out_root, exist_ok=True)

for p in sorted(glob.glob(r"win7build\msi\uniq\*.msi")):
    base = os.path.basename(p).replace(".msi", "")
    streams = parse_ole(p)
    cab = None
    for name, size, content in streams:
        if content[:4] == b"MSCF":
            cab = content
            break
    if cab is None:
        print(base, "没有 CAB 流，跳过")
        continue
    cab_path = os.path.join(out_root, base + ".cab")
    with open(cab_path, "wb") as f:
        f.write(cab)
    dest = os.path.join(out_root, base)
    os.makedirs(dest, exist_ok=True)
    r = subprocess.run(["expand.exe", "-F:*", cab_path, dest],
                       capture_output=True, text=True)
    files = os.listdir(dest)
    print(f"{base}: cab={len(cab):,} 解出 {len(files)} 个文件/目录")
    for f in sorted(files)[:12]:
        print("   ", f)
    if len(files) > 12:
        print("    ...")
