# lab-report

面向 AI agent的 skill，实现大学物理实验的**手写记录纸照片 → 电子原始数据 → 计算 → 报告 PDF** 链路自动化。

做 UCAS 基础物理实验时需要，总结成 skill 自用。

## 工作流程

| 步骤 | 做什么 |
|---|---|
| **0 报告头** | 开本地界面填实验名/姓名/教师/日期/附件，生成报告骨架 + `报告参数.json` |
| **1 转录** | 照片切块放大后逐个读数，认不清直接问用户 |
| **2 核对** | 确认前不进入计算 |
| **3 处理** | 生成 `处理.py`：零点修正、逐差法、不确定度传递、作图法／最小二乘法，并出图 |
| **4 报告** | 把结果填进骨架，编译成 PDF，再改名成 `班级号-分组号-姓名-实验名-实验日期-教师姓名.pdf` |
| **5 审阅** | 开 subagent 攻击**AI味文风** |

## 界面

```bash
python lab-data-workflow/ui/server.py --root <实验目录>     # 默认 http://127.0.0.1:8722
```

Windows 上更省事：直接双击 **`lab-data-workflow/打开界面.cmd`** —— 它自己找 python、自动用 `--open`
把浏览器打开，实验目录默认用 `sample\my_sample`（找不到就用桌面）；想换目录，把这个 `.cmd` 拖到
那个目录上再松手即可。那个文件是 **GBK + CRLF** 编码（cmd 在中文 Windows 上按 ANSI 读批处理），
用编辑器改它时别存成 UTF-8。

填实验名称（从 `experiments.json` 的 20 个往年实验名里搜）、输出格式（Typst / LaTeX / Word / Markdown）、
姓名、教师、日期（这三项可留空）、记录纸照片、补充文件、补充说明，
以及 **预习报告、数据记录**（这两项必填），然后生成到
`<实验目录>/<实验>/实验数据/`：报告骨架（报告头已填、分节留空）+ `报告参数.json` + 归档的附件。
命令行等价物是 `scripts/make_report.py`（`--list` 看实验名清单，`--help` 看全部参数）。

预习报告、数据记录会归档到 `实验数据/预习报告/`、`实验数据/数据记录/`，并被排成**附录 A / 附录 B
跟在报告最后**：LaTeX 直接用 `\includepdf`/`\includegraphics` 嵌进 PDF，Typst 能嵌图片（PDF 不行，
骨架里会留注释说明），Word/Markdown 列出文件名让你自己插。命令行对应 `--prelab` / `--record`（不强制）。

界面是**给人用的可选件**（只用标准库、不联网、由你手动启动）：纯 agent 场景不必开它，直接
`make_report.py` 走命令行，落盘的东西完全一样（包括 `报告参数.json`）。删掉 `ui/` 不影响 skill 本体。

正文写好后要改报告头（日期/分组/教师名字），勾**"只更新报告头"**：只重写报告头，正文一个字都不动。
命令行等价物是 `make_report.py --head-only`（与 `--force` 互斥；没给的字段沿用上次的值）。

生成成功后的结果里有**「复制以下文本到 DSH 中」**：一键复制一段已经把 `报告参数.json`、实验数据目录、
照片目录的绝对路径写好的指令，直接粘进 agent 对话就能开工（换别的宿主 agent 也一样用）。

交出去的 PDF **不叫 `实验报告.pdf`**：课程要求 `班级号-分组号-姓名-实验名-实验日期-教师姓名.pdf`
（`1-6-张三-光电探测-2026.09.21-李四.pdf` 那套写法）。名字由报告头字段算出来，写在 `报告参数.json`
的 `PDF 文件名` 里；编译完一条命令改名：

```bash
python lab-data-workflow/scripts/make_report.py --exp 测量金属的杨氏模量 --root <实验目录> --pdf-rename
```

细则与字段规整规则见 `SKILL.md` §4.2.1。

## 目录

