# -*- coding: utf-8 -*-
"""按"报告参数"生成报告骨架：typst / latex(tex) / docx / md 四种格式。

生成的只是**骨架 + 报告头**（报告头字段填好，正文分节留空），正文由 agent 用 SKILL.md 的流程写。
每次都写一份 `报告参数.json`（给 agent 读字段值），附件和记录纸照片也一起归到实验目录里。

命令行:
    python make_report.py --list                         # 列出实验名清单
    python make_report.py --exp 杨氏模量 --fmt typst --name 张三 --teacher 李四 \\
        --date 2026-09-26 --group 1-04-5 --file 补充.pdf --photo IMG_1.jpg
    python make_report.py --info 报告参数.json            # UI 走这个: 一次把参数都传进来
    python make_report.py --exp 杨氏模量 --head-only      # 只改报告头, 已写好的正文一个字都不动
    python make_report.py --exp 杨氏模量 --prelab 预习报告.pdf --record 数据记录.jpg   # 附在报告最后

目录约定（与 SKILL.md 一致）:
    <root>/<实验目录>/实验数据/实验报告.<ext>
    <root>/<实验目录>/实验数据/报告参数.json
    <root>/<实验目录>/实验数据/补充文件/…
    <root>/<实验目录>/实验数据/照片/…
    <root>/<实验目录>/实验数据/预习报告/…   ← 附录 A
    <root>/<实验目录>/实验数据/数据记录/…   ← 附录 B

注意: 报告头版式是以课程的 Word 报告头为准整理出来的默认值。当年模板/要求若不同,
**以用户上传或说明的为准**（SKILL.md 开头「材料优先级」）。
"""
import argparse
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL / 'templates'
EXPERIMENTS = SKILL / 'experiments.json'

FORMATS = {
    'typst': ('实验报告.typ', 'Typst → PDF'),
    'latex': ('实验报告.tex', 'LaTeX → PDF'),
    'docx': ('实验报告.docx', 'Word 文档'),
    'md': ('实验报告.md', 'Markdown'),
}

# 正文分节顺序（md 和 docx 共用; typst/latex 的分节在各自模板里）
SECTIONS = ('实验目的', '仪器用具', '实验原理', '实验内容', '实验数据', '数据处理与结果', '问题讨论')

if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ---------------- 小工具 ----------------

def load_experiments():
    data = json.loads(EXPERIMENTS.read_text(encoding='utf-8'))
    return data['实验']


def norm_date(s):
    """任意写法 -> ('2026 年 9 月 26 日', ('2026','9','26'))；空的就返回空。"""
    s = (s or '').strip()
    if not s:
        return '', ('', '', '')
    m = re.search(r'(\d{4})\D+(\d{1,2})\D+(\d{1,2})', s)
    if not m:
        return s, ('', '', '')
    y, mo, d = m.groups()
    return f'{y} 年 {int(mo)} 月 {int(d)} 日', (y, str(int(mo)), str(int(d)))


def split_group(s):
    """'1-04-5' -> ('1','04','5')；写不出三段就整串塞进第一段。"""
    s = (s or '').strip()
    m = re.fullmatch(r'\s*(\S+?)\s*[-－—/]\s*(\S+?)\s*[-－—/]\s*(\S+)\s*', s)
    if m:
        return m.groups()
    return (s, '', '')


def safe_name(s, fallback='未命名'):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', (s or '').strip()).strip('. ')
    return s or fallback


def unique(path: Path) -> Path:
    """目标已存在就加 -2 / -3 …，绝不覆盖用户的东西。"""
    if not path.exists():
        return path
    for i in range(2, 100):
        cand = path.with_name(f'{path.stem}-{i}{path.suffix}')
        if not cand.exists():
            return cand
    raise RuntimeError(f'{path} 及 99 个备选名都被占了')


def appx_name(name: str) -> str:
    """附录文件的归档名: 连空格也换掉 —— LaTeX 的 \\includegraphics 路径里有空格会炸。"""
    return re.sub(r'\s+', '_', safe_name(name))


# ---------------- 附录: 预习报告 / 数据记录 ----------------
# 课程/老师常要求把预习报告、数据记录附在报告后面。上传时归档到 实验数据/ 下的同名目录,
# 生成的骨架就把这两节排好（正文由 agent 写, 附录不用它管）。文件不在就不生成空附录。

IMG_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.svg'}
APPENDIX = (('预习报告', '附录 A：预习报告'), ('数据记录', '附录 B：数据记录'))
APPENDIX_KEYS = tuple(k for k, _ in APPENDIX)


def appendix_items(p: dict) -> list:
    """[(小节标题, [相对 实验数据/ 的路径...]), ...]；没传就空。"""
    return [(label, list(p.get(key) or [])) for key, label in APPENDIX if p.get(key)]


