# -*- coding: utf-8 -*-
"""解析 Python 3.8.10 安装包（WiX Burn bundle）尾部容器表，定位内嵌 MSI 的偏移与大小"""
import struct
import sys

path = sys.argv[1]
data = open(path, "rb").read()
size = len(data)
print("文件大小:", size)

# 找 wixburn 签名
sig = b"wixburn"
positions = []
start = 0
while True:
    i = data.find(sig, start)
    if i < 0:
        break
    positions.append(i)
    start = i + 1
print("wixburn 签名位置:", positions)

if not positions:
    sys.exit(1)

pos = positions[-1]
print("最后一个签名附近字节:")
print(data[pos - 16:pos + 64].hex(" "))

# 尝试解析：签名(8) + version(4) + count(4) + [GUID(16) + offset(8) + size(8)] * n
for p in positions:
    for head_len in (8, 16, 32):
        try:
            after = p + head_len
            count = struct.unpack_from("<I", data, after)[0]
            if not (1 <= count <= 20):
                continue
            entries = []
            valid = True
            off = after + 4
            for _ in range(count):
                if off + 32 > size:
                    valid = False
                    break
                guid = data[off:off + 16]
                c_off, c_size = struct.unpack_from("<QQ", data, off + 16)
                entries.append((guid, c_off, c_size))
                off += 32
            if not valid:
                continue
            # 验证每个容器偏移处是 MSI OLE 魔数
            ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
            ok = all(c_off + c_size <= size and data[c_off:c_off + 8] == ole
                     for _, c_off, c_size in entries)
            if ok:
                print(f"\n解析成功！签名@{p} head_len={head_len} 容器数={count}")
                for idx, (guid, c_off, c_size) in enumerate(entries):
                    print(f"  容器{idx}: off={c_off} size={c_size} end={c_off + c_size}")
                break
        except struct.error:
            continue
    else:
        continue
    break
else:
    print("未能从尾部结构解析出容器表，尝试用 OLE 魔数盲切")
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    offs = []
    s = 0
    while True:
        i = data.find(ole, s)
        if i < 0:
            break
        offs.append(i)
        s = i + 8
    print("OLE 魔数位置:", offs)
