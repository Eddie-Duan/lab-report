# lab-report

面向 AI agent的 skill，实现大学物理实验的**手写记录纸照片 → 电子原始数据 → 计算 → 报告 PDF** 链路自动化。

做 UCAS 基础物理实验时需要，总结成 skill 自用。

## 工作流程

| 步骤 | 做什么 |
|---|---|
| **1 转录** | 照片切块放大后逐个读数，认不清直接问用户 |
| **2 核对** | 确认前不进入计算 |
| **3 处理** | 生成 `处理.py`：零点修正、逐差法、不确定度传递、作图法／最小二乘法，并出图 |
| **4 报告** | 写成 Typst，编译成 PDF |
| **5 审阅** | 开 subagent 攻击**AI味文风** |


## 目录

```
lab-data-workflow/
  SKILL.md               完整流程、读数纪律、踩过的坑、排查表
  scripts/prep_photo.py  照片预处理：总览／转正／切半／裁切放大／去背景补光
  scripts/csv_tables.py  带分段标记的原始数据 CSV 读写
  scripts/to_utf8.py     GBK → UTF-8 BOM（解决 Excel 中文 CSV 乱码）
  scripts/selftest.py    上面三个脚本的回归自测，改完跑一遍
  templates/report.typ   Typst 报告模板（三线表、公式编号、中文字体）
```

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

之后在项目里说"录入实验数据""处理实验数据""写实验报告"就会自动加载。（或让AI agent自行安装）

## 依赖

- **Python 3 + Pillow** —— 三个脚本本身只要这些。`autolevel` 去背景用 numpy，没装会自动退化成
  全局对比度拉伸，不影响使用。
- **numpy、matplotlib** —— §3 你自己写的 `处理.py` 算数据、出图时才要。
- **[Typst](https://typst.app)** —— 只有 §4 出 PDF 才要。

## 自测

```bash
python lab-data-workflow/scripts/selftest.py
```

覆盖编码嗅探、同名分段、行列数不匹配、错字与空格子的区分、裁切坐标换算、去背景的极性等易错点，
全绿再提交。

## 说明

自用为主，欢迎其他同学取用和提建议。后面还会继续优化。
