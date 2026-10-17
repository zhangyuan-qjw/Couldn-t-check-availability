# -*- coding: utf-8 -*-
"""文件复制 / 压缩包解压 / 覆盖备份的底层实现"""
import os
import shutil
import tempfile

from ..core import TaskError

ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}


def is_archive(path):
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in ARCHIVE_EXTS


def _backup_one(dst_file, dst_root, backup_root):
    """把即将被覆盖的文件备份到 backup_root（保持相对目录结构）"""
    rel = os.path.relpath(dst_file, dst_root)
    if rel.startswith(".."):
        return None
    target = os.path.join(backup_root, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(dst_file, target)
    return target


def merge_tree(src_dir, dst_dir, backup_dir=None, log=None):
    """把 src_dir 整个合并复制到 dst_dir（覆盖模式，不弹框）。返回 (复制数, 备份数)"""
    count = 0
    backed = 0
    for root, _dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel == "." else os.path.join(dst_dir, rel)
        os.makedirs(target_root, exist_ok=True)
        for f in files:
            s = os.path.join(root, f)
            t = os.path.join(target_root, f)
            if os.path.exists(t) and backup_dir:
                _backup_one(t, dst_dir, backup_dir)
                backed += 1
            shutil.copy2(s, t)
            count += 1
            if log:
                log(f"复制：{os.path.relpath(t, dst_dir)}")
    return count, backed


def copy_dir_or_archive(src, dst, backup_dir=None, log=None):
    """src 为文件夹或压缩包：复制/解压到 dst（覆盖模式，不弹框）"""
    if not os.path.exists(src):
        raise TaskError(f"源路径不存在：{src}")
    try:
        os.makedirs(dst, exist_ok=True)
    except Exception as e:
        raise TaskError(f"无法创建目标文件夹：{e}")
    if os.path.isdir(src):
        return merge_tree(src, dst, backup_dir=backup_dir, log=log)

    ext = os.path.splitext(src)[1].lower()
    if ext not in ARCHIVE_EXTS:
        raise TaskError(f"无法识别的源类型（既不是文件夹，也不是支持的压缩包）：{src}")
    tmp = tempfile.mkdtemp(prefix="deploy_extract_")
    try:
        if ext == ".rar":
            raise TaskError("暂不支持 RAR 压缩包，请先手动解压或转换为 zip")
        if ext == ".7z":
            try:
                import py7zr  # type: ignore
            except ImportError:
                raise TaskError("解压 .7z 需要 py7zr 库，请执行：pip install py7zr")
            py7zr.SevenZipFile(src).extractall(tmp)
        else:
            try:
                shutil.unpack_archive(src, tmp)
            except Exception as e:
                raise TaskError(f"解压失败（压缩包可能损坏或格式不受支持）：{e}")
        if log:
            log(f"压缩包已解压：{src}")
        return merge_tree(tmp, dst, backup_dir=backup_dir, log=log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
