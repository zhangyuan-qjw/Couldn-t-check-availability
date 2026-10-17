# -*- coding: utf-8 -*-
"""分析 Install.exe：识别安装框架类型、是否要求管理员、按钮/文字特征"""
import sys

p = r"C:\Users\29215\Desktop\海盟设备\得实打印机驱动\Install.exe"
data = open(p, "rb").read()
print("大小:", len(data))

# 1. PE 分析（管理员清单、子系统）
try:
    import pefile
    pe = pefile.PE(p, fast_load=True)
    print("machine:", hex(pe.FILE_HEADER.Machine), "| 位:", 32 if pe.FILE_HEADER.Machine == 0x14C else 64)
    # 提取 manifest 资源
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
    man = None
    if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
        for rsrc in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            for e in rsrc.directory.entries:
                for e2 in e.directory.entries:
                    for e3 in e2.directory.entries:
                        try:
                            d = e3.data.struct
                            off = d.OffsetToData
                            size = d.Size
                            raw = pe.get_memory_mapped_image()[off:off + size]
                            if b'<assembly' in raw or b'requestedExecutionLevel' in raw:
                                man = raw
                        except Exception:
                            pass
    if man:
        txt = man.decode('utf-8', 'ignore')
        import re
        m = re.search(r'level="([^"]+)"', txt)
        print("manifest 执行级别:", m.group(1) if m else "未找到")
        print("含 requireAdministrator:", 'requireAdministrator' in txt)
    else:
        print("manifest: 无内嵌 manifest（默认 asInvoker）")
except Exception as e:
    print("PE 分析失败:", e)

# 2. 框架特征扫描
sigs = {
    "NSIS": b"Nullsoft",
    "NSIS2": b"NullsoftInst",
    "InnoSetup": b"Inno Setup",
    "InnoSetup2": b"InnoSetup",
    "Wix": b"Wix",
    "InstallShield": b"InstallShield",
    "7zSFX": b"7-Zip",
    "Inno Setup 中文": "Inno Setup".encode("gbk", "ignore"),
}
for k, sig in sigs.items():
    if sig in data:
        print(f"特征命中: {k}")

# 3. 常见按钮/界面文字（GBK + UTF-16）
for enc in ("gbk", "utf-16-le"):
    try:
        txt = data.decode(enc, "ignore")
    except Exception:
        continue
    hits = []
    for kw in ("下一步", "开始安装", "安装", "我接受", "我同意", "完成", "取消", "浏览", "目标文件夹",
               "Next", "Install", "Finish", "I Agree", "Browse", "Destination", "Setup", "安装向导", "欢迎"):
        if kw in txt:
            hits.append(kw)
    if hits:
        print(f"编码 {enc} 中出现的关键词: {hits}")