def file_kind(rel: str) -> str:
    ext = Path(rel).suffix.lower()
    return 'pdf' if ext == '.pdf' else ('img' if ext in IMG_EXT else 'other')


def img_size(path) -> tuple:
    """读 PNG/JPEG 的像素尺寸, 只认文件头, 不引入 Pillow 依赖。认不出就 (0, 0)。"""
    try:
        data = Path(path).read_bytes()[:64 * 1024]
    except OSError:
        return (0, 0)
    if data.startswith(b'\x89PNG') and len(data) > 24:
        w = int.from_bytes(data[16:20], 'big')
        h = int.from_bytes(data[20:24], 'big')
        return (w, h)
    if data.startswith(b'\xff\xd8'):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(data[i + 5:i + 7], 'big')
                w = int.from_bytes(data[i + 7:i + 9], 'big')
                return (w, h)
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seglen = int.from_bytes(data[i + 2:i + 4], 'big')
            i += 2 + max(seglen, 2)
    return (0, 0)


# 附录图排版: 每页放 2 张, 别一张图占一页 —— 报告总页数要压在 10 页以内(含附录)
APPX_BOX_CM = (16.0, 11.5)          # (宽, 高) 上限, A4 + 2.3cm 页边距的大致可用区
APPX_BOX_IN = (5.9, 4.4)            # docx 用英寸
EMU_PER_IN = 914400
EMU_PER_CM = 360000


def fit_cm(path) -> float:
    """算出这张图该显示多宽(cm), 同时不超过高上限。尺寸读不出来就按满宽。"""
    w, h = img_size(path)
    max_w, max_h = APPX_BOX_CM
    if not w or not h:
        return max_w
    return round(min(max_w, max_h * w / h), 1)


def appendix_typst(p: dict) -> str:
    out = []
    for label, files in appendix_items(p):
        out += ['', '#pagebreak()', f'#heading(numbering: none, outlined: false)[{label}]', '']
        for rel in files:
            kind = file_kind(rel)
            if kind == 'img':
                # 限高: 一张图别吃掉整页, 报告要压在 10 页内
                out.append(f'#align(center)[#image("{rel}", height: 44%)]')
            elif kind == 'pdf':
                out.append(f'// {rel} 是 PDF, Typst 嵌不进去: 改用 LaTeX 出报告, '
                           '或先用 PDF 工具把两份合并')
            else:
                out.append(f'// 附件 {rel}（非图片/PDF），手动附上')
            out.append('')
    return '\n'.join(out)


def appendix_latex(p: dict) -> str:
    if not appendix_items(p):
        return ''
    out = ['', '% ============ 附录（生成器按上传的文件排好的）============', r'\clearpage']
    for label, files in appendix_items(p):
        out.append(r'\section*{' + label.replace('：', r'\quad ') + '}')
        for rel in files:
            posix = rel.replace('\\', '/')
            kind = file_kind(rel)
            if kind == 'img':
                # 限高 + 居中, 每页两张; 图之间不再 \clearpage(那是页数翻倍的主要原因)
                out += [r'\begin{center}',
                        r'\includegraphics[width=\linewidth,height=0.44\textheight,keepaspectratio]{'
                        + posix + '}',
                        r'\end{center}', r'\vspace{0.3em}']
            elif kind == 'pdf':
                out.append(r'\includepdf[pages=-,fitpaper=true]{' + posix + '}')   # 缺 pdfpages 会画提示框
            else:
                out.append('% 附件 ' + rel + '（非图片/PDF）排不进 PDF，手动附上')
    return '\n'.join(out) + '\n'


def appendix_md(p: dict) -> list:
    out = []
    for label, files in appendix_items(p):
        out += ['---', '', f'## {label}', '']
        for rel in files:
            kind = file_kind(rel)
            if kind == 'img':
                out += [f'![{label}]({rel})', '']
            elif kind == 'pdf':
                out += [f'[{label}（PDF）]({rel})', '']
            else:
                out += [f'- 附件：`{rel}`', '']
    return out


# ---------------- 四种格式 ----------------

def typst_head_vals(p: dict) -> dict:
    _, (y, mo, d) = norm_date(p['实验日期'])
    return {
        'exp_name': p['实验名称'],
        'teacher': p['指导教师'],
        'student': p['姓名'],
        'student_id': p['学号'],
        'class_group': p['分班分组及座号'],
        'date': f'{y} 年 {mo} 月 {d} 日' if y else p['实验日期'],
        'room': p['实验地点'],
        'others': p['调课补课'],
        'grade': p['成绩评定'],
        'mates': p['同组人员'],
    }


