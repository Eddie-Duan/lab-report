# -*- coding: utf-8 -*-
"""按"报告参数"生成报告骨架：typst / latex(tex) / docx / md 四种格式。

生成的只是**骨架 + 报告头**（报告头字段填好，正文分节留空），正文由 agent 用 SKILL.md 的流程写。
每次都写一份 `报告参数.json`（给 agent 读字段值），附件和记录纸照片也一起归到实验目录里。

命令行:
    python make_report.py --list                         # 列出实验名清单
    python make_report.py --exp 杨氏模量 --fmt typst --name 张三 --teacher 李四 \\
        --date 2026-09-26 --group 1-04-5 --file 补充.pdf --photo IMG_1.jpg
    python make_report.py --info 报告参数.json            # UI 走这个: 一次把参数都传进来

目录约定（与 SKILL.md 一致）:
    <root>/<实验目录>/实验数据/实验报告.<ext>
    <root>/<实验目录>/实验数据/报告参数.json
    <root>/<实验目录>/实验数据/补充文件/…
    <root>/<实验目录>/实验数据/照片/…

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


# ---------------- 四种格式 ----------------

def fill_typst(dst: Path, p: dict):
    """变量式模板: 替换开头那几个 #let 的值, 补充说明放成注释块。"""
    text = (TEMPLATES / 'report.typ').read_text(encoding='utf-8')
    _, (y, mo, d) = norm_date(p['实验日期'])
    vals = {
        'exp_name': p['实验名称'],
        'teacher': p['指导教师'],
        'student': p['姓名'],
        'student_id': p['学号'],
        'class_group': p['分班分组及座号'],
        'date': f'{y} 年 {mo} 月 {d} 日' if y else p['实验日期'],
        'room': p['实验地点'],
        'mates': p['同组人员'],
    }
    for k, v in vals.items():
        v = str(v).replace('\\', '\\\\').replace('"', '\\"')
        text, n = re.subn(rf'^#let {k} = .*$', f'#let {k} = "{v}"', text, count=1, flags=re.M)
        if n != 1:
            raise RuntimeError(f'模板里找不到 #let {k}, 模板被改动了?')
    text = notes_block(text, '// ', ['补充说明（写报告时看，定稿前把整段删掉）：']
                       + p['补充说明'].splitlines()) if p['补充说明'] else text
    if p['补充文件']:
        text = notes_block(text, '// ', ['参考文件（报告同目录）：'] + p['补充文件'])
    dst.write_text(text, encoding='utf-8')


def notes_block(text: str, prefix: str, lines):
    head = '// ============ 生成器加的备注（定稿前删） ============\n'
    return head + ''.join(prefix + ln + '\n' for ln in lines) + '\n' + text


def fill_latex(dst: Path, p: dict):
    """学长模板只取导言区+报告头; 正文是空的, 不用拷字体(用系统字体名)。"""
    text = (TEMPLATES / 'latex' / 'main.tex').read_text(encoding='utf-8')
    _, (y, mo, d) = norm_date(p['实验日期'])
    cls, grp, seat = split_group(p['分班分组及座号'])
    vals = {
        'experiName': p['实验名称'], 'supervisor': p['指导教师'], 'name': p['姓名'],
        'studentNum': p['学号'], 'class': cls, 'group': grp, 'seat': seat,
        'dateYear': y, 'dateMonth': mo, 'dateDay': d, 'room': p['实验地点'],
    }
    for k, v in vals.items():
        text, n = re.subn(rf'(\\newcommand\{{\\{k}\}}){{[^}}]*}}', lambda m: m.group(1) + '{' + str(v) + '}',
                          text, count=1)
        if n != 1:
            raise RuntimeError(f'LaTeX 模板里找不到 \\{k}, 模板被改动了?')
    head = ''
    if p['补充说明']:
        head += '% ---- 补充说明（写报告时看，定稿前删掉）----\n'
        head += ''.join('% ' + ln + '\n' for ln in p['补充说明'].splitlines())
        head += '\n'
    if p['补充文件']:
        head += '% ---- 参考文件（报告同目录）----\n'
        head += ''.join('% ' + f + '\n' for f in p['补充文件']) + '\n'
    dst.write_text(head + text, encoding='utf-8')


