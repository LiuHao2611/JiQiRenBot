"""SnowLuma 新部署验收（prove-it：每条规则都要有能拦住它的判据）。

    python scripts/verify_snowluma_deploy.py              # 全量验收
    python scripts/verify_snowluma_deploy.py --skip-containers   # 只验静态/隔离
    python scripts/verify_snowluma_deploy.py --selftest          # 反例注入自测

判定分三级：PASS / FAIL（退出码 1） / WARN（不阻断，需人工确认）。
绝不打印任何凭据值：只报告「已设置 / 与源不同 / 是否为空」等布尔结论。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path("D:/AI/manju_agent/qq_bridge")
OFFICIAL = Path("D:/AI/manju_agent/qq_bridge_official")
COMPOSE = ROOT / "docker-compose.snowluma.yml"
MANIFEST = ROOT / "tools" / "copy_manifest.json"

OLD_CONTAINER = "qq-bridge-official"
CONTAINERS = {
    "qq-bridge-snowluma-bridge": "8082",
    "qq-bridge-snowluma-protocol": "5099/6081",
    "qq-bridge-snowluma-aria2": "6802",
}
NAPCAT_ARTIFACTS = [
    "docker/Dockerfile.napcat-launcher",
    "docker/qqbridge_no_autologin.py",
    "docker-compose.napcat.yml",
    "docker-compose.bridge.yml",
    "docker/libnapcat_launcher_amd64.so",
]

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str) -> None:
    results.append((status, name, detail))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=ROOT)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 99, type(exc).__name__


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ---------------------------------------------------------------------------
# 纯函数：便于 --selftest 注入反例
# ---------------------------------------------------------------------------
def check_env_isolation(env: dict[str, str], src_env: dict[str, str]) -> list[str]:
    problems = []
    if env.get("OFFICIAL_ENABLE", "").lower() not in {"false", "0", "no"}:
        problems.append("OFFICIAL_ENABLE 未关闭（会与官方机器人抢 AppID 单连接）")
    if env.get("PORT") != "8082":
        problems.append("PORT 不是 8082（会与旧仓/官方副本冲突）")
    if env.get("OFFICIAL_APPID") or env.get("OFFICIAL_SECRET"):
        problems.append("副本仍携带官方凭据")
    if env.get("BOT_UIN"):
        problems.append("BOT_UIN 未清空（登录号应由 SnowLuma 扫码决定）")
    if env.get("GROUP_WHITELIST"):
        problems.append("GROUP_WHITELIST 非空（新号不应自动向旧群发消息）")
    if not env.get("ONEBOT_V11_ACCESS_TOKEN"):
        problems.append("OneBot token 为空")
    elif env.get("ONEBOT_V11_ACCESS_TOKEN") == src_env.get("ONEBOT_V11_ACCESS_TOKEN"):
        problems.append("OneBot token 与旧仓相同（未隔离）")
    if not env.get("VNC_PASSWD"):
        problems.append("VNC_PASSWD 为空（noVNC 远程桌面无密码）")
    return problems


COMPOSE_REQUIRED = [
        ("name: qq_bridge_snowluma", "项目名未隔离"),
        ("image: qq-bridge-snowluma:latest", "bridge 镜像名未隔离"),
        ("motricseven7/snowluma:v2.2.0", "SnowLuma 未钉固定版本"),
        ("restart: \"no\"", "协议端 restart 不是 no（会自动重登）"),
        ("SYS_PTRACE", "缺 ptrace 能力"),
        ("seccomp=unconfined", "缺 seccomp 放开"),
        ("shm_size: 1gb", "缺 /dev/shm 1gb"),
        ("SNOWLUMA_HOOK_AUTOLOAD: \"1\"", "缺扫码后自动加载 hook"),
        ("OFFICIAL_ENABLE: \"false\"", "bridge 未强制关闭官方适配器"),
        ("OPS_CONN_WATCH_ENABLE: \"false\"", "conn_watch 噪音未关闭"),
        ("ws://bridge:8082/onebot/v11/ws", "缺反向 WS 契约说明"),
        ("127.0.0.1:6081:6081", "noVNC 未绑回环"),
        ("127.0.0.1:5099:5099", "WebUI 未绑回环"),
        ("hostname: snowluma-home", "容器设备名未固定"),
        ("mac_address: \"02:42:ac:1f:5a:0a\"", "容器 MAC 未固定"),
        ("ipv4_address: 172.31.90.10", "容器内网 IP 未固定"),
]


def check_compose_contract(text: str) -> list[str]:
    problems = []
    for needle, msg in COMPOSE_REQUIRED:
        if needle not in text:
            problems.append(msg)
    if "3000:3000" in text or "3001:3001" in text:
        problems.append("把 SnowLuma 正向 WS/HTTP 端口映射到了宿主")
    if "latest" in text and "motricseven7/snowluma:latest" in text:
        problems.append("SnowLuma 用了浮动 latest")
    return problems


def check_napcat_free(paths: list[str]) -> list[str]:
    hits = [p for p in paths if p in NAPCAT_ARTIFACTS]
    return [f"副本残留 NapCat 协议端文件: {', '.join(hits)}"] if hits else []


# ---------------------------------------------------------------------------
# 实际检查
# ---------------------------------------------------------------------------
def check_manifest() -> None:
    if not MANIFEST.is_file():
        record("FAIL", "副本清单", "tools/copy_manifest.json 不存在")
        return
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = data["files"]
    # 副本「可改」：本地修复过的文件在 manifest.local_fixes 里登记当前 sha256，
    # 副本侧按登记值校验，源仓侧仍按初始快照校验 —— 两边都诚实，不伪造一致。
    local_fixes: dict[str, str] = data.get("local_fixes") or {}
    # 业务代码源以清单里的 source 字段为准：最初来自 NapCat，2026-11-13 起
    # 切到官方 qq_bridge_official（最新 working tree）。不要再硬编码 NapCat。
    src_root = Path(data.get("source") or str(SOURCE))
    bad_dst, bad_src, bad_fix = [], [], []
    for rel, meta in files.items():
        dst = ROOT / rel
        expected = local_fixes.get(rel, meta["sha256"])
        if not dst.is_file() or sha256(dst) != expected:
            bad_dst.append(rel)
        if rel in local_fixes and not (ROOT / rel).is_file():
            bad_fix.append(rel)
        src = src_root / meta["source"]
        if not src.is_file() or sha256(src) != meta["sha256"]:
            bad_src.append(rel)
    if bad_dst or bad_fix:
        record("FAIL", "副本文件完整性",
               f"{len(bad_dst)} 个文件 sha256 与登记不符，例: {bad_dst[:3]}")
    else:
        record("PASS", "副本文件完整性",
               f"{len(files) - len(local_fixes)} 个与初始快照一致 + "
               f"{len(local_fixes)} 个已登记本地修复 sha 校验通过")
    if local_fixes:
        record("WARN", "副本本地修复",
               f"{len(local_fixes)} 个文件有意偏离源仓快照（manifest.local_fixes 已登记）；"
               f"源仓仍逐字节未改")
    if bad_src:
        record("WARN", "源仓未被改写", f"{len(bad_src)} 个源文件与复制时快照不同（可能是其它会话改动）: {bad_src[:3]}")
    else:
        record("PASS", "源仓未被改写", "全部源文件仍与复制时快照逐字节一致")


def check_isolation() -> None:
    env, src = read_env(ROOT / ".env"), read_env(SOURCE / ".env")
    problems = check_env_isolation(env, src)
    record("FAIL" if problems else "PASS", ".env 隔离项",
           "; ".join(problems) if problems else "11 项改写全部生效（不打印值）")
    hits = [p for p in NAPCAT_ARTIFACTS if (ROOT / p).exists()]
    probs = check_napcat_free(hits)
    record("FAIL" if hits else "PASS", "无 NapCat 协议端残留",
           "; ".join(probs) if hits else "NapCat 镜像/compose/注入脚本共 5 类均不存在")
    probs = check_compose_contract(COMPOSE.read_text(encoding="utf-8"))
    record("FAIL" if probs else "PASS", "compose 静态契约",
           "; ".join(probs) if probs else f"{len(COMPOSE_REQUIRED)} 项必需字段齐全")
    rc, out = run(["docker", "compose", "-f", str(COMPOSE), "config", "--quiet"])
    record("PASS" if rc == 0 else "FAIL", "compose 变量展开",
           "config --quiet 通过" if rc == 0 else out.strip().splitlines()[0][:140] if out.strip() else f"rc={rc}")
    vp = check_vnc_password_length(env.get("VNC_PASSWD", ""))
    record("FAIL" if vp else "PASS", "VNC 口令长度",
           "; ".join(vp) if vp else "8 位，与 x11vnc -rfbauth 实际校验值一致")


def check_secret_leak() -> None:
    env = read_env(ROOT / ".env")
    secrets = [v for k, v in env.items() if v and k in {
        "ONEBOT_V11_ACCESS_TOKEN", "VNC_PASSWD", "OFFICIAL_SECRET",
        "AI_API_KEY", "SEED_TTS_API_KEY", "DL_ARIA2_SECRET",
    }]
    hits: list[str] = []
    exts = {".py", ".yml", ".yaml", ".md", ".ps1", ".json", ".toml"}
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        rel = p.relative_to(ROOT)
        if p.name in {".env", "copy_manifest.json"} or ".env" in p.parts:
            continue
        # 运行态 onebot*.json 必然含 accessToken（OneBot 协议要求），
        # 它是容器生成/脚本注入的产物，不是源码或文档；由下面的
        # check_runtime_credentials() 单独把「必须被 gitignore」这道闸看住。
        if rel.parts[:3] == ("snowluma", "data", "config") and rel.name.startswith("onebot"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(s in text for s in secrets):
            hits.append(str(rel))
    record("FAIL" if hits else "PASS", "源码/文档凭据审计",
           f"明文出现在: {hits[:5]}" if hits else "源码 / 文档 / 编排中零明文")
    rc, _ = run(["git", "check-ignore", str(ROOT / ".env")])
    record("PASS" if rc == 0 else "WARN", ".env 不被 git 跟踪",
           "check-ignore 命中" if rc == 0 else "未命中，请确认主仓 .gitignore")


def check_mode_values(modes: list[str]) -> list[str]:
    """纯函数：运行态凭据文件必须是 0600，供 selftest 注入反例。"""
    return [f"权限过宽: {m}" for m in modes if m.strip() and m.strip() != "600"]


def check_wsclient_placement(facts: dict) -> list[str]:
    """纯函数：wsClients 必须在 networks 下，且指向本副本 bridge。

    SnowLuma v2.2.0 的 onebot.json 结构是
    {networks:{httpServers,wsServers,httpClients,wsClients}, ...}；
    顶层 wsClients 是网上旧示例的写法，应用根本不读。
    """
    problems = []
    if facts.get("top_level"):
        problems.append("存在无效的顶层 wsClients（应用不读，应删除）")
    if facts.get("nested_count", 0) != 1:
        problems.append(f"networks.wsClients 条目数={facts.get('nested_count')}，应为 1")
    if facts.get("url") != "ws://bridge:8082/onebot/v11/ws":
        problems.append("WS 客户端 URL 未指向本副本 bridge:8082")
    if not facts.get("token_set"):
        problems.append("networks.wsClients 未携带 accessToken")
    return problems


def check_vnc_password_length(value: str) -> list[str]:
    """纯函数：VNC DES 认证只取前 8 字符，配置必须就是 8 位。

    镜像 /root/start.sh 用 `x11vnc -storepasswd "${VNC_STORE_PASS}"
    /root/.vnc/passwd`，超过 8 位会被静默截断，表现为输 .env 里的全串
    报 `password check failed!`，而实际生效的是前 8 位。
    """
    if not value:
        return ["VNC_PASSWD 为空（noVNC 无密码）"]
    if len(value) > 8:
        return [f"VNC_PASSWD 为 {len(value)} 位，x11vnc 只认前 8 位，配置与实际值不一致"]
    return []


def check_warframe_data(dest: Path) -> list[str]:
    """纯函数：紫卡分析必需的三张派生表必须存在、非空且可解析。

    2026-11-13 事故：data/ 被 gitignore 且不在镜像里，全新部署只有
    _sync_state.json，OCR 读对全部词条却解析失败。部署验收必须拦住它。
    """
    problems = []
    for name in ("riven_disp.json", "riven_stat_base.json", "riven_stat_zh.json"):
        p = dest / name
        if not p.is_file():
            problems.append(f"缺 {name}")
            continue
        try:
            if not json.loads(p.read_text(encoding="utf-8")):
                problems.append(f"{name} 为空")
        except Exception as e:  # noqa: BLE001 — 验收要把原因报全
            problems.append(f"{name} 不可解析: {type(e).__name__}")
    return problems


def check_warframe_static_data() -> None:
    """实际检查：直接跑 prepare 脚本的 --check（覆盖全部 7 个必需文件）。"""
    rc, out = run([sys.executable, str(ROOT / "scripts" / "prepare_warframe_data.py"), "--check"])
    lines = [ln.strip() for ln in out.strip().splitlines()
             if ln.strip() and "Could not find platform" not in ln]
    detail = next((ln for ln in reversed(lines) if ln.startswith("check:")),
                  lines[-1] if lines else "无输出")
    record("PASS" if rc == 0 else "FAIL", "紫卡静态词库",
           detail if rc == 0 else f"{detail}（修复：python scripts/prepare_warframe_data.py）")


def check_runtime_credentials() -> None:
    cfg = ROOT / "snowluma" / "data" / "config"
    files = sorted(cfg.glob("onebot*.json")) if cfg.is_dir() else []
    if not files:
        record("WARN", "运行态凭据隔离", "尚未生成 onebot*.json（首次启动后生成）")
        return
    leaked: list[str] = []
    for p in files:
        rc, _ = run(["git", "check-ignore", str(p)])
        if rc != 0:
            leaked.append(p.name)
    record("FAIL" if leaked else "PASS", "运行态凭据隔离",
           f"{len(files)} 个 onebot*.json，未被 gitignore: {leaked}" if leaked
           else f"{len(files)} 个 onebot*.json 含 token 属正常，全部被 gitignore 排除")
    rc, modes = run([
        "docker", "exec", "qq-bridge-snowluma-protocol", "sh", "-c",
        "stat -c '%a' /app/data/config/onebot*.json",
    ])
    if rc != 0:
        record("WARN", "运行态凭据权限", "协议端容器未运行，跳过 0600 检查")
        return
    bad = check_mode_values(modes.splitlines())
    record("FAIL" if bad else "PASS", "运行态凭据权限",
           "; ".join(bad) if bad else "全部 onebot*.json 为 0600 且属主 node")


def check_containers() -> None:
    rc, out = run(["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.Ports}}"])
    if rc != 0:
        record("FAIL", "容器状态", f"docker ps 失败 rc={rc}")
        return
    lines = out.strip().splitlines()
    by_name = {ln.split("|", 1)[0]: ln for ln in lines if "|" in ln}
    for name, ports in CONTAINERS.items():
        line = by_name.get(name)
        if not line:
            record("FAIL", f"容器 {name}", "不存在")
        elif "Up " not in line:
            record("FAIL", f"容器 {name}", f"未运行: {line.split('|')[1]}")
        else:
            record("PASS", f"容器 {name}", f"运行正常 | {ports}")
    if OLD_CONTAINER not in by_name:
        record("WARN", "旧官方机器人未受影响", f"{OLD_CONTAINER} 当前不在运行（非本次操作所致？请确认）")
    else:
        record("PASS", "旧官方机器人未受影响", f"{OLD_CONTAINER} 仍在，8081 未被抢占")
    rc, caps = run(["docker", "exec", "qq-bridge-snowluma-protocol", "getcap", "/usr/local/bin/node"])
    ok = rc == 0 and "cap_sys_ptrace" in caps
    record("PASS" if ok else "FAIL", "ptrace 注入能力",
           "node 具备 cap_sys_ptrace" if ok else f"getcap 未通过 rc={rc}: {caps.strip()[:100]}")
    rc, net = run([
        "docker", "exec", "qq-bridge-snowluma-protocol", "node", "-e",
        "require('net').connect(8082,'bridge').on('connect',()=>{console.log('OPEN');process.exit(0)}).on('error',e=>{console.log(e.code);process.exit(1)})",
    ])
    record("PASS" if rc == 0 and "OPEN" in net else "FAIL", "容器内网连通",
           "snowluma -> bridge:8082 可达" if rc == 0 else f"不可达: {net.strip()[:100]}")
    rc, ws = run([sys.executable, str(ROOT / "scripts" / "setup_snowluma_ws.py"), "--check"])
    record("PASS" if rc == 0 else "WARN", "wsClients 配置",
           "已指向本副本 bridge" if rc == 0 else "尚未配置（扫码后运行 setup 脚本）")
    probe = (
        "const o=JSON.parse(require('fs').readFileSync('/app/data/config/onebot.json','utf8'));"
        "const n=o.networks||{};const l=Array.isArray(n.wsClients)?n.wsClients:[];"
        "console.log(JSON.stringify({top_level:Object.prototype.hasOwnProperty.call(o,'wsClients'),"
        "nested_count:l.length,url:(l[0]||{}).url||'',token_set:!!((l[0]||{}).accessToken)}))"
    )
    rc, facts_raw = run(["docker", "exec", "qq-bridge-snowluma-protocol", "node", "-e", probe])
    if rc != 0:
        record("WARN", "wsClients 落点", "容器未就绪，跳过结构检查")
        return
    try:
        problems = check_wsclient_placement(json.loads(facts_raw.strip().splitlines()[-1]))
    except (ValueError, IndexError):
        problems = ["无法解析 onebot.json 结构"]
    record("FAIL" if problems else "PASS", "wsClients 落点",
           "; ".join(problems) if problems else "位于 networks.wsClients（非无效的顶层字段）")


def selftest() -> None:
    good_env = {
        "OFFICIAL_ENABLE": "false", "PORT": "8082", "OFFICIAL_APPID": "",
        "OFFICIAL_SECRET": "", "BOT_UIN": "", "GROUP_WHITELIST": "",
        "ONEBOT_V11_ACCESS_TOKEN": "aaa", "VNC_PASSWD": "bbb",
    }
    good_src = {"ONEBOT_V11_ACCESS_TOKEN": "zzz"}
    wf_missing = Path(tempfile.mkdtemp(prefix="wfdata_missing_"))
    wf_blank = Path(tempfile.mkdtemp(prefix="wfdata_blank_"))
    for name in ("riven_disp.json", "riven_stat_base.json", "riven_stat_zh.json"):
        (wf_blank / name).write_text("{}", encoding="utf-8")
    cases = [
        ("词库反例: 三张派生表全缺", check_warframe_data(wf_missing)),
        ("词库反例: 派生表内容为空", check_warframe_data(wf_blank)),
        ("env 反例: 官方通道未关", check_env_isolation({**good_env, "OFFICIAL_ENABLE": "true"}, good_src)),
        ("env 反例: 端口撞旧仓", check_env_isolation({**good_env, "PORT": "8080"}, good_src)),
        ("env 反例: 群白名单沿用", check_env_isolation({**good_env, "GROUP_WHITELIST": "12345"}, good_src)),
        ("env 反例: token 与旧仓相同", check_env_isolation({**good_env, "ONEBOT_V11_ACCESS_TOKEN": "zzz"}, good_src)),
        ("compose 反例: 协议端自动重启", check_compose_contract(
            COMPOSE.read_text(encoding="utf-8").replace('restart: "no"', 'restart: unless-stopped'))),
        ("compose 反例: 浮动 latest", check_compose_contract(
            COMPOSE.read_text(encoding="utf-8").replace("motricseven7/snowluma:v2.2.0", "motricseven7/snowluma:latest"))),
        ("compose 反例: 缺 ptrace", check_compose_contract(
            COMPOSE.read_text(encoding="utf-8").replace("SYS_PTRACE", "SYS_ADMIN"))),
        ("compose 反例: 设备名漂移", check_compose_contract(
            COMPOSE.read_text(encoding="utf-8").replace("hostname: snowluma-home", "hostname: snowluma-tmp"))),
        ("compose 反例: conn_watch 打开", check_compose_contract(
            COMPOSE.read_text(encoding="utf-8").replace('OPS_CONN_WATCH_ENABLE: "false"', 'OPS_CONN_WATCH_ENABLE: "true"'))),
        ("隔离反例: 残留 NapCat", check_napcat_free(["docker/Dockerfile.napcat-launcher"])),
        ("compose 反例: MAC 漂移", check_compose_contract(
            COMPOSE.read_text(encoding="utf-8").replace('mac_address: "02:42:ac:1f:5a:0a"', 'mac_address: "02:42:ac:1f:5a:0b"'))),
        ("权限反例: 凭据文件 0644", check_mode_values(["644"])),
        ("落点反例: 顶层 wsClients", check_wsclient_placement(
            {"top_level": True, "nested_count": 0, "url": "", "token_set": False})),
        ("落点反例: URL 指错端口", check_wsclient_placement(
            {"top_level": False, "nested_count": 1, "url": "ws://bridge:8080/onebot/v11/ws", "token_set": True})),
        ("VNC 反例: 24 位密码", check_vnc_password_length("a" * 24)),
    ]
    failed = 0
    for name, problems in cases:
        ok = bool(problems)
        print(("[PASS] " if ok else "[FAIL] ") + name + (" -> 已拦住" if ok else " -> 反例没被拦住！"))
        failed += 0 if ok else 1
    print(f"\nselftest: {len(cases) - failed}/{len(cases)} 类反例被拦住")
    sys.exit(1 if failed else 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--skip-containers", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    check_manifest()
    check_isolation()
    check_warframe_static_data()
    check_secret_leak()
    check_runtime_credentials()
    if not args.skip_containers:
        check_containers()
    else:
        record("WARN", "容器状态", "--skip-containers，未做运行时验收")
    print(f"\n{'状态':<6}{'检查项':<26}说明")
    print("-" * 100)
    for status, name, detail in results:
        print(f"{status:<6}{name:<26}{detail}")
    fails = sum(1 for s, _, _ in results if s == "FAIL")
    warns = sum(1 for s, _, _ in results if s == "WARN")
    print("-" * 100)
    print(f"合计: {len(results)} 项 | FAIL {fails} | WARN {warns} | PASS {len(results) - fails - warns}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
