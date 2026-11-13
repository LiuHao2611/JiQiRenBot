# -*- coding: utf-8 -*-
"""补齐 SnowLuma 副本的 Warframe 静态词库（只读源仓，绝不写旧仓一个字节）。

事故背景（2026-11-13 19:43，容器日志实证）：
  * OCR 把紫卡四条词条**全部读对**（wf_riven_ocr_raw len=91），但
    /app/data/warframe_items/ 里只有 _sync_state.json，
    riven_disp.json / riven_stat_base.json / riven_stat_zh.json 三张派生表
    从未落地（_sync_state 记「快照落盘失败」）。
  * riven._load_riven_data() 把 FileNotFoundError 吞成空字典 → _find_stat
    词库为空 → _parse_ocr 的 stats=[] → 返回 None → 用户看到
    「图可能太小、被裁切」的误导诊断卡。

为什么必须有个脚本：data/ 被 .gitignore 排除，是 bind mount 的运行态目录，
既不进 git 也不进镜像（Dockerfile 明确不 COPY data/）。全新部署若不补这份
静态快照，紫卡分析必然不可用，而运行时 wf_sync 依赖 DE 官方 Public Export
联网，容器内出网受限时同步会失败（本次即如此）。

用法：
    python scripts/prepare_warframe_data.py            # 补齐（幂等，逐文件校验）
    python scripts/prepare_warframe_data.py --check    # 只检查，不写任何文件
    python scripts/prepare_warframe_data.py --source <其它源目录>

数据口径：源取 qq_bridge_official（业务代码的同源 working tree）里已派生好的
静态快照；NapCat 旧仓 qq_bridge 永久只读，本脚本连读都不碰它。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path("D:/AI/manju_agent/qq_bridge_official/data/warframe_items")
DEST_DIR = ROOT / "data" / "warframe_items"

#: 紫卡分析链路必需：缺任意一个就显式失败，绝不允许用空词库冒充成功。
REQUIRED_FILES = (
    "riven_disp.json",          # 武器名 → 倾向/类型/中文名（_parse_ocr 查武器）
    "riven_stat_base.json",     # 7 类武器 × 词条基础值（_find_stat 的 en_keys）
    "riven_stat_zh.json",       # 词条中文名 + 别名（_find_stat 的 zh_flat）
    "riven-public-export.json", # DE 官方裁剪快照，wf_sync 重新派生的唯一输入
    "mod_full.json",            # 紫卡/Mod 全量数据（riven_card）
    "zh_names.json",            # 武器中文名反查
    "aliases.json",             # 武器别名反查
)

#: data/ 根目录（warframe_items/ 的父目录）里的 Warframe 静态快照。
#: 2026-11-14 端到端复验又抓到 wf_riven_mults_load_failed: /app/data/wf_riven_weapons.json
#: 缺失 —— 只补 warframe_items/ 会让「倾向倍率」继续走空表，故一并复制。
ROOT_LEVEL_FILES = ("wf_riven_weapons.json", "solNodes.json", "wf_items_v2.json")

#: 不复制：运行态状态文件 / 备份 / 图标缓存索引（由各自功能自行生成）。
EXCLUDE_NAMES = {"_sync_state.json", "_img_index.json"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_json(path: Path) -> str:
    """必须是非空且可解析的 JSON（dict/list），否则显式抛错。"""
    raw = path.read_text(encoding="utf-8")
    obj = json.loads(raw)
    if isinstance(obj, (dict, list)) and obj:
        return sha256(path)
    raise ValueError(f"JSON 为空或结构不是非空 object/array: {path}")


def optional_files(source: Path) -> list[str]:
    """源目录顶层其它静态 JSON（如实列出，不伪造存在）。"""
    return sorted(
        p.name for p in source.glob("*.json")
        if p.name not in REQUIRED_FILES
        and p.name not in EXCLUDE_NAMES
        and ".bak" not in p.name
    )


def check(dest: Path) -> list[str]:
    """只检查 REQUIRED 是否齐全可用，返回问题列表（不写任何文件）。"""
    problems = []
    for name in REQUIRED_FILES:
        p = dest / name
        if not p.is_file():
            problems.append(f"{name}: 文件不存在")
            continue
        try:
            validate_json(p)
        except Exception as e:  # noqa: BLE001 — 检查阶段要把原因报全
            problems.append(f"{name}: {type(e).__name__}: {e}")
    return problems


def copy_one(source: Path, dest: Path, name: str, required: bool) -> str:
    src = source / name
    if not src.is_file():
        if required:
            raise FileNotFoundError(
                f"源文件缺失（必需）: {src}；无法补齐静态词库，"
                f"请确认 qq_bridge_official 的 data/warframe_items 完整，或用 --source 指定")
        return "SKIP 源文件不存在（非必需）"
    digest = validate_json(src)
    dst = dest / name
    tmp = dest / (name + ".tmp")
    shutil.copyfile(src, tmp)
    try:
        got = validate_json(tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if got != digest:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"复制后 sha256 不一致: {name}")
    os.replace(tmp, dst)
    return f"OK   {name} ({dst.stat().st_size} B, sha256={digest[:12]}…)"


def main() -> int:
    ap = argparse.ArgumentParser(description="补齐 SnowLuma 副本的 Warframe 静态词库")
    ap.add_argument("--check", action="store_true", help="只检查必需文件，不写任何文件")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="静态词库源目录")
    args = ap.parse_args()
    source: Path = args.source

    if args.check:
        problems = check(DEST_DIR)
        for name in REQUIRED_FILES:
            print(("OK   " if not any(pb.startswith(name + ":") for pb in problems) else "MISS ") + name)
        if problems:
            print("\n必需词库不齐全：")
            for pb in problems:
                print("  - " + pb)
            print("\n修复：python scripts/prepare_warframe_data.py")
            return 1
        print(f"\ncheck: {len(REQUIRED_FILES)}/{len(REQUIRED_FILES)} 必需文件齐全且可解析")
        return 0

    if not source.is_dir():
        raise FileNotFoundError(f"源目录不存在: {source}（可用 --source 指定）")
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    print(f"源: {source}\n目标: {DEST_DIR}\n")
    for name in REQUIRED_FILES:
        print(copy_one(source, DEST_DIR, name, required=True))
    optional = optional_files(source)
    for name in optional:
        print(copy_one(source, DEST_DIR, name, required=False))
    print("\n[data/ 根目录静态快照]")
    for name in ROOT_LEVEL_FILES:
        print(copy_one(source.parent, DEST_DIR.parent, name, required=False))

    problems = check(DEST_DIR)
    if problems:
        raise RuntimeError("复制后自检失败（禁止静默交付）: " + "; ".join(problems))
    print(f"\n完成：必需 {len(REQUIRED_FILES)} 个，warframe_items 可选 {len(optional)} 个，"
          f"data 根 {len(ROOT_LEVEL_FILES)} 个；"
          f"目标目录自检 {len(REQUIRED_FILES)}/{len(REQUIRED_FILES)} 通过")
    print("注意：data/ 被 .gitignore 排除，这份静态数据不入库；"
          "容器重建后若 data/ 被清空，需要重跑本脚本。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
