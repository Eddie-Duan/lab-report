// 物理实验报告 Typst 模板
//   编译: typst compile 报告.typ        (跑一遍即可, 交叉引用自动解析)
//   字体: 用系统字体, Windows 下 SimSun/SimHei 一定有; 换机器改第 3 行的字体名
//   图:   同目录放 fig1.png 之类, 用 #figure(image("fig1.png", width: 60%), caption: [...])
//
// 已验过的坑:
//   * 表格默认齐左, 加第 9 行的 show table 规则才会居中
//   * bar(x) 在 Typst 里是竖线符号, 不是上划线! 均值要用 overline(x)
//   * 单位用 #u("mm"), 它自带一点间距; 直接写 $... "mm"$ 会贴着数字

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

// 单位: 写 #u("mm") 得到带前置间距的正体 mm
#let u(s) = h(0.17em) + math.upright(s)

// 三线表: 第一行自动加粗当表头, 其余是数据行
//   单元格必须写成内容块 [...]，不能写 "字符串" —— 字符串不会被当标记解析,
//   里面的 $公式$ 会原样印出来
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
  #text(size: 17pt, weight: "bold", font: ("Times New Roman", "SimHei"))[实验名称]
  #v(0.9em)
  #table(
    columns: (auto, auto, auto, auto),
    align: (right, left, right, left),
    stroke: none,
    inset: (x: 6pt, y: 2pt),
    [姓名], [×××], [学号], [×××××××××××],
    [分组组号], [××], [实验日期], [×××× 年 × 月 × 日],
    [地点], [×××], [指导教师], [×××],
  )
]

= 实验目的

+ 目的之一。
+ 目的之二。

= 实验原理

$ Y = (4 M g L) / (pi d^2 Delta L) $

式中 $M$ 为砝码质量，$d$ 为直径，$Delta L$ 为伸长量。用逐差法取 $Delta L$。

= 实验数据

#bt((
  ([序号 $i$], [$M\/"g"$], [$l_i\/"mm"$]),
  ([1], [250], [$-0.10$]),
  ([2], [500], [$+0.22$]),
))

某量 $x = 12.3#u("mm")$，均值 $overline(x) = 12.30#u("mm")$。

= 数据处理

$ Y = (4 M g L) / (pi d^2 overline(Delta l)) = 2.63 times 10^11#u("N/m")^2 $

#figure(
  image("fig1.png", width: 55%),
  caption: [某量关系图],
)

= 实验结果

#block(breakable: false, bt((
  ([方法], [样品], [杨氏模量 $Y \/ 10^11 "N/m"^2$], [相对不确定度]),
  ([拉伸法], [钼丝], [$2.63 plus.minus 0.18$], [6.7%]),
  ([动态法], [铜棒], [$1.038 plus.minus 0.008$], [0.8%]),
)))
