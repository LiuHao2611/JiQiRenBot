# qq_bridge_snowluma · SnowLuma 协议端独立部署副本

> 建立于 2026-11-13。目标：NapCat 风控严重 → 换用 SnowLuma 作为 QQ 协议端，
> **全新 Docker 部署，旧仓一个字节都不改**。
> 对应最高声明（2026-11-10）：`qq_bridge/` 原 NapCat 代码永久只读；新通道 = 完整独立副本。

---

## 0. 先读风险（换平台不等于消除风控）

| 事实 | 说明 |
|---|---|
| SnowLuma 仍是第三方注入 | 容器内跑真实 Linux QQ，用 `ptrace` 注入 hook；**不是官方接口**，仍有封号/风控风险。社区反馈「比 NapCat 稳」只是经验，无安全承诺 |
| 许可 | 源码可见的**非商业许可**（非 OSI 开源）；商用、公开发布衍生版需书面授权 |
| 账号 | 建议小号。**同一 QQ 号不能同时在 NapCat 与 SnowLuma 在线**，会互踢并抬高风控 |
| 自动重登 | 协议端容器 `restart: "no"`，且不要加任何守护脚本。被踢线后人工确认再 `docker start` |
| 远程桌面 | `6081` 等于一台能操作 QQ 的桌面，只绑 `127.0.0.1`，绝不裸放公网 |

---

## 1. 三套部署对照（隔离验收的依据）

| | `qq_bridge/`（旧 NapCat） | `qq_bridge_official/`（官方） | **`qq_bridge_snowluma/`（本副本）** |
|---|---|---|---|
| 状态 | **冻结只读**，本次零改动 | 运行中，本次零改动 | 新建，可改 |
| 协议端 | NapCat 容器 | QQ 开放平台 AppID（WS 出站） | SnowLuma 容器（Linux QQ + ptrace） |
| 业务端口 | 8080 | 8081 | **8082**（仅 `127.0.0.1`） |
| 其它端口 | 6099 WebUI | — | **5099** WebUI / **6081** noVNC / **6802** aria2 |
| compose 项目名 | `qq_bridge_standalone` / NapCat 独立 | `qq_bridge_official` | **`qq_bridge_snowluma`** |
| 容器名 | `qq-bridge` / `qq-bridge-napcat` | `qq-bridge-official` | `qq-bridge-snowluma-{bridge,protocol,aria2}` |
| 数据目录 | `qq_bridge/data` | `qq_bridge_official/data` | **本目录 `data/` + `snowluma/{data,qq-config,qq-share}`** |
| 镜像 | `qq-bridge` / `qq-bridge-napcat` | `qq-bridge-official` | **`qq-bridge-snowluma` + `motricseven7/snowluma:v2.2.0`** |

业务代码是 `qq_bridge_official/`（官方最新 working tree）的**逐字节副本**
（615 文件 / 45.8 MiB，见 `tools/copy_manifest.json`；快照里每个文件的 `source`
字段即指向官方源，而非旧 NapCat 仓），协议层换掉即可，意图路由 / 卡片渲染 /
Warframe / 管家 M1–M9 / TTS 全部零改动。

---

## 2. 链路方向（最容易接反的地方）

```
QQ 客户端(容器内真实 Linux QQ)  ←ptrace←  SnowLuma
                                            │ OneBot v11, WS 客户端【出站】
                                            ▼
                              ws://bridge:8082/onebot/v11/ws
                                            │
                                            ▼
                    bridge = NoneBot2 OneBot V11【反向 WS 服务端】
```

- bridge 是**被动方（服务端）**，SnowLuma 是**主动填地址的一方（客户端）**。
- SnowLuma 自带的 `3000`（OneBot HTTP）/ `3001`（正向 WS）本方案**不用、不映射**。
- 两个服务在**同一个 compose 项目**里，共享默认网络，因此 URL 直接写服务名 `bridge`，
  不需要 `docker network connect`（手动 connect 在容器重建后会丢）。
- 鉴权：bridge 侧 `ONEBOT_V11_ACCESS_TOKEN`，SnowLuma 侧 `wsClients[].accessToken`，
  两者必须一致；NoneBot 按 `Authorization: Bearer` 校验（401/403 = token 不对）。

