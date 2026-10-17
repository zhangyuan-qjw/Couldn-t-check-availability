# -*- coding: utf-8 -*-
"""从 python-3.8.10.exe (Burn bundle) 中切出内嵌的 CAB 文件"""
import struct
import sys

src = sys.argv[1]
data = open(src, "rb").read()
size = len(data)

offs = []
s = 0
while True:
    i = data.find(b"MSCF", s)
    if i < 0:
        break
    offs.append(i)
    s = i + 4
print("CAB 魔数位置:", offs)

for idx, off in enumerate(offs):
    # CFHEADER: signature(4) reserved1(4) cbCabinet(4)
    cb = struct.unpack_from("<I", data, off + 8)[0]
    end = off + cb
    print(f"CAB{idx}: off={off} cbCabinet={cb} end={end}")
    if end > size:
        print("  !! 超出文件范围，跳过")
        continue
    out = f"win7build\\cab{idx}.cab"
    with open(out, "wb") as f:
        f.write(data[off:end])
    print(f"  已写出: {out}")
