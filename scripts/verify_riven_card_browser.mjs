/**
 * 紫卡修复的真浏览器验证（prove-it：用户看得见的卡面/文案必须在真浏览器里过一遍）。
 *
 * 前置（容器内生成，见 scripts/prepare_warframe_data.py 的复验流程）：
 *   tmp/riven_card_after_fix.png   修复后用真实紫卡原图渲染出的分析卡
 *   tmp/riven_error_text.txt       词库缺失时 riven_img_analyze_full 的真实返回文案
 *
 * 运行：node scripts/verify_riven_card_browser.mjs
 * 产出：outputs/riven_fix_browser.png（整页截图）
 * 判定：图片加载 / 新文案含真实原因与修复命令 / 不再甩锅截图 / 控制台零报错，
 *       任一项不通过即退出码 1。
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pngPath = path.join(root, 'tmp', 'riven_card_after_fix.png');
const errPath = path.join(root, 'tmp', 'riven_error_text.txt');
const outDir = path.join(root, 'outputs');
fs.mkdirSync(outDir, { recursive: true });

const cardB64 = fs.readFileSync(pngPath).toString('base64');
const newMsg = fs.readFileSync(errPath, 'utf8').trim();
const oldMsg = [
  '识别到了内容，但没凑齐「武器名 + 词条」：',
  '没读完整词条（图可能太小、被裁切或词条行被遮挡）。',
  '标题行读到：卡帕压力枪 Croni- / satipia',
].join('\n');

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>紫卡修复 · 浏览器验证</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; padding:28px 32px; background:#16181d; color:#e8eaf0;
         font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; }
  h1 { font-size:20px; font-weight:500; margin:0 0 4px; }
  .sub { color:#9aa2b1; font-size:13px; margin-bottom:22px; }
  .grid { display:grid; grid-template-columns:minmax(0,560px) minmax(0,1fr); gap:28px; align-items:start; }
  .panel { background:#1e2128; border:1px solid #333844; border-radius:12px; padding:16px; }
  .panel h2 { font-size:14px; font-weight:500; margin:0 0 12px; color:#cdd4e0; }
  img { width:100%; height:auto; border-radius:8px; display:block; background:#0f1115; }
  pre { white-space:pre-wrap; word-break:break-word; font-size:13px; line-height:1.7;
        margin:0; font-family:Consolas,"Microsoft YaHei",monospace; }
  .old { border-color:#7a3b3b; } .old pre { color:#f0a9a9; }
  .new { border-color:#2f6b52; margin-top:16px; } .new pre { color:#a8e6c3; }
  .tag { display:inline-block; font-size:11px; padding:2px 8px; border-radius:10px; margin-right:8px; }
  .tag-old { background:#4a2424; color:#f0a9a9; } .tag-new { background:#1f4436; color:#a8e6c3; }
  ul { margin:18px 0 0; padding-left:20px; font-size:13px; color:#c2c9d6; line-height:1.9; }
</style></head><body>
<h1>紫卡分析修复 · 浏览器验证</h1>
<div class="sub">真实紫卡原图 → 容器内 RapidOCR + 静态词库 → 分析卡 / 错误文案</div>
<div class="grid">
  <div class="panel">
    <h2>修复后：真实原图渲染出的紫卡分析卡</h2>
    <img id="card" alt="紫卡分析卡" src="data:image/png;base64,${cardB64}">
  </div>
  <div>
    <div class="panel old">
      <h2><span class="tag tag-old">事故时</span>误导诊断（甩锅截图）</h2>
      <pre>${esc(oldMsg)}</pre>
    </div>
    <div class="panel new">
      <h2><span class="tag tag-new">修复后</span>词库缺失时如实报错</h2>
      <pre id="new-msg">${esc(newMsg)}</pre>
    </div>
    <ul>
      <li>根因：data/warframe_items/ 三张派生表从未落地，OCR 其实四条词条全读对</li>
      <li>修复：prepare_warframe_data.py 补齐静态词库 + 缺失时显式上抛 + 日志落盘</li>
      <li>验证：控制台零报错、卡面图片真实加载、文案含真实原因与修复命令</li>
    </ul>
  </div>
</div>
</body></html>`;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => consoleErrors.push(String(e)));

await page.setContent(html, { waitUntil: 'load' });
await page.locator('#card').waitFor({ state: 'visible' });
const imgOk = await page.locator('#card').evaluate((el) => el.complete && el.naturalWidth > 0);
const shown = await page.locator('#new-msg').innerText();
const checks = [
  ['分析卡 PNG 在真浏览器加载', imgOk],
  ['新文案含真实原因「紫卡词库未就绪」', shown.includes('紫卡词库未就绪')],
  ['新文案含修复命令 prepare_warframe_data.py', shown.includes('prepare_warframe_data.py')],
  ['新文案不再出现「没读完整词条」甩锅句', !shown.includes('没读完整词条')],
  ['浏览器控制台零报错', consoleErrors.length === 0],
];
const shot = path.join(outDir, 'riven_fix_browser.png');
await page.screenshot({ path: shot, fullPage: true });
await browser.close();

for (const [name, ok] of checks) console.log(`${ok ? '[PASS]' : '[FAIL]'} ${name}`);
if (consoleErrors.length) console.log('控制台错误：', consoleErrors.slice(0, 5));
console.log('截图：', shot);
const failed = checks.filter(([, ok]) => !ok).length;
console.log(`\n浏览器验证：${checks.length - failed}/${checks.length} 通过`);
process.exit(failed ? 1 : 0);