---

## 3. 部署（你只需要在自己的终端跑第 1 步）

> 长期运行的容器由 Docker daemon 托管；本环境的会话结束不会带走它们。
> 但**扫码登录、WebUI 首次引导必须你本人操作**，脚本不会代你同意 EULA。

### 3.1 起容器

```powershell
cd D:\AI\manju_agent\qq_bridge_snowluma
powershell -File start_snowluma.ps1
# 或： docker compose -f docker-compose.snowluma.yml up -d --build
```

### 3.2 首次引导（人工）

1. 登录页那句「**输入访问令牌**」不是 API token：前端输入框 `name="password"`，
   它要的就是 **WebUI 初始登录密码**（容器启动时随机生成，只在日志打印一次）。
   在你自己的终端取最后一条：日志行形如
   `initial credentials: user=admin password=<16位随机串>`，
   **账号固定是 `admin`**，只有密码是随机生成、只显示一次：

   ```powershell
   # PowerShell
   docker logs qq-bridge-snowluma-protocol 2>&1 | Select-String "initial credentials" | Select-Object -Last 1
   # Git Bash
   docker logs qq-bridge-snowluma-protocol 2>&1 | grep "initial credentials" | tail -1
   ```

   ⚠️ **必须取最后一条**：只要还没改过密码，容器每次重启都会打印
   `previous bootstrap password was never rotated; regenerated a new one` 并作废旧密码。
   如果确实丢了，手动 `docker compose -f docker-compose.snowluma.yml restart snowluma`
   重新生成一条再看日志（协议端 `restart: "no"`，不会被自动拉起）。
2. 打开 `http://127.0.0.1:5099` → 用该密码登录 → **`mustChangePassword=true`，必须立刻改密**
   → **自行阅读并同意 EULA / 隐私政策**，面板才会解锁、OneBot 模块才会启动。
3. 打开 `http://127.0.0.1:6081` → noVNC 里 QQ 已自动启动 → **扫码登录**（建议小号）。
   `SNOWLUMA_HOOK_AUTOLOAD=1` 会在登录后自动加载 hook。
   ⚠️ noVNC 的密码是 `.env::VNC_PASSWD`，**和 WebUI 初始密码是两个不同的值**，别填混。
   ⚠️ **VNC 的 DES 认证只认前 8 个字符**：早期 `.env` 里生成的是 24 位 hex，
   `x11vnc -storepasswd` 静默截成前 8 位，输全串会报 `password check failed!`。
   现已把 `.env::VNC_PASSWD` 与容器内 `vnc-password` 同步截断为 8 位，
   配置值即实际生效值；生成脚本也改为 `token_hex(4)`。
4. 日志出现 `[preload] succeeded` / `[Hook] pipe connected` 即注入成功。

