# -*- coding: utf-8 -*-
"""生成 api-ms-win-core-sysinfo-l1-2-0.dll 转发器存根（纯 Python 手写 PE32）。

背景：conda 版 Python 3.8 的 ucrtbase.dll 会延迟加载该 API 集，
Win7 系统没有这个文件，启动时会弹「找不到 api-ms-win-core-sysinfo-l1-2-0.dll」。
此存根把 9 个导出转发到 Win7 上存在的 kernel32 函数：
  - GetSystemTimePreciseAsFileTime -> kernel32.GetSystemTimeAsFileTime（近似替代）
  - 三个 Win8+ 才有、但 CRT/驱动安装器不会调用的函数也转发到安全函数占位
"""
import struct

NAME = "api-ms-win-core-sysinfo-l1-2-0.dll"

# 导出名 -> 转发目标（KERNEL32.函数名）
EXPORTS = [
    ("EnumSystemFirmwareTables", "KERNEL32.GetSystemTimeAsFileTime"),
    ("GetNativeSystemInfo", "KERNEL32.GetNativeSystemInfo"),
    ("GetOsSafeBootMode", "KERNEL32.GetSystemTimeAsFileTime"),
    ("GetProductInfo", "KERNEL32.GetProductInfo"),
    ("GetSystemFirmwareTable", "KERNEL32.GetSystemTimeAsFileTime"),
    ("GetSystemTimePreciseAsFileTime", "KERNEL32.GetSystemTimeAsFileTime"),
    ("SetComputerNameExW", "KERNEL32.SetComputerNameExW"),
    ("SetSystemTime", "KERNEL32.SetSystemTime"),
    ("VerSetConditionMask", "KERNEL32.VerSetConditionMask"),
]
N = len(EXPORTS)

EDATA_RVA = 0x2000
TEXT_RVA = 0x1000


def build():
    # ---- .edata 布局 ----
    dir_off = 0                                    # 导出目录（40 字节）
    funcs_off = 40                                 # 函数地址表（N*4）
    names_off = funcs_off + N * 4                  # 名称表（N*4）
    ords_off = names_off + N * 4                   # 序号表（N*2，对齐4）
    ords_off = (ords_off + 3) & ~3
    fwd_off = ords_off + N * 2                     # 转发字符串区
    # 计算转发字符串偏移
    fwd_offs = []
    cur = fwd_off
    for _, target in EXPORTS:
        fwd_offs.append(cur)
        cur += len(target) + 1
    name_off = cur
    name_offs = []
    for name, _ in EXPORTS:
        name_offs.append(cur)
        cur += len(name) + 1
    dllname_off = cur
    edata_size = cur + len(NAME) + 1
    edata_raw = (edata_size + 0x1FF) & ~0x1FF

    edata = bytearray(edata_raw)
    # 导出目录（IMAGE_EXPORT_DIRECTORY，11 个字段共 40 字节）
    struct.pack_into("<IIHHIIIIIII", edata, dir_off,
                     0, 0, 0, 0,
                     EDATA_RVA + dllname_off,   # Name
                     1,                         # Base
                     N, N,                      # NumberOfFunctions / Names
                     EDATA_RVA + funcs_off,
                     EDATA_RVA + names_off,
                     EDATA_RVA + ords_off)
    for i, (_, target) in enumerate(EXPORTS):
        struct.pack_into("<I", edata, funcs_off + i * 4, EDATA_RVA + fwd_offs[i])
        edata[fwd_offs[i]:fwd_offs[i] + len(target)] = target.encode("ascii")
    for i, (name, _) in enumerate(EXPORTS):
        struct.pack_into("<I", edata, names_off + i * 4, EDATA_RVA + name_offs[i])
        struct.pack_into("<H", edata, ords_off + i * 2, i)
        edata[name_offs[i]:name_offs[i] + len(name)] = name.encode("ascii")
    edata[dllname_off:dllname_off + len(NAME)] = NAME.encode("ascii")

    # ---- PE 头 ----
    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)  # e_lfanew
    # PE 签名 + COFF
    coff = struct.pack("<IHHIIIHH", 0x00004550, 0x14C, 2, 0, 0, 0, 0xE0, 0x2102)
    # 可选头 PE32（标准 96 字节 + 数据目录）
    opt = struct.pack(
        "<HBB" + "I" * 9 + "H" * 6 + "I" + "I" * 3 + "H" * 2 + "I" * 4 + "I" * 2,
        0x10B,      # Magic
        6, 0,       # linker ver
        0x200,      # SizeOfCode
        edata_raw,  # SizeOfInitializedData
        0,          # SizeOfUninitializedData
        0,          # EntryPoint
        TEXT_RVA,   # BaseOfCode
        EDATA_RVA,  # BaseOfData
        0x10000000, # ImageBase
        0x1000,     # SectionAlignment
        0x200,      # FileAlignment
        6, 1,       # OS version 6.1（Win7）
        0, 0,
        6, 0,       # subsystem version
        0,          # Win32Version
        0x3000,     # SizeOfImage
        0x200,      # SizeOfHeaders
        0,          # CheckSum
        3,          # Subsystem CUI
        0,          # DllCharacteristics
        0x100000, 0x1000,   # stack
        0x100000, 0x1000,   # heap
        0,          # LoaderFlags
        16,         # NumberOfRvaAndSizes
    )
    # 数据目录（16 个，前 3 个占位：导出表/导入表/资源）
    ddir = struct.pack("<II", EDATA_RVA, edata_size)
    ddir += struct.pack("<I", 0) * (16 * 2 - 2)

    sec_text = struct.pack("<8sIIIIIIHHI", b".text\0\0\0",
                           0x1000, TEXT_RVA, 0x200, 0x200, 0, 0, 0, 0,
                           0x60000020)
    sec_data = struct.pack("<8sIIIIIIHHI", b".edata\0\0",
                           edata_size, EDATA_RVA, edata_raw, 0x400, 0, 0, 0, 0,
                           0x40000040)

    headers = bytes(dos) + bytes(coff) + opt + ddir + sec_text + sec_data
    headers = headers.ljust(0x200, b"\0")

    return headers + b"\0" * 0x200 + bytes(edata)


if __name__ == "__main__":
    import os
    blob = build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "py38", NAME)
    with open(out, "wb") as f:
        f.write(blob)
    print(f"已生成 {out}（{len(blob)} 字节）")
