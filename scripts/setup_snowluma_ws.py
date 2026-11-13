"""把 SnowLuma 的 OneBot v11「WS 客户端」指向本副本的 bridge（幂等）。

为什么需要这个脚本
------------------
SnowLuma 官方 Docker 文档只讲它当 **WS 服务端**（3000/3001）；而本项目的 bridge
是 **反向 WS 服务端**（NoneBot2 OneBot V11），必须由 SnowLuma 作为客户端主动连过来：

    SnowLuma(WS 客户端) --出站--> ws://bridge:8082/onebot/v11/ws --> bridge

这个能力在 WebUI「OneBot 协议端点 → WS 客户端」，落盘为
`/app/data/config/onebot*.json` 的 **`networks.wsClients`** 字段。

⚠️ 2026-11-13 实测纠错：网上流传的 compose/JSON 示例把 `wsClients` 写在
**顶层**，但 SnowLuma v2.2.0 生成的 `onebot.json` 结构是
`{networks:{httpServers,wsServers,httpClients,wsClients}, ...}`，
顶层 `wsClients` **不会被读取**（表现为 OneBot 模块完全不发起连接、日志零
WS-Client 行）。本脚本只写 `networks.wsClients`，并删除历史误写的顶层字段。

账号级 `onebot_<uin>.json` 是 overlay，会覆盖基础 `onebot.json`，所以脚本对
**所有** onebot*.json 都写入同一份 wsClients，避免「改错文件等于白改」。

实现要点
--------
* 通过 `docker exec -i <container> node -` 从 stdin 传脚本，在容器内以正确
  属主/权限改文件；不让 token 出现在命令行、日志或命令输出里。
* 只覆盖 `wsClients`，其余字段原样保留（JSON 解析失败即报错，不猜测、不重建）。
* `--check` 只读检查；默认写入后需 `docker compose restart snowluma` 才生效。

用法
----
    python scripts/setup_snowluma_ws.py --check
    python scripts/setup_snowluma_ws.py
    docker compose -f docker-compose.snowluma.yml restart snowluma
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTAINER = "qq-bridge-snowluma-protocol"
WS_URL = "ws://bridge:8082/onebot/v11/ws"
CONFIG_DIR = "/app/data/config"


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def build_js(client: dict, check_only: bool) -> str:
    payload = json.dumps(client, ensure_ascii=False)
    action = "check" if check_only else "write"
    return f"""
const fs = require('fs');
const path = require('path');
const dir = {json.dumps(CONFIG_DIR)};
const client = {payload};
const action = {json.dumps(action)};
if (!fs.existsSync(dir)) {{ console.log('NO_CONFIG_DIR'); process.exit(2); }}
const files = fs.readdirSync(dir).filter(f => /^onebot.*\\.json$/i.test(f)).sort();
if (!files.length) {{ console.log('NO_ONEBOT_CONFIG'); process.exit(3); }}
let bad = 0;
for (const f of files) {{
  const p = path.join(dir, f);
  let obj;
  try {{ obj = JSON.parse(fs.readFileSync(p, 'utf8')); }}
  catch (e) {{ console.log('BAD_JSON ' + f); bad++; continue; }}
  if (!obj.networks || typeof obj.networks !== 'object') obj.networks = {{}};
  const cur = JSON.stringify(obj.networks.wsClients || []);
  const want = JSON.stringify([client]);
  const stale = Object.prototype.hasOwnProperty.call(obj, 'wsClients');
  const ok = cur === want && !stale;
  if (action === 'check') {{
    console.log((ok ? 'MATCH ' : 'DIFF  ') + f + (stale ? ' (stale top-level wsClients)' : ''));
    if (!ok) bad++;
    continue;
  }}
  obj.networks.wsClients = [client];
  delete obj.wsClients;
  fs.writeFileSync(p, JSON.stringify(obj, null, 2) + '\\n', {{ mode: 0o600 }});
  // writeFileSync 的 mode 只在新建时生效；已有文件必须显式收紧，
  // 否则含 accessToken 的配置会停留在 0644（容器内任意用户可读）。
  fs.chmodSync(p, 0o600);
  console.log('UPDATED ' + f + ' mode=0600');
}}
process.exit(bad ? 1 : 0);
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查，不写入")
    ap.add_argument("--container", default=DEFAULT_CONTAINER)
    args = ap.parse_args()

    env = read_env()
    token = env.get("ONEBOT_V11_ACCESS_TOKEN", "")
    if not token:
        print("FAIL .env 缺少 ONEBOT_V11_ACCESS_TOKEN（不允许无鉴权接入）")
        return 1
    if env.get("OFFICIAL_ENABLE", "").lower() not in {"false", "0", "no"}:
        print("FAIL .env 里 OFFICIAL_ENABLE 必须为 false（防止抢占 AppID 单连接）")
        return 1

    client = {
        "name": "qq_bridge_snowluma",
        "enabled": True,
        "url": WS_URL,
        "role": "Universal",
        # NoneBot OneBot V11 反向 WS 服务端按 Authorization: Bearer 校验。
        "accessToken": token,
        "messageFormat": "array",
        "reconnectIntervalMs": 5000,
    }

    cmd = ["docker", "exec", "-i", args.container, "node", "-"]
    try:
        proc = subprocess.run(
            cmd,
            input=build_js(client, args.check).encode("utf-8"),
            capture_output=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL 无法在容器内执行配置脚本: {type(exc).__name__}")
        return 1

    # stdout 只含文件名与状态，不含 token；stderr 只透传错误类型，不透传原始内容。
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith(("MATCH ", "DIFF  ", "UPDATED ", "NO_", "BAD_JSON")):
            print(line)
    if proc.returncode == 2:
        print("FAIL 容器内尚无 /app/data/config —— 先启动一次 SnowLuma 让它生成配置")
    elif proc.returncode == 3:
        print("FAIL 尚未发现 onebot*.json —— 先在 WebUI 完成首次引导，或启动容器后再跑")
    elif proc.returncode != 0:
        print(f"FAIL 配置{'检查' if args.check else '写入'}未通过（rc={proc.returncode}）")
        if proc.stderr:
            print("       stderr 首行: " + proc.stderr.decode("utf-8", "replace").splitlines()[0][:160])
    else:
        print("OK " + ("wsClients 检查通过" if args.check else "wsClients 已写入"))
        if not args.check:
            print("下一步: docker exec qq-bridge-snowluma-protocol supervisorctl restart snowluma")
        print("       （只重载应用进程，不重启 QQ / noVNC；扫码后账号级配置生成时需再跑一次本脚本）")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