> **noVNC 鼠标点不动 / 二维码过期（2026-11-13 实测）**
> 桌面启动时 `fbsetbg` 会弹出一个 `xmessage` 壁纸/字体警告窗（578×96），
> 压在 QQ 登录窗口上并抢走输入焦点，表现为「指针在动但点什么都没反应」。
> 清掉它（**必须用 `-x`**；`pkill -f xmessage` 会把执行它的 shell 自己也匹配掉，
> 命令直接 143 中断）：
> `docker exec qq-bridge-snowluma-protocol pkill -x xmessage`
>
> 刷新二维码（当前没有登录态，重启 QQ **不算重登**，不触发账号风险）：
> `docker exec qq-bridge-snowluma-protocol supervisorctl restart qq`
> 约 8 秒后新码出现，hook 会自动重新注入。二维码约 60 秒过期，
> 过期就再跑一次，或鼠标恢复后直接点窗口里的「刷新」按钮。
> 不想开 noVNC 也能验画面：
> `docker exec qq-bridge-snowluma-protocol ffmpeg -y -f x11grab -video_size 1920x1080 -i :1 -frames:v 1 /tmp/qr.png`
> （截图含一次性登录凭证，用完立刻删，别留存/外传）。
>
> **扫码之后若重启过 QQ 进程（如上面的 `restart qq`）：登录界面会变成「快捷登录」，
> 不再是二维码** —— 已保存账号 + 中间一个蓝色「登录」按钮，点一下即完成登录，
> 无需重新扫码（这不等于重登，不触发账号风险）。
> 容器内没有鼠标模拟工具，需要脚本代点时：
> `docker exec qq-bridge-snowluma-protocol apt-get update -qq && apt-get install -y xdotool`
> （源在 `/etc/apt/sources.list.d/debian.sources`，deb.debian.org bookworm main，镜像自带可用；
> 若报 `Unable to locate package xdotool`，先 `pkill -9 -x apt-get` 清掉上一条残留的
> `apt-get update` 锁，再重跑 update）。
> 定位并点击按钮：本部署 QQ 窗口固定 `320x460+800+300`，蓝色「登录」按钮质心绝对坐标
> 约 **(959, 630)**（窗口相对 (159, 330)）；视觉模型给的像素坐标不可信，
> 优先用截图颜色检测（B>150 & R<120 & B−R>70 & 80≤G≤220）或 `xwininfo` 确认：
> `docker exec qq-bridge-snowluma-protocol sh -c 'DISPLAY=:1 xdotool windowraise 0x400003; xdotool mousemove 959 630 click 1'`
> （`windowactivate` 因缺 EWMH 会报 `_NET_ACTIVE_WINDOW failed`，改用 `windowraise`；
> 第一次若压到「自动登录」勾选区没反应，把 y 加大到 ~630 即可）。

### 3.3 把 OneBot 连到 bridge

**前置：必须先在 6081 完成 QQ 扫码登录**（见 3.2 第 3 步）。扫码后按这个顺序收尾：

```powershell
python scripts/setup_snowluma_ws.py --check     # 先看当前配置
python scripts/setup_snowluma_ws.py             # 写入 networks.wsClients
docker exec qq-bridge-snowluma-protocol supervisorctl restart snowluma
```

⚠️ **配置落点是 `networks.wsClients`，不是顶层 `wsClients`**。网上流传的
compose/JSON 示例写顶层，但 SnowLuma v2.2.0 的 `onebot.json` 结构是
`{networks:{httpServers,wsServers,httpClients,wsClients}, …}`，运行时
`compileDesiredPlan()` 遍历的是 `config.networks.wsClients`；顶层字段不会被读取，
表现是「配置看着写好了、日志里一条 OneBot 都没有」。本副本脚本只写嵌套位置，
并会删掉历史误写的顶层字段。

脚本对 `/app/data/config/onebot*.json` **全部**写入同一份配置：
**扫码后 SnowLuma 会新生成账号级 `onebot_<uin>.json`（overlay，会覆盖基础文件），
所以扫码之后必须再跑一次 setup**，否则新文件里没有 WS 客户端。
建议只重载应用进程（`supervisorctl restart snowluma`），不要 `docker compose restart`
—— 后者会连 QQ 一起重启，多一次登录动作。

> **实测（2026-11-13 15:08）**：改密 + 同意 EULA/隐私已完成
> （`mustChangePassword=false` / `consent.json` / `agreements consent recorded`），
> 但 QQ 仍 `[Hook] awaiting login`，容器内 3000/3001 均 `ECONNREFUSED`、
> 全日志 `OneBot` 零行 —— **整个 OneBot 服务要等 QQ 账号登录才启动**。
> 这是当前唯一缺的一环，不是配置故障。扫码后按上面三条命令收尾即可。
> 若握手返回 401/403，核对 `.env::ONEBOT_V11_ACCESS_TOKEN` 与
> SnowLuma `accessToken` 是否一致（NoneBot 按 `Authorization: Bearer` 校验）。

成功日志：
```
snowluma: [OneBot.WS-Client] [qq_bridge_snowluma] connected ws://bridge:8082/onebot/v11/ws
bridge:   Bot <QQ号> connected
```

