// 界面前端自检：内联 JS 语法、JS 引用的 id 是否都存在、表单字段与后端参数是否对得上。
//   用法: node <SKILL>/ui/check_frontend.js <SKILL>/ui/index.html
// 没有浏览器也能跑（比开 Playwright 轻得多），改完 index.html 就跑一遍。
const fs = require('fs');
const src = fs.readFileSync(process.argv[2] || __dirname + '/index.html', 'utf8');
let bad = 0;
const say = (ok, msg) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); if (!ok) bad++; };

// --- 1. 取出内联脚本, 检查语法 ---
const m = src.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.log('FAIL  找不到 <script> 块'); process.exit(1); }
const js = m[1];
try { new Function(js); say(true, '内联 JS 语法正确'); }
catch (e) { say(false, '内联 JS 语法错误: ' + e.message); }

// --- 2. JS 用到的 id 必须在 HTML 里有 ---
const htmlIds = new Set([...src.matchAll(/\sid="([^"]+)"/g)].map(x => x[1]));
for (const id of new Set([...js.matchAll(/\$\('([^']+)'\)/g)].map(x => x[1]))) {
  say(htmlIds.has(id), `JS 引用的 #${id} 存在于 HTML`);
}
for (const id of ['reveal-btn', 'photos-list', 'attachments-list', 'prelabs-list', 'records-list']) {
  say(js.includes(id), `JS 里处理了 ${id}`);
}

// --- 3. 表单控件与后端字段一一对应 ---
for (const f of ['exp', 'dir', 'student', 'teacher', 'date', 'sid', 'group', 'room',
                 'mates', 'notes', 'root', 'force', 'head-only', 'prelabs', 'records']) {
  say(htmlIds.has(f), `<input> 字段 ${f} 存在`);
}
for (const f of ['实验名称', '实验目录名', '输出格式', '姓名', '指导教师', '实验日期', '学号',
                 '分班分组及座号', '实验地点', '同组人员', '补充说明', '实验目录',
                 '覆盖已有报告', '只更新报告头', '记录纸照片', '补充文件',
                 '预习报告', '数据记录']) {
  say(js.includes(`'${f}'`), `提交参数里有 ${f}`);
}

// --- 4. 易错的几处约定 ---
say(/type="radio" name="fmt"/.test(js), '输出格式是单选且同属一个 name 组');
say(/aria-live="polite"/.test(src), '结果区有 aria-live');
say(/<label for="/.test(src), '用了 label for 绑定');
say(!/onclick="/.test(js), '没有内联 onclick（Windows 路径的反斜杠会过不了转义）');
say(/required/.test(src), '实验名称必填');
say(/location\.protocol/.test(js), '直接双击 index.html 会提示要用 server.py 启动');
say(/fail|catch/.test(js) && /读不到本地服务/.test(js), '取不到 /api/config 时会在格式框里写明原因');
say(/<noscript>/.test(src), '禁了 JavaScript 也有提示（不会只剩空格）');
say(/navigator\.clipboard/.test(js), '复制按钮用 clipboard API（带 execCommand 兜底）');
say(/复制以下文本到 DSH/.test(js), '生成结果里有“复制以下文本到 DSH 中”');
say(/function esc\(/.test(js) && /esc\(j\['给agent的话'\]\)/.test(js),
    '拼进 HTML 的动态文本走了转义');
say(/missing\.push\('预习报告'\)/.test(js) && /missing\.push\('数据记录'\)/.test(js),
    '提交前检查预习报告/数据记录必填');

// --- 5. 两个生成开关语义相反, 前端必须互斥（后端也拦）---
const mutex = (a, b) => js.includes(`if ($('${a}').checked) $('${b}').checked = false`);
say(mutex('force', 'head-only') && mutex('head-only', 'force'), '覆盖 与 只更新报告头 互斥');

console.log(bad ? `\n${bad} 项失败` : '\n全部通过');
process.exit(bad ? 1 : 0);
