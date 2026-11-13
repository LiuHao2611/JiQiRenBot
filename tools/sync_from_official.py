"""把 qq_bridge_official 的最新 working-tree 业务代码同步进本副本。

与 bootstrap_snowluma_copy.py 不同：本脚本只同步「业务代码」子集
（src/ tests/ bot.py pyproject.toml requirements.txt），并**保留**本副本的
snowluma 专属文件（.env、docker-compose.snowluma.yml、scripts/、tools/、docker/、
运行期 data/ snowluma/ tmp/ logs/ downloads/、README.md、.gitignore）。

动机（2026-11-13）：snowluma 初版业务代码是从 NapCat 旧仓拷的，但官方仓有大批
未提交的新改动（dispatcher/config/game_tools/channel/pic 等）。用户要求用官方容器
（qq_bridge_official）的最新代码。官方代码在 OFFICIAL_ENABLE=false 时退回 OneBot 模式，
正好就是 SnowLuma 要的，整体覆盖安全。

安全性：只读 qq_bridge_official/，不改动任何旧仓一个字节；只写 qq_bridge_snowluma/。
junk（__pycache__ / _backup_* / *.bak-* / *.pyc）不复制、镜像删除时也不误删目录。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

OFFICIAL = Path("D:/AI/manju_agent/qq_bridge_official")
DEST = Path("D:/AI/manju_agent/qq_bridge_snowluma")
MANIFEST = DEST / "tools" / "copy_manifest.json"

# 要同步的业务代码（相对根目录）
SYNC_TOP = ["bot.py", "pyproject.toml", "requirements.txt", "src", "tests"]

# 本副本专属、绝不被覆盖/删除的文件与目录（相对 DEST 根）
PROTECTED = {
    ".env", ".env.example", ".gitignore", "copy_manifest.json", "README.md",
    "docker-compose.snowluma.yml", "start_snowluma.ps1", "stop_snowluma.ps1",
    "scripts", "tools", "docker", "data", "snowluma", "tmp", "logs", "downloads",
    "docs",  # 保留 docs/legacy
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_junk(path: Path) -> bool:
    name = path.name
    if name == "__pycache__" or name.endswith(".pyc"):
        return True
    if name.startswith("_backup_"):
        return True
    if ".bak-" in name or name.endswith(".bak"):
        return True
    if name in {".DS_Store", "Thumbs.db"}:
        return True
    return False


def copy_one(src: Path, dst: Path, manifest: dict) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    rel = str(dst.relative_to(DEST))
    manifest[rel] = {
        "source": rel,  # 业务代码结构官方与副本平行，rel 同义
        "size": src.stat().st_size,
        "sha256": sha256(src),
    }


def mirror_tree(src_root: Path, dst_root: Path, manifest: dict, seen: set[str]) -> None:
    """镜像 src_root -> dst_root：复制非 junk 文件，并删除 dst 中多余的（保留 PROTECTED 与 junk）。"""
    # 1) 复制
    for src in src_root.rglob("*"):
        if not src.is_file() or is_junk(src):
            continue
        rel = str(src.relative_to(OFFICIAL))
        seen.add(rel)
        copy_one(src, DEST / rel, manifest)
    # 2) 删除 dst 中不在 src 的多余文件（只删该子树内、非 junk、非 protected）
    if not dst_root.is_dir():
        return
    for dst in dst_root.rglob("*"):
        if not dst.is_file() or is_junk(dst):
            continue
        rel = str(dst.relative_to(DEST))
        if rel in PROTECTED or any(rel == p or rel.startswith(p + "/") for p in PROTECTED):
            continue
        if rel not in seen:
            dst.unlink()
            print(f"  DEL {rel}")


def main() -> None:
    if not OFFICIAL.is_dir():
        raise SystemExit(f"FAIL 官方源目录不存在: {OFFICIAL}")
    manifest: dict[str, dict] = {}
    seen: set[str] = set()

    for top in SYNC_TOP:
        s = OFFICIAL / top
        d = DEST / top
        if s.is_dir():
            print(f"[mirror] {top}/")
            mirror_tree(s, d, manifest, seen)
        elif s.is_file():
            print(f"[copy]   {top}")
            seen.add(top)
            copy_one(s, d, manifest)
        else:
            print(f"[skip]   {top} (官方源不存在)")

    data = {
        "source": str(OFFICIAL),
        "dest": str(DEST),
        "note": "2026-11-13 起业务代码源切换为 qq_bridge_official（最新 working tree）；"
                "snowluma 专属文件（.env/compose/scripts/tools/docker/运行期卷）保留不动。",
        "file_count": len(manifest),
        "files": manifest,
    }
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(v["size"] for v in manifest.values())
    print(f"OK 同步 {len(manifest)} 个文件 / {total / 1024 / 1024:.1f} MiB")
    print(f"OK manifest 已重生成（source -> {OFFICIAL}）: {MANIFEST}")


if __name__ == "__main__":
    main()