> **当前状态（2026-11-13 16:03）**：已按本流程完成登录与连通 ——
> QQ 扫码登录（账号 UIN `2193813501`）→ 账号级 `onebot_2193813501.json` 写入 wsClients
> → `supervisorctl restart snowluma` 后协议端
> `[OneBot.WS-Client] connected ws://bridge:8082/onebot/v11/ws`、
> bridge `Bot 2193813501 connected`。全量验收 **19/19 PASS**。
> 仅剩真实收发端到端验收（见 §5 待实测）。

### 3.4 验收

```powershell
python scripts/verify_snowluma_deploy.py --selftest          # 15 类反例注入自测
python scripts/verify_snowluma_deploy.py                    # 全量（静态 + 运行时）
```

### 3.5 回滚 / 停服

```powershell
powershell -File stop_snowluma.ps1       # docker compose down，卷保留
```
旧仓 `qq_bridge/` 与 `qq_bridge_official/` 的容器、配置、数据**完全不受影响**。

---

## 4. `.env` 派生清单（只列键名，值一律不进文档）

从 `qq_bridge/.env` 复制后，由 `tools/bootstrap_snowluma_copy.py` 改写 / 新增 11 项：

| 键 | 处理 | 原因 |
|---|---|---|
| `OFFICIAL_ENABLE` / `OFFICIAL_APPID` / `OFFICIAL_SECRET` | `false` / 清空 | 原仓 `.env` 是 `true`；照搬会注册官方适配器，与正在运行的官方副本**抢 AppID 单连接并互踢** |
| `PORT` / `HOST` | `8082` / `0.0.0.0` | 避开 8080（NapCat）、8081（官方） |
| `ONEBOT_V11_ACCESS_TOKEN` | 新强随机值 | 不与旧仓共用鉴权 |
| `BOT_UIN` | 清空 | 登录号由扫码决定，不预设旧号；扫码后可在配置页自行填入 |
| `GROUP_WHITELIST` | 清空 | 出站闸是 fail-closed：新号默认**不许向任何群发消息**，需你显式填群号 |
| `MANJU_API_BASE` / `MANJU_FILE_BASE` | 指向 `host.docker.internal` | 容器内 `localhost` 不是宿主 |
| `VNC_PASSWD` | 新强随机值（新增） | noVNC 远程桌面密码 |

`BOT_OWNER_QQ`、`PRIVATE_WHITELIST`、AI / TTS / aria2 等凭据保持原值，功能照常可用。
**凭据只存在于 `.env` 与运行态 `snowluma/data/config/onebot*.json`**：
后者因 OneBot 协议必须携带 `accessToken`，由 `setup_snowluma_ws.py` 写入并强制
`0600`（属主 `node`），且已被 `.gitignore` 排除；验收脚本对「源码/文档零明文」
「运行态文件被 gitignore」「运行态文件 0600」三道闸分别判定。
不要把这个文件复制进文档、日志、聊天或提交。

---

## 5. 关键实现与已知边界

| 项 | 说明 |
|---|---|
| 镜像版本 | `motricseven7/snowluma:v2.2.0`，linux/amd64，1.89GB，构建于 2026-10-24。拉取后 digest = `sha256:34b4ec03738a…`，与 Docker Hub 原始 digest 一致（加速源未篡改）。**不追 latest** |
| 必需参数 | `cap_add: SYS_PTRACE`、`seccomp=unconfined`、`shm_size: 1gb`、`SNOWLUMA_HOOK_AUTOLOAD=1`；缺前两个 QQ 在跑但收不到消息，缺 shm QQ 随机崩 |
| 卷 | `/app/data`（含 `config/onebot*.json`）、`/app/.config`、`/app/.local/share`（**QQ 登录态，删了要重扫**）——三个都 bind mount |
| 版本钉死 | 与 NapCat 仓的教训一致：浮动 tag 意味着某次 pull 就可能换掉 QQ 内核 |
| 设备身份 | 沿用 NapCat 仓 2026-10-28 的教训：`hostname: snowluma-home` + 固定 MAC + 固定内网 IP（`172.31.90.0/24`），第四项 `/app/data/config/machine-id` 由 bind mount 持久化。容器重建不再触发「登录新设备」；**已在扫码前设置**，之后不要改 |
| 待实测 | 登录与 WS 握手已完成（bridge `Bot 2193813501 connected`）。剩真实群/私聊收发、@ 判定、发图发语音端到端验收：由你本人发一条测试消息确认能收到并回卡；SnowLuma 部分能力（撤回 / 合并转发 / 临时签名 URL 图片）与 NapCat 不等价，实测后按需适配 |
| 平台差异 | SnowLuma 的部分能力（撤回、合并转发、临时签名 URL 图片）与 NapCat 不完全等价，实测后按需在副本内适配 |
| 历史文档 | 旧仓 `README.md` / `AGENTS.md` 原样保存在 `docs/legacy/`，仅作只读参考；**本副本的权威说明是本文** |

