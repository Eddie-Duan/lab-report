// 物理实验报告 Typst 模板
//   编译: typst compile 报告.typ        (跑一遍即可, 交叉引用自动解析)
//   字体: 用系统字体, Windows 下 SimSun/SimHei 一定有;
//         换机器改下面 "#set text(font: ...)" 那行(别照行号找, 内容一改行号就漂了)
//   图:   同目录放 fig1.png 之类, 用 #figure(image("fig1.png", width: 60%), caption: [...])
//         模板里那段 figure 默认是注释掉的 —— 图还没生成时 image() 会直接报文件找不到
//
// 报告头那段 "#let" 会被 UI / make_report.py 填, 也可以手改。
// 分节顺序按课程《实验报告格式及要求》默认排的; 当年要求不一样就按当年的来 —— 见 SKILL.md「材料优先级」。
//
// 已验过的坑:
//   * 表格默认齐左, 加下面 "#show table:" 那条规则才会居中
//   * bar(x) 在 Typst 里是竖线符号, 不是上划线! 均值要用 overline(x)
//   * 单位用 #u("mm"), 它自带一点间距; 直接写 $... "mm"$ 会贴着数字
//   * 单元格必须写内容块 [...]，不能写 "字符串" —— 字符串不会被当标记解析,
//     里面的 $公式$ 会原样印出来

#set page(paper: "a4", margin: (x: 2.3cm, y: 2.0cm), numbering: "1", number-align: center)
#set text(font: ("Times New Roman", "SimSun"), size: 11pt, lang: "zh")
#set par(justify: true, leading: 0.62em, first-line-indent: 0em)
#set heading(numbering: "1.")
#show heading: set text(font: ("Times New Roman", "SimHei"), weight: "bold")
#show heading.where(level: 1): it => block(above: 1.3em, below: 0.8em, it)
#show heading.where(level: 2): it => block(above: 1.0em, below: 0.6em, it)
#set math.equation(numbering: "(1)", supplement: none)
#set figure(gap: 0.9em)
#show table: it => align(center, it)

// ============ 报告头（UI / make_report.py 改这一段）============
#let exp_name = ""          // 实验名称
#let teacher = ""           // 指导教师
#let student = ""           // 姓名
#let student_id = ""        // 学号
#let class_group = ""       // 分班分组及座号, 形如 1-04-5
#let date = ""              // 实验日期, 形如 2026 年 9 月 26 日
#let room = ""              // 实验地点
#let mates = ""             // 同组人员

// 单位: 写 #u("mm") 得到带前置间距的正体 mm
#let u(s) = h(0.17em) + math.upright(s)

// 空着的字段画成下划线空格, 有值就正常显示
#let fill(v, w: 5em) = if v == "" { underline[#box(width: w)] } else { v }

// 三线表: 第一行自动加粗当表头, 其余是数据行
//   #bt((
//     ([序号 $i$], [$M\/"g"$]),
//     ([1], [250]),
//     ([2], [500]),
//   ))
#let bt(cells, al: center) = table(
  columns: cells.at(0).len(),
  align: al + horizon,
  stroke: none,
  inset: 5pt,
  table.hline(stroke: 0.9pt),
  table.header(..cells.at(0).map(c => strong(c))),
  table.hline(stroke: 0.5pt),
  ..cells.slice(1).flatten(),
  table.hline(stroke: 0.9pt),
)

// ============ 正文 ============

#align(center)[
  #text(size: 16pt, weight: "bold", font: ("Times New Roman", "SimHei"))[《基础物理实验》实验报告]
  #v(0.6em)
  #table(
    columns: (auto, 1fr, auto, 1fr),
    align: (right, left, right, left),
    stroke: none,
    inset: (x: 6pt, y: 2.5pt),
    [实验名称], [#fill(exp_name, w: 12em)], [指导教师], [#fill(teacher, w: 6em)],
    [姓名], [#fill(student, w: 6em)], [学号], [#fill(student_id, w: 9em)],
    [分班分组及座号], [#fill(class_group, w: 9em)], [实验日期], [#fill(date, w: 9em)],
    [实验地点], [#fill(room, w: 6em)], [同组人员], [#fill(mates, w: 6em)],
  )
]

= 实验目的

+ 目的之一。
+ 目的之二。

= 仪器用具

仪器名称（型号、规格、分度值）。

= 实验原理

$ Y = (4 M g L) / (pi d^2 Delta L) $

式中 $M$ 为砝码质量，$d$ 为直径，$Delta L$ 为伸长量。用逐差法取 $Delta L$。

= 实验内容

调节与测量步骤、观察到的现象。

= 实验数据

#bt((
  ([序号 $i$], [$M\/"g"$], [$l_i\/"mm"$]),
  ([1], [250], [$-0.10$]),
  ([2], [500], [$+0.22$]),
))

某量 $x = 12.3#u("mm")$，均值 $overline(x) = 12.30#u("mm")$。

= 数据处理与结果

$ Y = (4 M g L) / (pi d^2 overline(Delta l)) = 2.63 times 10^11#u("N/m")^2 $

// 图: 出图后把这段取消注释, 文件名改成实际的 fig1.png
// #figure(
//   image("fig1.png", width: 55%),
//   caption: [某量关系图],
// )

#block(breakable: false, bt((
  ([方法], [样品], [杨氏模量 $Y \/ 10^11 "N/m"^2$], [相对不确定度]),
  ([拉伸法], [钼丝], [$2.63 plus.minus 0.18$], [6.7%]),
)))

= 问题讨论

// 要求里若还有"思考题/总结", 按当年要求加节 —— 见 SKILL.md「材料优先级」