def apply_typst_head(text: str, p: dict) -> str:
    """把报告头那几行 #let 换成参数值。整份生成与 --head-only 共用这一份, 免得两条路填法跑偏。"""
    for k, v in typst_head_vals(p).items():
        v = str(v).replace('\\', '\\\\').replace('"', '\\"')
        text, n = re.subn(rf'^#let {k} = .*$', f'#let {k} = "{v}"', text, count=1, flags=re.M)
        if n != 1:
            raise RuntimeError(f'找不到 `#let {k}` 那一行（模板被改过? 或报告头不是生成器写的）')
    return text


def fill_typst(dst: Path, p: dict):
    """变量式模板: 替换开头那几个 #let 的值, 补充说明放成注释块。"""
    text = apply_typst_head((TEMPLATES / 'report.typ').read_text(encoding='utf-8'), p)
    text = notes_block(text, '// ', ['补充说明（写报告时看，定稿前把整段删掉）：']
                       + p['补充说明'].splitlines()) if p['补充说明'] else text
    if p['补充文件']:
        text = notes_block(text, '// ', ['参考文件（报告同目录）：'] + p['补充文件'])
    text += appendix_typst(p)                      # 预习报告 / 数据记录 附在最后
    dst.write_text(text, encoding='utf-8')


def head_typst(dst: Path, p: dict):
    """--head-only: 只重写报告头那几行 #let, 正文（含已写好的分节内容）原样保留。"""
    dst.write_text(apply_typst_head(dst.read_text(encoding='utf-8'), p), encoding='utf-8')


def notes_block(text: str, prefix: str, lines):
    head = '// ============ 生成器加的备注（定稿前删） ============\n'
    return head + ''.join(prefix + ln + '\n' for ln in lines) + '\n' + text


def latex_head_vals(p: dict) -> dict:
    _, (y, mo, d) = norm_date(p['实验日期'])
    cls, grp, seat = split_group(p['分班分组及座号'])
    # 官方报告头是"调课/补课 □是": 打了勾就往方框里叠一个对号(模板注释里就是这么教的)
    tick = r'$\square$\hspace{-1em}$\surd$' if p['调课补课'] else r'$\square$'
    return {
        'experiName': p['实验名称'], 'supervisor': p['指导教师'], 'name': p['姓名'],
        'studentNum': p['学号'], 'class': cls, 'group': grp, 'seat': seat,
        'dateYear': y, 'dateMonth': mo, 'dateDay': d, 'room': p['实验地点'],
        'others': tick, 'grade': p['成绩评定'],
    }


def apply_latex_head(text: str, p: dict) -> str:
    """把报告头那串 \\newcommand 换成参数值。整份生成与 --head-only 共用。"""
    for k, v in latex_head_vals(p).items():
        text, n = re.subn(rf'(\\newcommand\{{\\{k}\}}){{[^}}]*}}',
                          lambda m: m.group(1) + '{' + str(v) + '}', text, count=1)
        if n != 1:
            raise RuntimeError(f'找不到 \\newcommand{{{k}}} 那一行（模板被改过? 或报告头不是生成器写的）')
    return text


def fill_latex(dst: Path, p: dict):
    """学长模板只取导言区+报告头; 正文是空的, 不用拷字体(用系统字体名)。"""
    text = apply_latex_head((TEMPLATES / 'latex' / 'main.tex').read_text(encoding='utf-8'), p)
    head = ''
    if p['补充说明']:
        head += '% ---- 补充说明（写报告时看，定稿前删掉）----\n'
        head += ''.join('% ' + ln + '\n' for ln in p['补充说明'].splitlines())
        head += '\n'
    if p['补充文件']:
        head += '% ---- 参考文件（报告同目录）----\n'
        head += ''.join('% ' + f + '\n' for f in p['补充文件']) + '\n'
    body = text.rsplit(r'\end{document}', 1)          # 附录插在 \end{document} 之前
    text = body[0] + appendix_latex(p) + r'\end{document}' + body[1] if len(body) == 2 else text
    dst.write_text(head + text, encoding='utf-8')


def head_latex(dst: Path, p: dict):
    """--head-only: 只重写报告头那几个宏, 正文原样保留。"""
    dst.write_text(apply_latex_head(dst.read_text(encoding='utf-8'), p), encoding='utf-8')


def md_head_lines(p: dict) -> list:
    """markdown 的报告头: 标题 + 两列字段表, 字段与顺序照课程统一报告头。"""
    disp, _ = norm_date(p['实验日期'])
    rows = [
        ('实验名称', p['实验名称']), ('指导教师', p['指导教师']),
        ('姓名', p['姓名']), ('学号', p['学号']),
        ('分班分组及座号', p['分班分组及座号']), ('实验日期', disp),
        ('实验地点', p['实验地点']), ('调课/补课', '☑ 是' if p['调课补课'] else '□ 是'),
        ('成绩评定', p['成绩评定']),                      # 留空也留着这一格: 四个格式的字段集要一致
    ]
    if p['同组人员']:
        rows.append(('同组人员', p['同组人员']))
    out = ['# 《基础物理实验》实验报告', '']
    for i in range(0, len(rows), 2):
        a = rows[i]
        b = rows[i + 1] if i + 1 < len(rows) else ('', '')
        out.append(f'| {a[0]} | {a[1]} | {b[0]} | {b[1]} |')
        if i == 0:
            out.append('|---|---|---|---|')
    return out