---

## 6. 交付文件

| 文件 | 作用 |
|---|---|
| `docker-compose.snowluma.yml` | 新部署唯一编排（bridge + snowluma + aria2，同项目共享网络） |
| `start_snowluma.ps1` / `stop_snowluma.ps1` | 起停包装（不含任何凭据） |
| `scripts/setup_snowluma_ws.py` | 幂等注入 `wsClients`，容器内改文件、token 只走 stdin |
| `scripts/verify_snowluma_deploy.py` | 隔离 / 契约 / 凭据 / 运行时验收 + 15 类反例自测 |
| `tools/bootstrap_snowluma_copy.py` | 副本生成脚本（**只读源仓** `qq_bridge_official`），`--force` 才会覆盖 |
| `tools/copy_manifest.json` | 615 文件 sha256 快照（源指向 `qq_bridge_official`），证明副本完整且源仓未被改写 |

---

## 7. 投产前检查清单（2026-11-13 16:0x）

> 结论：**技术链路已通、可先灰度试运行，但还不是「无虞投产」**——卡在两件事：
> ① 还没发过真实消息做端到端验收；② 换平台**没消除**风控/封号风险。

| 状态 | 项 |
|---|---|
| ✅ 已验证 | 部署四层隔离（进程/容器/数据/编排）、WS 握手成功、bridge `Bot 2193813501 connected`、19/19 验收全 PASS、凭据零明文 + 0600 + gitignore、旧仓零改动、镜像 digest 与源一致、**aria2 下载链路修复并端到端验证（RPC_OK v1.37.0）** |
| 🟡 待你验证 | **真实收发端到端**：私聊 @ 机器人发「赏金」「紫卡」等，确认能收到并回卡；**群白名单**：当前 `GROUP_WHITELIST` 为空（出站闸 fail-closed），要往群发消息需先在 `.env` 填群号；**长期稳定性**：刚登录，未观察过挂机 24h+ / 掉线重连行为 |
| 🔴 固有风险 | SnowLuma 是第三方 `ptrace` 注入、非商业许可，**换平台不消除封号/风控**；同一 QQ 号不能 NapCat 与 SnowLuma 同时在线；`restart:"no"` 意味着被踢后要人工确认再起 |

> 🔧 **2026-11-13 16:5x 追加修复**：aria2 下载链路（`/dl` 命令族 / M7 下载媒体中心）此前其实**一直不通**，根因两层——① `DL_ARIA2_RPC` 原用服务名 `aria2`，bridge 容器重建后 Docker 内嵌 DNS 的服务名别名注册失同步（`gethostbyname('aria2')` 报 `Name or service not known`）；② bridge 容器环境缺 `DL_ARIA2_SECRET`，而 aria2 sidecar 启用了 `--rpc-secret`，鉴权必败。已改为容器名 `qq-bridge-snowluma-aria2`（实测稳定解析 172.31.90.3）+ 显式注入 secret，端到端 `aria2.getVersion` 返回 `v1.37.0`。容器名与 DNS 失同步的坑在 `docker-compose.snowluma.yml` 的 `DL_ARIA2_RPC` 注释里已写明。

**灰度试运行建议**：小号先用私聊跑 1–2 天真实指令，确认功能与稳定后再考虑接群；
群功能上线前先填 `GROUP_WHITELIST` 并在小群试发。投产决策由你本人做。