def fill_md(dst: Path, p: dict):
    disp, _ = norm_date(p['实验日期'])
    rows = [
        ('实验名称', p['实验名称']), ('指导教师', p['指导教师']),
        ('姓名', p['姓名']), ('学号', p['学号']),
        ('分班分组及座号', p['分班分组及座号']), ('实验日期', disp),
        ('实验地点', p['实验地点']), ('同组人员', p['同组人员']),
    ]
    out = ['# 《基础物理实验》实验报告', '']
    for i in range(0, len(rows), 2):
        a, b = rows[i], rows[i + 1]
        out.append(f'| {a[0]} | {a[1]} | {b[0]} | {b[1]} |')
        if i == 0:
            out.append('|---|---|---|---|')
    out.append('')
    for h in ('实验目的', '仪器用具', '实验原理', '实验内容', '实验数据', '数据处理与结果', '问题讨论'):
        out += [f'## {h}', '', '']
    if p['补充说明']:
        out += ['---', '', '> **补充说明（写报告时看，定稿前删掉）**', '>']
        out += ['> ' + ln for ln in p['补充说明'].splitlines()]
        out.append('')
    if p['补充文件']:
        out += ['参考文件（报告同目录）：' + '、'.join(p['补充文件']), '']
    dst.write_text('\n'.join(out) + '\n', encoding='utf-8')


# ---- docx: 拿官方报告头当容器, 只换掉 word/document.xml ----
# 手搓最小 docx 包也能被 Word 打开, 但样式/主题/页眉页脚/编号这些都得自己补;
# 直接沿用官方那份的包结构, Word 亲生的最稳(顺便继承它的字体与页面设置)。

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
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


def build_docx_body(p: dict) -> str:
    disp, _ = norm_date(p['实验日期'])
    cols = (1900, 2900, 1900, 2400)
    rows = [
        ('实验名称', p['实验名称'], '指导教师', p['指导教师']),
        ('姓名', p['姓名'], '学号', p['学号']),
        ('分班分组及座号', p['分班分组及座号'], '实验日期', disp),
        ('实验地点', p['实验地点'], '同组人员', p['同组人员']),
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
    for h in ('实验目的', '仪器用具', '实验原理', '实验内容', '实验数据', '数据处理与结果', '问题讨论'):
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

    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1134" '
            'w:bottom="1440" w:left="1134" w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<w:document {W_NS}><w:body>' + ''.join(body) + sect + '</w:body></w:document>')


def fill_docx(dst: Path, p: dict):
    if not DOCX_CONTAINER.is_file():
        raise FileNotFoundError(f'缺少 docx 容器: {DOCX_CONTAINER}')
    doc = build_docx_body(p)
    with zipfile.ZipFile(DOCX_CONTAINER) as zin, \
            zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                data = doc.encode('utf-8')
            elif item.filename == 'docProps/core.xml':      # 属性里的作者/标题换成自己的
                xml = data.decode('utf-8')
                for tag, val in (('dc:title', p['实验名称']), ('dc:creator', p['姓名']),
                                 ('cp:lastModifiedBy', p['姓名'])):
                    xml = re.sub(rf'(<{tag}[^>]*>).*?(</{tag}>)',
                                 lambda m, v=val: m.group(1) + esc(v) + m.group(2), xml)
                data = xml.encode('utf-8')
            zout.writestr(item, data)


WRITERS = {'typst': fill_typst, 'latex': fill_latex, 'docx': fill_docx, 'md': fill_md}


# ---------------- 总入口 ----------------

def target_dirs(params: dict, root: Path):
    """<root>/<实验目录名>/实验数据/ —— UI 也要用这个推导, 所以单独拎出来。"""
    exp = (params.get('实验名称') or '').strip()
    if not exp:
        raise ValueError('实验名称不能为空')
    exp_dir = root / safe_name(params.get('实验目录名') or exp)
    return exp_dir, exp_dir / '实验数据'


