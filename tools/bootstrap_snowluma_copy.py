"""从 qq_bridge/ 生成 qq_bridge_snowluma/ 独立副本（只读源目录，不改旧仓一个字节）。

用法（首次）：
    python tools/bootstrap_snowluma_copy.py
重新生成（会覆盖副本里的同源文件，慎用）：
    python tools/bootstrap_snowluma_copy.py --force

设计要点：
1. 只复制「运行所需代码 + 构建上下文 + 文档」，不复制运行态数据（data/logs/tmp/
   downloads/.env 备份/探针 png），新部署的数据目录必须是全新的。
2. 不复制 NapCat 专用构建产物（Dockerfile.napcat-launcher / *.so /
   qqbridge_no_autologin.py），新仓不允许出现任何 NapCat 协议端入口。
3. `.env` 由源 `.env` 派生并改写隔离项；凭据明文只在两份 `.env` 里，
   绝不打印、绝不写进 manifest / 日志 / 文档。
4. 产出 `tools/copy_manifest.json`：逐文件 sha256，供验收脚本证明「副本代码
   与源仓逐字节一致」，也证明旧仓在本次操作后没有任何改动。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import sys
from pathlib import Path

SOURCE = Path("D:/AI/manju_agent/qq_bridge")
DEST = Path("D:/AI/manju_agent/qq_bridge_snowluma")
MANIFEST = DEST / "tools" / "copy_manifest.json"

TOP_FILES = {
    "bot.py": "bot.py",
    "pyproject.toml": "pyproject.toml",
    "requirements.txt": "requirements.txt",
    ".dockerignore": ".dockerignore",
    ".env.example": ".env.example",
    "README.md": "docs/legacy/README.md",
    "AGENTS.md": "docs/legacy/AGENTS.md",
}

TOP_DIRS = [
    "src",
    "tools",
    "tests",
    "scripts",
    "docs",
]

DOCKER_FILES = [
    "docker/Dockerfile.bridge",
    "docker/bin/aria2c",
]
DOCKER_DIRS = [
    "docker/wheels",
]

# 派生 .env 时强制改写的隔离项。值为 None 表示置空。
ENV_OVERRIDES: dict[str, str | None] = {
    "HOST": "0.0.0.0",
    "PORT": "8082",
    # 原仓 .env 的 OFFICIAL_ENABLE=true 会让副本去连 AppID（单连接语义），
    # 与正在运行的 qq-bridge-official 互踢。副本是纯 OneBot/SnowLuma 通道。
    "OFFICIAL_ENABLE": "false",
    "OFFICIAL_APPID": None,
    "OFFICIAL_SECRET": None,
    # 独立鉴权：不能与旧仓共用同一个 OneBot token。
    "ONEBOT_V11_ACCESS_TOKEN": secrets.token_hex(16),
    # 登录号由 SnowLuma 扫码决定，不由 .env 预设；避免显示/使用旧号。
    "BOT_UIN": None,
    # 出站闸是 fail-closed：新号默认不允许往任何群发消息，需用户显式填写。
    "GROUP_WHITELIST": None,
    # 容器内 localhost 不是宿主，主项目能力一律走 host.docker.internal。
    "MANJU_API_BASE": "http://host.docker.internal:7788/api/v1",
    "MANJU_FILE_BASE": "http://host.docker.internal:7788",
}

ENV_APPEND: dict[str, str] = {
    # noVNC 远程桌面密码（等价于能操作 QQ 的桌面，必须强随机）。
    # ⚠️ VNC 的 DES 认证只取密码前 8 个字符：镜像 start.sh 用
    #    `x11vnc -storepasswd "${VNC_STORE_PASS}" /root/.vnc/passwd`，
    #    24 位 hex 会被静默截成 8 位，导致「.env 里的值 ≠ 实际登录值」。
    #    直接生成 8 位（token_hex(4)），让配置与生效值一致。
    "VNC_PASSWD": secrets.token_hex(4),
}


def skipped(rel: Path) -> bool:
    """副本不需要的路径：缓存 / 运行态 / 旧协议端 / 根目录探针图。"""
    parts = rel.parts
    names = set(parts)
    if "__pycache__" in names or ".pytest_cache" in names or ".venv" in names:
        return True
    if rel.suffix in {".pyc", ".pyo"}:
        return True
    if parts[:2] == ("src", "data") and "pic_cache" in names:
        return True
    if any(p.startswith("_backup_") or ".bak" in p for p in parts):
        return True
    # 根目录的历史探针/预览 png 不进副本；src/ 与 docs/ 下的图片资源要保留。
    if len(parts) == 1 and rel.suffix.lower() in {".png", ".jpg", ".jpeg", ".html", ".txt"}:
        return True
    if len(parts) == 1 and parts[0].startswith("_"):
        return True
    return False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_one(src_rel: str, dst_rel: str, manifest: dict) -> None:
    src = SOURCE / src_rel
    dst = DEST / dst_rel
    if not src.is_file():
        raise FileNotFoundError(f"源文件缺失: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    manifest[dst_rel] = {"source": src_rel, "size": src.stat().st_size, "sha256": sha256(src)}


def copy_tree(src_rel: str, dst_rel: str, manifest: dict) -> None:
    src_root = SOURCE / src_rel
    if not src_root.is_dir():
        raise FileNotFoundError(f"源目录缺失: {src_root}")
    for src in sorted(src_root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(SOURCE)
        if skipped(rel):
            continue
        target_rel = str(Path(dst_rel) / src.relative_to(src_root))
        copy_one(str(rel), target_rel, manifest)


def derive_env() -> list[str]:
    """逐行改写源 .env，保留注释/顺序/其它键值，绝不输出任何值。"""
    src = SOURCE / ".env"
    dst = DEST / ".env"
    lines = src.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out = [
        "# qq_bridge_snowluma 独立副本配置（由 qq_bridge/.env 派生，2026-11-13）",
        "# 与旧仓绝不共用：端口 / OneBot token / 官方通道连接权 / 登录号 / 群白名单",
        "# 改动项清单见根目录 DEPLOY_SNOWLUMA.md；本文件含凭据，禁止提交、禁止贴日志。",
    ]
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in ENV_OVERRIDES:
                value = ENV_OVERRIDES[key] or ""
                out.append(f"{key}={value}")
                seen.add(key)
                continue
            if key in ENV_APPEND:
                seen.add(key)
        out.append(line)
    appended: list[str] = []
    for key, value in ENV_OVERRIDES.items():
        if key not in seen:
            appended.append(f"{key}={value or ''}")
    for key, value in ENV_APPEND.items():
        if key not in seen:
            appended.append(f"{key}={value}")
    if appended:
        out += ["", "# ---- 副本新增项 ----"] + appended
    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    return sorted(seen | set(appended and ENV_APPEND.keys()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="允许覆盖已生成的副本")
    args = ap.parse_args()

    if not SOURCE.is_dir():
        print(f"FAIL 源目录不存在: {SOURCE}")
        return 1
    if MANIFEST.exists() and not args.force:
        print(f"FAIL 副本已生成（{MANIFEST}）。如需重建请显式加 --force。")
        return 1

    manifest: dict[str, dict] = {}
    for src_rel, dst_rel in TOP_FILES.items():
        copy_one(src_rel, dst_rel, manifest)
    for rel in TOP_DIRS:
        copy_tree(rel, rel, manifest)
    for rel in DOCKER_FILES:
        copy_one(rel, rel, manifest)
    for rel in DOCKER_DIRS:
        copy_tree(rel, rel, manifest)

    MANIFEST.write_text(
        json.dumps(
            {
                "source": str(SOURCE),
                "dest": str(DEST),
                "file_count": len(manifest),
                "files": manifest,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    derive_env()
    changed = sorted(set(ENV_OVERRIDES) | set(ENV_APPEND))

    total = sum(v["size"] for v in manifest.values())
    print(f"OK 复制 {len(manifest)} 个文件 / {total / 1024 / 1024:.1f} MiB")
    print(f"OK manifest: {MANIFEST}")
    print(f"OK .env 派生完成，改写/新增键: {', '.join(changed)}")
    print("OK 源目录只读，未写入任何文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