def fill_md(dst: Path, p: dict):
    out = md_head_lines(p) + ['']
    for h in SECTIONS:
        out += [f'## {h}', '', '']
    if p['补充说明']:
        out += ['---', '', '> **补充说明（写报告时看，定稿前删掉）**', '>']
        out += ['> ' + ln for ln in p['补充说明'].splitlines()]
        out.append('')
    if p['补充文件']:
        out += ['参考文件（报告同目录）：' + '、'.join(p['补充文件']), '']
    out += appendix_md(p)                          # 预习报告 / 数据记录 附在最后
    dst.write_text('\n'.join(out) + '\n', encoding='utf-8')


def head_md(dst: Path, p: dict):
    """--head-only: 只换标题和字段表; 第一个 ## 分节往下一律不动。"""
    lines = dst.read_text(encoding='utf-8').split('\n')
    if not lines or not lines[0].startswith('# '):
        raise RuntimeError('这份 markdown 开头不是 "# 标题", 认不出报告头, 请重新生成一次')
    end = None
    for i in range(1, min(len(lines), 15)):        # 报告头就在开头几个, 别往里找太远
        if lines[i].startswith('|'):
            end = i
        elif end is not None:
            break
    if end is None:
        raise RuntimeError('这份 markdown 的报告头里找不到字段表, 请重新生成一次')
    rest = lines[end + 1:]
    while rest and rest[0].strip() == '':          # 表后那个空行由 md_head_lines 补, 免得越攒越多
        rest.pop(0)
    dst.write_text('\n'.join(md_head_lines(p) + [''] + rest), encoding='utf-8')


# ---- docx: 拿官方报告头当容器, 只换掉 word/document.xml ----
# 手搓最小 docx 包也能被 Word 打开, 但样式/主题/页眉页脚/编号这些都得自己补;
# 直接沿用官方那份的包结构, Word 亲生的最稳(顺便继承它的字体与页面设置)。

W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
DOCX_CONTAINER = TEMPLATES / 'docx' / '官方报告头容器.docx'


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def w_run(text, *, bold=False, size=21, underline=False, font='SimSun', ea='SimSun'):
    rpr = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:eastAsia="{ea}"/>']
    if bold:
        rpr.append('<w:b/>')
    if underline:
        rpr.append('<w:u w:val="single"/>')
    rpr.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    return (f'<w:r><w:rPr>{"".join(rpr)}</w:rPr>'
            f'<w:t xml:space="preserve">{esc(text)}</w:t></w:r>')


