# -*- coding: utf-8 -*-
"""纯 Python 解析 MSI(OLE 复合文档)：列出所有流及其魔数，并可导出流内容"""
import struct
import sys

FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC

MAXREGSECT = 0xFFFFFFFA


def parse_ole(path):
    data = open(path, "rb").read()
    if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError("不是 OLE 复合文档")

    # MSI 复合文档怪癖：512 字节头部挤占 0 号扇区前部，
    # 头部里所有扇区号相对真实扇区偏移 +1（真实扇区 = 逻辑扇区 + 1）
    SHIFT = 1

    # 头部
    sec_shift = struct.unpack_from("<H", data, 0x1E)[0]
    mini_shift = struct.unpack_from("<H", data, 0x20)[0]
    sec_size = 1 << sec_shift
    mini_size = 1 << mini_shift
    num_fat = struct.unpack_from("<I", data, 0x2C)[0]
    dir_start = struct.unpack_from("<I", data, 0x30)[0]
    mini_cutoff = struct.unpack_from("<I", data, 0x38)[0]
    mini_fat_start = struct.unpack_from("<I", data, 0x3C)[0]
    num_mini_fat = struct.unpack_from("<I", data, 0x40)[0]
    difat_start = struct.unpack_from("<I", data, 0x44)[0]
    num_difat = struct.unpack_from("<I", data, 0x48)[0]

    def real(n):
        return n + SHIFT if n not in (FREESECT, ENDOFCHAIN) else n

    def sector(n):
        n = real(n)
        return data[n * sec_size:(n + 1) * sec_size]

    # DIFAT
    difat = list(struct.unpack_from("<109I", data, 0x4C))
    difat = [d for d in difat if d != FREESECT]
    while difat_start != ENDOFCHAIN and difat_start != FREESECT:
        entries = struct.unpack("<" + "I" * (sec_size // 4), sector(difat_start))
        difat.extend(entries[:-1])
        difat_start = entries[-1]

    # FAT
    fat = []
    for fs in difat[:num_fat]:
        fat.extend(struct.unpack("<" + "I" * (sec_size // 4), sector(fs)))

    def chain(start):
        out = []
        s = start
        guard = 0
        while s != ENDOFCHAIN and s < len(fat) and guard < len(fat) + 10:
            out.append(s)
            s = fat[s]
            guard += 1
        return out

    # 目录
    dir_bytes = b"".join(sector(s) for s in chain(dir_start))

    def read_dir(e):
        off = e * 128
        name_len = struct.unpack_from("<H", dir_bytes, off + 64)[0]
        name = dir_bytes[off:off + name_len - 2].decode("utf-16-le", "ignore") if name_len >= 2 else ""
        etype = dir_bytes[off + 66]
        start = struct.unpack_from("<I", dir_bytes, off + 116)[0]
        size = struct.unpack_from("<Q", dir_bytes, off + 120)[0]
        left = struct.unpack_from("<I", dir_bytes, off + 68)[0]
        right = struct.unpack_from("<I", dir_bytes, off + 72)[0]
        child = struct.unpack_from("<I", dir_bytes, off + 76)[0]
        return dict(name=name, type=etype, start=start, size=size,
                    left=left, right=right, child=child)

    entries = [read_dir(i) for i in range(len(dir_bytes) // 128)]

    # miniFAT 与 mini 流
    mini_fat = []
    for ms in chain(mini_fat_start)[:num_mini_fat]:
        mini_fat.extend(struct.unpack("<" + "I" * (sec_size // 4), sector(ms)))
    root = entries[0]
    root_bytes = b"".join(sector(s) for s in chain(root["start"]))

    def mini_chain(start):
        out = []
        s = start
        guard = 0
        while s != ENDOFCHAIN and s < len(mini_fat) and guard < len(mini_fat) + 10:
            out.append(s)
            s = mini_fat[s]
            guard += 1
        return out

    def stream_bytes(e):
        size = e["size"]
        if size < mini_cutoff:
            return b"".join(root_bytes[s * mini_size:(s + 1) * mini_size]
                            for s in mini_chain(e["start"]))[:size]
        return b"".join(sector(s) for s in chain(e["start"]))[:size]

    # 遍历目录树（红黑树中序遍历：左 → 自身 → 右）
    streams = []

    def visit(idx, path):
        if idx >= len(entries) or idx == FREESECT:
            return
        e = entries[idx]
        visit(e["left"], path)
        if e["type"] == 2:
            streams.append((path + e["name"], e["size"], stream_bytes(e)))
        elif e["type"] in (1, 5):
            visit(e["child"], path + e["name"] + "/")
        visit(e["right"], path)

    visit(root["child"], "")
    return streams


if __name__ == "__main__":
    path = sys.argv[1]
    streams = parse_ole(path)
    print(f"共 {len(streams)} 个流\n")
    for name, size, content in streams:
        head = content[:8]
        magic = "".join(chr(b) if 32 <= b < 127 else "." for b in head)
        print(f"{size:>12,}  {name:40s} {magic}")
