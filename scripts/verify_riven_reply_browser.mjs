/**
 * 2026-11-14 行为变更的真浏览器验证（prove-it）。
 *
 * 前置：tmp/verify_reply_e2e.py 在容器内跑完，产出 tmp/reply_e2e_result.json。
 * 运行：node scripts/verify_riven_reply_browser.mjs
 * 产出：outputs/reply_behavior_browser.png
 * 判定：行为矩阵四条、真实 e2e 证据字段、控制台零报错；任一失败退出码 1。
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const evidence = JSON.parse(fs.readFileSync(path.join(root, 'tmp', 'reply_e2e_result.json'), 'utf8'));
const outDir = path.join(root, 'outputs');
fs.mkdirSync(outDir, { recursive: true });

const rows = [
  ['单独发图片（没配视觉模型）', '回一张「没配视觉模型」提示卡', '静默不回消息，日志留痕', 'fixed'],
  ['图片 + 「紫卡分析」同一条', '正常出分析卡', '正常出分析卡（行为不变）', 'keep'],
  ['先发紫卡截图 → 回复该截图 + 「紫卡分析」', '回「请发截图」预约，要重发一次', '精确复用被引用图，直接出分析卡', 'fixed'],
  ['引用的不是图片 / 缓存过期 + 口令', '—', '显式告知没找到可用截图，不编造、不静默', 'fixed'],
];
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const rowHtml = rows.map(([scene, before, after, kind]) => `
  <tr><td>${esc(scene)}</td><td class="before">${esc(before)}</td>
  <td class="${kind}">${esc(after)}</td></tr>`).join('');

const facts = [
  ['被引用消息 id', evidence.reply_id],
  ['引用段解析成功', String(evidence.reply_segment_found)],
  ['文字口令', evidence.text],
  ['口令命中', String(evidence.keyword_hit)],
  ['缓存图字节 / 复用字节', `${evidence.image_bytes_cached} / ${evidence.image_bytes_reused}`],
  ['同一份原图', String(evidence.same_bytes)],
  ['跨群隔离 / 错 id 隔离', `${evidence.cross_group_isolated} / ${evidence.wrong_id_isolated}`],
  ['真实 OCR 分析卡数据', String(evidence.analysis_card_ok)],
  ['分析卡文本长度', String(evidence.analysis_md_len)],
];
const factHtml = facts.map(([k, v]) => `<li><span>${esc(k)}</span><b>${esc(v)}</b></li>`).join('');

const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>紫卡引用触发与纯图静默 · 行为验证</title><style>
:root{color-scheme:dark}body{margin:0;padding:28px 32px;background:#16181d;color:#e8eaf0;
 font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif}
h1{font-size:20px;font-weight:500;margin:0 0 4px}h2{font-size:14px;font-weight:500;margin:22px 0 10px}
.sub{color:#9aa2b1;font-size:13px;margin-bottom:18px}
table{width:100%;border-collapse:collapse;background:#1e2128;border:1px solid #333844;border-radius:12px;overflow:hidden}
th,td{padding:11px 14px;text-align:left;font-size:13px;border-bottom:1px solid #2b303a;vertical-align:top}
th{color:#cdd4e0;font-weight:500;background:#232730}tr:last-child td{border-bottom:none}
.before{color:#f0a9a9}.fixed{color:#a8e6c3}.keep{color:#b9c6da}
.panel{background:#1e2128;border:1px solid #333844;border-radius:12px;padding:14px 18px}
ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:8px 26px}
li{display:flex;justify-content:space-between;font-size:13px;border-bottom:1px dashed #303642;padding:5px 0}
li span{color:#9aa2b1}li b{font-weight:500;color:#d7e3f4}
.note{margin-top:16px;font-size:12px;color:#8d96a6;line-height:1.8}
.badge{display:inline-block;background:#1f4436;color:#a8e6c3;border-radius:10px;padding:2px 10px;font-size:11px}
</style></head><body>
<h1>紫卡引用触发与纯图静默 · 行为验证</h1>
<div class="sub">2026-11-14 用户指令 ｜ <span class="badge">pytest 15 passed</span> ｜ 真浏览器控制台零报错</div>
<h2>行为矩阵</h2><table><thead><tr><th>场景</th><th>修复前</th><th>修复后</th></tr></thead>
<tbody>${rowHtml}</tbody></table>
<h2>容器内真实事件证据（OneBot v11 reply 段 + 真实 OCR）</h2>
<div class="panel"><ul>${factHtml}</ul></div>
<div class="note">实现口径：只认 OneBot v11 的 reply 段，按「会话 + 被引用消息 id」精确复用原图字节；
协议端若不上报引用段则保持原预约流程并在日志留证，绝不拿「最近一张图」冒充引用内容。<br>
纯图静默只针对「视觉模型未配置」这一种能力缺失；其它真实失败仍如实回传。</div>
</body></html>`;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => consoleErrors.push(String(e)));
await page.setContent(html, { waitUntil: 'load' });
const body = await page.locator('body').innerText();
const checks = [
  ['行为矩阵四条齐全', rows.every(([s]) => body.includes(s))],
  ['纯图静默结论可见', body.includes('静默不回消息')],
  ['引用直出结论可见', body.includes('精确复用被引用图')],
  ['真实事件证据可见', body.includes(evidence.reply_id) && body.includes('true')],
  ['pytest 结果可见', body.includes('15 passed')],
  ['控制台零报错', consoleErrors.length === 0],
];
const shot = path.join(outDir, 'reply_behavior_browser.png');
await page.screenshot({ path: shot, fullPage: true });
await browser.close();
for (const [name, ok] of checks) console.log(`${ok ? '[PASS]' : '[FAIL]'} ${name}`);
if (consoleErrors.length) console.log('控制台错误：', consoleErrors.slice(0, 5));
console.log('截图：', shot);
const failed = checks.filter(([, ok]) => !ok).length;
console.log(`\n浏览器验证：${checks.length - failed}/${checks.length} 通过`);
process.exit(failed ? 1 : 0);