def w_p(runs, *, align=None, spacing=None, bottom_border=False):
    ppr = []
    if bottom_border:
        ppr.append('<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="1" w:color="000000"/></w:pBdr>')
    if spacing:
        ppr.append(f'<w:spacing w:before="{spacing}" w:after="{spacing}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    return f'<w:p>{"<w:pPr>" + "".join(ppr) + "</w:pPr>" if ppr else ""}{runs}</w:p>'


def w_cell(text, width, *, bold=False, blank=9):
    shown = text if str(text).strip() else ' ' * blank
    body = w_p(w_run(shown, bold=bold, underline=not str(text).strip()))
    return (f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>{body}</w:tc>')


def build_docx_head(p: dict) -> list:
    """报告头三件套: 大标题 + 字段表 + 一条分隔线。字段与顺序照课程统一报告头。
    整份生成与 --head-only 共用。"""
    disp, _ = norm_date(p['实验日期'])
    cols = (1900, 2900, 1900, 2400)
    rows = [
        ('实验名称', p['实验名称'], '指导教师', p['指导教师']),
        ('姓名', p['姓名'], '学号', p['学号']),
        ('分班分组及座号', p['分班分组及座号'], '实验日期', disp),
        ('实验地点', p['实验地点'], '调课/补课', '☑ 是' if p['调课补课'] else '□ 是'),
        ('成绩评定', p['成绩评定'], '同组人员', p['同组人员']),
    ]
    tbl = ['<w:tbl><w:tblPr><w:tblW w:w="9100" w:type="dxa"/><w:tblBorders>'
           + ''.join(f'<w:{s} w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                     for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
           + '</w:tblBorders><w:tblCellMar>'
             '<w:top w:w="40" w:type="dxa"/><w:left w:w="40" w:type="dxa"/>'
             '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="40" w:type="dxa"/>'
             '</w:tblCellMar></w:tblPr><w:tblGrid>'
           + ''.join(f'<w:gridCol w:w="{c}"/>' for c in cols) + '</w:tblGrid>']
    for label1, v1, label2, v2 in rows:
        tbl.append('<w:tr>' + w_cell(label1, cols[0]) + w_cell(v1, cols[1])
                   + w_cell(label2, cols[2]) + w_cell(v2, cols[3]) + '</w:tr>')
    tbl.append('</w:tbl>')

    body = [
        w_p(w_run('《基础物理实验》实验报告', bold=True, size=32, font='SimHei', ea='SimHei'),
            align='center', spacing=60),
        ''.join(tbl),
        w_p(w_run('', size=2), bottom_border=True, spacing=20),
    ]
    return body


def docx_picture(rid: str, pid: int, name: str, w_px: int, h_px: int) -> str:
    """一张内嵌图片的 DrawingML。按 APPX_BOX_IN 缩放, 保证每页能放两张。"""
    max_w, max_h = APPX_BOX_IN
    w_in = (w_px or 0) / 96.0
    h_in = (h_px or 0) / 96.0
    if w_in <= 0 or h_in <= 0:                       # 尺寸读不出来就按上限框排
        w_in, h_in = max_w, max_h
    s = min(max_w / w_in, max_h / h_in, 1.0)
    cx, cy = int(w_in * s * EMU_PER_IN), int(h_in * s * EMU_PER_IN)
    return (
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
        f'<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{pid}" name="Picture{pid}" descr="{esc(name)}"/>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic><pic:nvPicPr>'
        f'<pic:cNvPr id="{pid}" name="{esc(name)}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')


def appendix_docx(p: dict, data_dir: Path):
    """附录 A/B: 图片真的嵌进 docx(加 media 部件 + 关系), PDF 塞不进去就留一行说明。
    返回 (段落 XML 列表, 待加入包的 media 列表)。"""
    body, media = [], []
    n = 0
    for label, files in appendix_items(p):
        body.append(w_p(w_run(label, bold=True, size=24, font='SimHei', ea='SimHei'),
                        align='left', spacing=60))
        for rel in files:
            kind = file_kind(rel)
            src = data_dir / rel
            if kind == 'img' and src.is_file():
                n += 1
                ext = src.suffix.lower().lstrip('.')          # 部件名保留原后缀(jpg 就写 jpg)
                mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else \
                       ('image/svg+xml' if ext == 'svg' else 'image/' + ext)
                media.append({
                    'part': f'word/media/appendix{n}.{ext}',
                    'ctype': mime, 'ext': ext, 'data': src.read_bytes(),
                    'rid': f'rIdImg{n}',
                })
                w_px, h_px = img_size(src)
                body.append(docx_picture(f'rIdImg{n}', n, src.name, w_px, h_px))
            elif kind == 'pdf':
                body.append(w_p(w_run(
                    f'{rel}（PDF — Word 里塞不进去: 当附件单独交, 或用 LaTeX 出报告自动附上）', size=18)))
            else:
                body.append(w_p(w_run(f'{rel}（这个后缀 Word 也不认，单独交）', size=18)))
    return body, media


def build_docx_body(p: dict, data_dir: Path):
    """返回 (document.xml 文本, media 列表)。"""
    body = build_docx_head(p)
    for h in SECTIONS:
        body.append(w_p(w_run(h, bold=True, size=24, font='SimHei', ea='SimHei'),
                        align='left', spacing=60))
        body.append(w_p(w_run('', size=21)))
        body.append(w_p(w_run('', size=21)))
    if p['补充说明']:
        body.append(w_p(w_run('【补充说明（写报告时看，定稿前整段删掉）】', bold=True, size=21,
                              font='SimHei', ea='SimHei')))
        for ln in p['补充说明'].splitlines():
            body.append(w_p(w_run(ln, size=21)))
    if p['补充文件']:
        body.append(w_p(w_run('参考文件（报告同目录）：' + '、'.join(p['补充文件']), size=18)))
    appx, media = appendix_docx(p, data_dir)      # 预习报告 / 数据记录 附在最后
    body += appx

    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1134" '
            'w:bottom="1440" w:left="1134" w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document {W_NS}><w:body>' + ''.join(body) + sect + '</w:body></w:document>'), media


def patch_content_types(xml: str, media) -> str:
    """给新加的图片后缀补 Default 条目, 否则 Word 说文件损坏。"""
    for m in media:
        key = f'Extension="{m["ext"]}"'
        if key not in xml and key.upper() not in xml.upper():
            xml = xml.replace('</Types>',
                              f'<Default {key} ContentType="{m["ctype"]}"/></Types>')
    return xml


def patch_docx_rels(xml: str, media) -> str:
    rel = ''.join(
        f'<Relationship Id="{m["rid"]}" Type="http://schemas.openxmlformats.org/officeDocument/'
        f'2006/relationships/image" Target="media/{Path(m["part"]).name}"/>' for m in media)
    return xml.replace('</Relationships>', rel + '</Relationships>')


def set_core_props(xml: str, p: dict) -> str:
    """文档属性里的标题/作者换成自己的。"""
    for tag, val in (('dc:title', p['实验名称']), ('dc:creator', p['姓名']),
                     ('cp:lastModifiedBy', p['姓名'])):
        xml = re.sub(rf'(<{tag}[^>]*>).*?(</{tag}>)',
                     lambda m, v=val: m.group(1) + esc(v) + m.group(2), xml)
    return xml


def fill_docx(dst: Path, p: dict):
    if not DOCX_CONTAINER.is_file():
        raise FileNotFoundError(f'缺少 docx 容器: {DOCX_CONTAINER}')
    doc, media = build_docx_body(p, dst.parent)
    with zipfile.ZipFile(DOCX_CONTAINER) as zin, \
            zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                data = doc.encode('utf-8')
            elif item.filename == 'docProps/core.xml':      # 属性里的作者/标题换成自己的
                data = set_core_props(data.decode('utf-8'), p).encode('utf-8')
            elif item.filename == '[Content_Types].xml' and media:
                data = patch_content_types(data.decode('utf-8'), media).encode('utf-8')
            elif item.filename == 'word/_rels/document.xml.rels' and media:
                data = patch_docx_rels(data.decode('utf-8'), media).encode('utf-8')
            zout.writestr(item, data)
        for m in media:                                  # 附录图片本体
            zout.writestr(m['part'], m['data'])


def head_docx(dst: Path, p: dict):
    """--head-only: 只换报告头三件套和文档属性, 正文段落（含你在 Word 里写的）全留着。

    定位靠段落里的**文字**（"实验目的"等）而不是某段固定标签串: Word 存盘会重排 XML 属性、
    切分 run, 写死标签串的话你改一次正文就对不上了。
    """
    tmp = dst.with_name(dst.name + '.tmp')
    with zipfile.ZipFile(dst) as zin:
        names = {i.filename for i in zin.infolist()}
        if 'word/document.xml' not in names:
            raise RuntimeError(f'{dst.name} 里没有 word/document.xml, 不像一份 docx')
        xml = zin.read('word/document.xml').decode('utf-8')
        body_at = xml.find('<w:body>')
        if body_at < 0:
            raise RuntimeError(f'{dst.name} 里找不到 <w:body>, 不像一份 docx')
        cuts = [c for c in (xml.find(f'>{h}<') for h in SECTIONS) if c > body_at]
        if not cuts:
            raise RuntimeError(f'这份 docx 里找不到分节标题（{SECTIONS[0]}…）, 认不出报告头到哪为止, '
                               '请重新生成一次')
        head_end = min(cuts)
        starts = [m.start() for m in re.finditer(r'<w:p[ >]', xml[body_at:head_end])]
        if not starts:
            raise RuntimeError('这份 docx 的报告头里找不到段落, 请重新生成一次')
        xml = (xml[:body_at + len('<w:body>')] + ''.join(build_docx_head(p))
               + xml[body_at + starts[-1]:])
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'word/document.xml':
                    data = xml.encode('utf-8')
                elif item.filename == 'docProps/core.xml':
                    data = set_core_props(data.decode('utf-8'), p).encode('utf-8')
                zout.writestr(item, data)
    tmp.replace(dst)


WRITERS = {'typst': fill_typst, 'latex': fill_latex, 'docx': fill_docx, 'md': fill_md}
HEAD_ONLY = {'typst': head_typst, 'latex': head_latex, 'docx': head_docx, 'md': head_md}


# ---------------- 总入口 ----------------

def target_dirs(params: dict, root: Path):
    """<root>/<实验目录名>/实验数据/ —— UI 也要用这个推导, 所以单独拎出来。"""
    exp = (params.get('实验名称') or '').strip()
    if not exp:
        raise ValueError('实验名称不能为空')
    exp_dir = root / safe_name(params.get('实验目录名') or exp)
    return exp_dir, exp_dir / '实验数据'


def exp_dirname(exp: str) -> str:
    """实验子目录名: 按 experiments.json 里记的 dir, 没记就用实验名。"""
    for e in load_experiments():
        if e['name'] == exp and e.get('dir'):
            return e['dir']
    return exp


def existing_params(exp: str, root: Path, dir_name=None) -> dict:
    """--head-only 的底稿: 上次那份 报告参数.json; 没有就按目录里现存哪种报告文件推。

    子目录名到底叫什么不用你猜: 显式给的 -> experiments.json 里记的 dir -> 就用实验名称,
    三个都找一遍。
    """
    looked = []
    for name in dict.fromkeys([dir_name, exp_dirname(exp), exp]):      # 去重且保序
        if not name:
            continue
        _, data_dir = target_dirs({'实验名称': exp, '实验目录名': name}, root)
        looked.append(data_dir)
        meta_path = data_dir / '报告参数.json'
        if meta_path.is_file():
            params = json.loads(meta_path.read_text(encoding='utf-8'))
            params['实验目录名'] = name          # 就以"在这儿找到它"的目录为准
            return params
        for fmt, (fname, _) in FORMATS.items():
            if (data_dir / fname).is_file():
                return {'实验名称': exp, '实验目录名': name, '输出格式': fmt}
    raise FileNotFoundError(f'没找到「{exp}」的报告, 这几处都看过了: '
                            + ' / '.join(str(d) for d in looked))


def make(params: dict, root: Path, force=False, copy_files=True, head_only=False):
    """把参数落成一整套文件, 返回给 UI 用的结果字典。

    head_only=True: 只重写报告头，已写好的正文一个字不动（所以 force 在这里没意义）。
    报告文件还不存在时报 FileNotFoundError —— 先把骨架生成出来，再来改报告头。
    """
    exp = (params.get('实验名称') or '').strip()
    if not exp:
        raise ValueError('实验名称不能为空')
    fmt = (params.get('输出格式') or 'typst').lower()
    if fmt not in FORMATS:
        raise ValueError(f'输出格式只能是 {"/".join(FORMATS)}, 收到 {fmt!r}')

    exp_dir, data_dir = target_dirs(params, root)
    data_dir.mkdir(parents=True, exist_ok=True)

    p = {}
    for k in ('实验名称', '指导教师', '姓名', '学号', '分班分组及座号',
              '实验日期', '实验地点', '同组人员', '调课补课', '成绩评定', '补充说明'):
        v = params.get(k)
        p[k] = '' if v is None else str(v).strip()
    p['实验名称'] = exp
    copied = []

    if copy_files:
        for key, sub in (('补充文件', '补充文件'), ('记录纸照片', '照片'),
                         ('预习报告', '预习报告'), ('数据记录', '数据记录')):
            for f in params.get(key) or []:
                src = Path(f)
                if not src.is_file():
                    raise ValueError(f'{key}里这个文件找不到: {src}')
                target_dir = data_dir / sub
                target_dir.mkdir(parents=True, exist_ok=True)
                base = target_dir / (appx_name(src.name) if key in APPENDIX_KEYS else safe_name(src.name))
                if base.is_file() and base.read_bytes() == src.read_bytes():
                    dst = base            # 同名同内容说明已经归档过了, 不重复堆 -2 -3
                else:
                    dst = unique(base)
                    shutil.copy2(src, dst)
                copied.append(dst.relative_to(data_dir).as_posix())
    for key, sub in (('补充文件', '补充文件'), ('记录纸照片', '照片'),
                     ('预习报告', '预习报告'), ('数据记录', '数据记录')):
        p[key] = [c for c in copied if c.startswith(sub + '/')]

    report = data_dir / FORMATS[fmt][0]
    existed = report.exists()
    if head_only:
        if not existed:
            raise FileNotFoundError(f'{report} 还没有；先用正常模式生成一次骨架，之后才能只改报告头')
        HEAD_ONLY[fmt](report, p)
    else:
        if existed and not force:
            raise FileExistsError(f'{report} 已存在；要重新生成请勾选"覆盖已有报告"或加 --force'
                                  '（只想改报告头就勾"只更新报告头"或加 --head-only，正文不会动）')
        WRITERS[fmt](report, p)

    meta = dict(p)
    meta.update({
        '输出格式': fmt,
        '实验目录': str(exp_dir.resolve()),
        '报告文件': report.name,
        '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '生成方式': '只更新报告头（正文未动）' if head_only else '整份重新生成',
        '是否覆盖了已有报告': existed and not head_only,
        '注意': '报告头/分节版式是默认值；课程当年要求若不同，以用户上传或说明的为准（见 SKILL.md「材料优先级」）',
    })
    params_path = data_dir / '报告参数.json'
    params_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    return {
        'ok': True, '实验名称': exp, '输出格式': fmt, '只更新报告头': bool(head_only),
        '实验目录': str(exp_dir.resolve()), '报告文件': str(report.resolve()),
        '参数文件': str(params_path.resolve()),
        '归档': copied, '覆盖已有': existed and not head_only,
    }


def main(argv):
    ap = argparse.ArgumentParser(description='生成实验报告骨架（typst / latex / docx / md）')
    ap.add_argument('--info', help='报告参数.json：一次把所有字段传进来（UI 用）')
    ap.add_argument('--list', action='store_true', help='列出实验名清单')
    ap.add_argument('--exp', help='实验名称')
    ap.add_argument('--fmt', choices=list(FORMATS), help='输出格式(默认 typst; --head-only 时默认沿用已有的)')
    ap.add_argument('--name', help='学生姓名(可空)')
    ap.add_argument('--teacher', help='指导教师(可空)')
    ap.add_argument('--date', help='实验日期, 如 2026-09-26(可空)')
    ap.add_argument('--sid', help='学号(可空)')
    ap.add_argument('--group', help='分班分组及座号, 如 1-04-5(可空)')
    ap.add_argument('--room', help='实验地点(可空)')
    ap.add_argument('--mates', help='同组人员(可空)')
    ap.add_argument('--others', help='调课/补课: 给了值就打勾(写"是"即可, 空=不勾)')
    ap.add_argument('--grade', help='成绩评定(老师填, 一般留空)')
    ap.add_argument('--notes', help='补充说明(可空)')
    ap.add_argument('--file', action='append', default=[], help='补充文件, 可重复')
    ap.add_argument('--photo', action='append', default=[], help='记录纸照片, 可重复')
    ap.add_argument('--prelab', action='append', default=[],
                    help='预习报告（PDF/图片，可重复）：会归档并附在报告最后')
    ap.add_argument('--record', action='append', default=[],
                    help='数据记录（PDF/图片，可重复）：会归档并附在报告最后')
    ap.add_argument('--root', default='.', help='实验目录的上级目录(默认当前目录)')
    ap.add_argument('--dir-name', help='实验子目录名(默认用实验名称)')
    pick = ap.add_mutually_exclusive_group()
    pick.add_argument('--force', action='store_true', help='覆盖已存在的报告文件')
    pick.add_argument('--head-only', action='store_true',
                      help='只更新报告头字段, 保留已写好的正文(两个选项互斥: 一个覆盖, 一个保留)')
    a = ap.parse_args(argv)

    if a.list:
        for e in load_experiments():
            print(f"  {e['name']}\t{e.get('dir','')}\t{' '.join(e.get('aliases', []))}")
        return 0

    try:
        if a.info:
            params = json.loads(Path(a.info).read_text(encoding='utf-8'))
        elif a.head_only:
            # 只改报告头时没给的字段沿用上次的 报告参数.json: 不然 --date 一条命令下去,
            # 姓名/学号这些没写的字段会被悄悄清空（报告头就变成空的了）
            if not a.exp:
                ap.error('--head-only 要么搭配 --info 报告参数.json, 要么给 --exp')
            dir_name = a.dir_name or exp_dirname(a.exp)
            params = existing_params(a.exp, Path(a.root), a.dir_name)
            for k, v in (('实验名称', a.exp), ('输出格式', a.fmt), ('姓名', a.name),
                         ('指导教师', a.teacher), ('实验日期', a.date), ('学号', a.sid),
                         ('分班分组及座号', a.group), ('实验地点', a.room),
                         ('同组人员', a.mates), ('调课补课', a.others),
                         ('成绩评定', a.grade), ('补充说明', a.notes)):
                if v is not None:                   # None = 没给这个选项; '' = 你要清空它
                    params[k] = v
            params.setdefault('实验目录名', dir_name)   # 底稿里已经定好了就听底稿的
        else:
            if not a.exp:
                ap.error('要么给 --exp, 要么给 --info')
            params = {'实验名称': a.exp, '输出格式': a.fmt or 'typst', '姓名': a.name,
                      '指导教师': a.teacher, '实验日期': a.date, '学号': a.sid,
                      '分班分组及座号': a.group, '实验地点': a.room,
                      '同组人员': a.mates, '调课补课': a.others, '成绩评定': a.grade,
                      '补充说明': a.notes,
                      '补充文件': a.file, '记录纸照片': a.photo,
                      '预习报告': a.prelab, '数据记录': a.record,
                      '实验目录名': a.dir_name}
        r = make(params, Path(a.root), force=a.force, head_only=a.head_only)
    except Exception as e:
        print(f'失败: {type(e).__name__}: {e}')
        return 1
    if r['只更新报告头']:
        print(f"报告头已更新 [{r['输出格式']}]（正文一个字都没动）")
    else:
        print(f"生成成功 [{r['输出格式']}]")
    print(f"  实验目录 {r['实验目录']}")
    print(f"  报告文件 {r['报告文件']}" + ('（覆盖了旧的）' if r['覆盖已有'] else ''))
    print(f"  参数文件 {r['参数文件']}")
    for c in r['归档']:
        print(f'  归档 {c}')
    if r['只更新报告头']:
        print('提示：补充说明/参考文件那两块备注块没动；正文也没动（这正是本题的意义）')
    else:
        print('下一步：按 SKILL.md 的流程写正文（先 §1 转录数据，再 §3 出图，最后填报告）')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