```
lab-data-workflow/
  SKILL.md                 完整流程、读数纪律、材料优先级、踩过的坑、排查表
  experiments.json         往年实验名清单（界面搜索用）
  ui/server.py             报告头界面（标准库 HTTP 服务，不联网；人用，可选）
  ui/index.html            界面本身（无外部依赖，离线可用）
  打开界面.cmd            Windows 双击就能启动界面（GBK+CRLF，别用 UTF-8 编辑器保存）
  scripts/prep_photo.py    照片预处理：总览／转正／切半／裁切放大／去背景补光
  scripts/csv_tables.py    带分段标记的原始数据 CSV 读写
  scripts/to_utf8.py       GBK → UTF-8 BOM（解决 Excel 中文 CSV 乱码）
  scripts/make_report.py   按参数生成报告骨架（typst/latex/docx/md）；--head-only 只改报告头不动正文；--pdf-rename 把编译好的 PDF 改成课程要求的名字
  scripts/selftest.py      上面这些的回归自测（31 个用例），改完跑一遍
  templates/report.typ     Typst 报告模板（三线表、公式编号、中文字体、报告头变量）
  templates/latex/main.tex LaTeX 报告模板（学长模板的导言区+报告头，正文清空）
  templates/latex/原版参考.tex  学长模板的完整原版（课程推荐模板）——要加宏包/改版式照它抄
  templates/docx/          Word 容器（今年的官方《实验报告报告头》，生成时只换正文）
sample/                    本地参考料（默认不入 git）：参考/预习要求·仪器说明书·网格坐标纸·
                           数据表曲线图要素（课程《数据表、曲线图要素示意》+ 抽出的两张示意图）、
                           模板/、范例报告/ —— skill 本身不依赖它，删了也能用
```

`sample/` 里是别的同学的实名报告，**默认不入 git**（见 `.gitignore`）；skill 本身不依赖它 ——
模板、实验名清单、Word 容器都在 `lab-data-workflow/` 里自带。

## 安装

装到项目里（跟随项目走）：

```bash
git clone https://github.com/Helios-YQH/lab-report.git
mkdir -p <你的项目>/.claude/skills
cp -r lab-report/lab-data-workflow <你的项目>/.claude/skills/
```

装成全局（所有项目都能用），按你用的 agent 选一个目录：

| 目录 | 谁认 |
|---|---|
| `~/.claude/skills/` | Claude Code |
| `~/.agents/skills/` | 认 `.agents` 约定的 agent（DeepSeek Harness 等） |
| `$DSH_HOME/skills/` | DeepSeek Harness |
| `<项目>/.dsh/skills/`、`<项目>/.agents/skills/` | 只在该项目里生效 |

目录名保持 `lab-data-workflow/` 且里面有 `SKILL.md` 就行（平铺成 `lab-data-workflow.md` 也可以）。
如果只给 agent 用，`ui/` 可有可无 —— 它就是 `make_report.py` 的一层网页壳，agent 走命令行。

之后在项目里说"录入实验数据""处理实验数据""写实验报告"就会自动加载。（或让AI agent自行安装）

## 依赖

- **Python 3 + Pillow** —— 脚本本身就只要这些。`autolevel` 去背景用 numpy，没装会自动退化成
  全局对比度拉伸，不影响使用。界面只用标准库。
- **numpy、matplotlib** —— §3 你自己写的 `处理.py` 算数据、出图时才要。
- **Typst** —— 出 Typst 版 PDF 要装（没装就选 LaTeX 或 Word）。
- **TeX 发行版（MiKTeX / TeX Live）** —— 出 LaTeX 版 PDF 要装；Word 版生成 `.docx` 不用额外工具。

## 自测

```bash
python lab-data-workflow/scripts/selftest.py
```

覆盖编码嗅探、同名分段、行列数不匹配、错字与空格子的区分、裁切坐标换算、去背景的极性、
四种输出格式的报告头填充、只看报告头不动正文、四种格式的附录 A/B 排版、附件归档去重、
界面后端全流程等易错点（31 个用例），全绿再提交。

## 说明

自用为主，欢迎其他同学取用和提建议。后面还会继续优化。