def make(params: dict, root: Path, force=False, copy_files=True):
    """把参数落成一整套文件, 返回给 UI 用的结果字典。"""
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
              '实验日期', '实验地点', '同组人员', '补充说明'):
        v = params.get(k)
        p[k] = '' if v is None else str(v).strip()
    p['实验名称'] = exp
    copied = []

    if copy_files:
        for key, sub in (('补充文件', '补充文件'), ('记录纸照片', '照片')):
            for f in params.get(key) or []:
                src = Path(f)
                if not src.is_file():
                    raise ValueError(f'{key}里这个文件找不到: {src}')
                target_dir = data_dir / sub
                target_dir.mkdir(parents=True, exist_ok=True)
                base = target_dir / safe_name(src.name)
                if base.is_file() and base.read_bytes() == src.read_bytes():
                    dst = base            # 同名同内容说明已经归档过了, 不重复堆 -2 -3
                else:
                    dst = unique(base)
                    shutil.copy2(src, dst)
                copied.append(dst.relative_to(data_dir).as_posix())
    p['补充文件'] = [c for c in copied if c.startswith('补充文件/')]
    p['记录纸照片'] = [c for c in copied if c.startswith('照片/')]

    report = data_dir / FORMATS[fmt][0]
    existed = report.exists()
    if existed and not force:
        raise FileExistsError(f'{report} 已存在；要重新生成请勾选"覆盖已有报告"或加 --force')

    WRITERS[fmt](report, p)

    meta = dict(p)
    meta.update({
        '输出格式': fmt,
        '实验目录': str(exp_dir.resolve()),
        '报告文件': report.name,
        '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '是否覆盖了已有报告': existed,
        '注意': '报告头/分节版式是默认值；课程当年要求若不同，以用户上传或说明的为准（见 SKILL.md「材料优先级」）',
    })
    params_path = data_dir / '报告参数.json'
    params_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    return {
        'ok': True, '实验名称': exp, '输出格式': fmt,
        '实验目录': str(exp_dir.resolve()), '报告文件': str(report.resolve()),
        '参数文件': str(params_path.resolve()),
        '归档': copied, '覆盖已有': existed,
    }


def main(argv):
    ap = argparse.ArgumentParser(description='生成实验报告骨架（typst / latex / docx / md）')
    ap.add_argument('--info', help='报告参数.json：一次把所有字段传进来（UI 用）')
    ap.add_argument('--list', action='store_true', help='列出实验名清单')
    ap.add_argument('--exp', help='实验名称')
    ap.add_argument('--fmt', default='typst', choices=list(FORMATS), help='输出格式(默认 typst)')
    ap.add_argument('--name', default='', help='学生姓名(可空)')
    ap.add_argument('--teacher', default='', help='指导教师(可空)')
    ap.add_argument('--date', default='', help='实验日期, 如 2026-09-26(可空)')
    ap.add_argument('--sid', default='', help='学号(可空)')
    ap.add_argument('--group', default='', help='分班分组及座号, 如 1-04-5(可空)')
    ap.add_argument('--room', default='', help='实验地点(可空)')
    ap.add_argument('--mates', default='', help='同组人员(可空)')
    ap.add_argument('--notes', default='', help='补充说明(可空)')
    ap.add_argument('--file', action='append', default=[], help='补充文件, 可重复')
    ap.add_argument('--photo', action='append', default=[], help='记录纸照片, 可重复')
    ap.add_argument('--root', default='.', help='实验目录的上级目录(默认当前目录)')
    ap.add_argument('--dir-name', help='实验子目录名(默认用实验名称)')
    ap.add_argument('--force', action='store_true', help='覆盖已存在的报告文件')
    a = ap.parse_args(argv)

    if a.list:
        for e in load_experiments():
            print(f"  {e['name']}\t{e.get('dir','')}\t{' '.join(e.get('aliases', []))}")
        return 0

    if a.info:
        params = json.loads(Path(a.info).read_text(encoding='utf-8'))
    else:
        if not a.exp:
            ap.error('要么给 --exp, 要么给 --info')
        params = {'实验名称': a.exp, '输出格式': a.fmt, '姓名': a.name, '指导教师': a.teacher,
                  '实验日期': a.date, '学号': a.sid, '分班分组及座号': a.group, '实验地点': a.room,
                  '同组人员': a.mates, '补充说明': a.notes,
                  '补充文件': a.file, '记录纸照片': a.photo, '实验目录名': a.dir_name}
    try:
        r = make(params, Path(a.root), force=a.force)
    except Exception as e:
        print(f'失败: {type(e).__name__}: {e}')
        return 1
    print(f"生成成功 [{r['输出格式']}]")
    print(f"  实验目录 {r['实验目录']}")
    print(f"  报告文件 {r['报告文件']}" + ('（覆盖了旧的）' if r['覆盖已有'] else ''))
    print(f"  参数文件 {r['参数文件']}")
    for c in r['归档']:
        print(f'  归档 {c}')
    print('下一步：按 SKILL.md 的流程写正文（先 §1 转录数据，再 §3 出图，最后填报告）')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
