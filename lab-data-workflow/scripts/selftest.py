# -*- coding: utf-8 -*-
"""回归自测：三个脚本 + 报告生成器 + UI 后端。改完代码跑一遍，全绿再提交。

    python selftest.py

不依赖 pytest，只用标准库。临时文件建在**当前目录**的 .selftest_tmp/ 下，跑完删掉
（不用系统临时目录：Windows 上那个目录常被策略挡住，写不进去）。
"""
import io
import json
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import contextlib
import threading
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import csv_tables as ct      # noqa: E402
import to_utf8 as tu         # noqa: E402
import prep_photo as pp      # noqa: E402
import make_report as mr     # noqa: E402
from PIL import Image, ImageDraw, ImageFilter   # noqa: E402

TMP = Path.cwd() / '.selftest_tmp'
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def raises(exc, fn, *a, **kw):
    """跑 fn, 断言它抛了 exc, 返回那个异常。"""
    try:
        fn(*a, **kw)
    except exc as e:
        return e
    except Exception as e:                       # 抛了别的类型也算不合格, 但要说清
        raise AssertionError(f'期望 {exc.__name__}, 实际 {type(e).__name__}: {e}') from e
    raise AssertionError(f'期望 {exc.__name__}, 但它正常返回了')


def capture(fn, *a, **kw):
    """跑 fn 并把 stdout 收起来(顺便把 argparse 的 SystemExit 传出去)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn(*a, **kw)
    return r, buf.getvalue()


def w(path, text, enc='utf-8'):
    Path(path).write_bytes(text.encode(enc))
    return Path(path)


def read(p):
    return Path(p).read_bytes()


# ---------------- csv_tables ----------------

@case
def test_roundtrip():
    p = TMP / 'a.csv'
    ct.write(p, [('横梁', [['测量次数', '1', '2', '3'],
                           ['长度d/cm', '23.60', '23.55', '23.57'],
                           ['宽度b/mm', '22.16', '', '22.02']])],
             comments=['照抄记录纸, 未换算'])
    t = ct.load(p)['横梁']
    assert ct.row(t, '长度d/cm') == [23.6, 23.55, 23.57]
    assert ct.row(t, '宽度b') == [22.16, None, 22.02], '空格子必须是 None, 不是 0'
    assert ct.col(t, 1) == [23.55, None]
    assert read(p).startswith(b'\xef\xbb\xbf') and b'\r\n' in read(p), '要 UTF-8 BOM + CRLF'


@case
def test_dup_section_raises():
    p = w(TMP / 'dup.csv', '# ---- 横梁 ----\n序号,1\n长度d,23.6\n'
                           '# ---- 横梁 ----\n序号,1\n宽度b,22.16\n')
    e = raises(ValueError, ct.load, p)
    assert '分段名重复' in str(e), e


@case
def test_nameless_marker_raises():
    e = raises(ValueError, ct.load, w(TMP / 'nm.csv', '# ----\n# --------\n序号,1\n'))
    assert '没有名字' in str(e), e


@case
def test_col_count():
    long_row = w(TMP / 'long.csv', '# ---- T ----\n序号,1,2\n备注,改后,原值7,ok\n')
    e = raises(ValueError, ct.load, long_row)
    assert '表头只有' in str(e), e

    short = w(TMP / 'short.csv', '# ---- T ----\n序号,1,2,3\nM,19.9,40.0\nZ,1.1,2.2,3.3\n')
    t, out = capture(ct.load, short)
    assert '末尾按空格子补齐' in out, '短行要警告'
    _h, rows = t['T']
    assert [len(r) for r in rows] == [4, 4], '补齐后才能对齐, 否则 zip 静默截断'


@case
def test_junk_vs_blank():
    p = w(TMP / 'junk.csv', '# ---- T ----\n序号,1,2,3\nL,23.60,,2.16O\n')
    t = ct.load(p)['T']
    e = raises(ValueError, ct.row, t, 'L')
    assert '读不成数字' in str(e) and '2.16O' in str(e), e
    assert ct.row(t, 'L', strict=False) == [23.6, None, None], 'strict=False 才是旧行为'


@case
def test_row_ambiguity():
    p = TMP / 'amb.csv'
    ct.write(p, [('T', [['序号', '1'], ['长度d/cm', '23.6'], ['长度d/mm', '236']])])
    t = ct.load(p)['T']
    e = raises(ValueError, ct.row, t, '长度d')
    assert '命中多行' in str(e), e
    assert ct.row(t, '长度d/mm') == [236.0], '写全标签要能精确定位'
    e = raises(KeyError, ct.row, t, '厚度a')
    assert '厚度a' in str(e), e


@case
def test_write_rejects_bad_values():
    for bad, why in [(23.6, 'float'), (True, 'bool'), ('改后,原值7', '逗号'), ('#注释', '# 开头'),
                     ('带\n换行', '换行')]:
        e = raises(ValueError, ct.write, TMP / 'x.csv', [('T', [['序号', '1'], ['L', bad]])])
        assert why.split()[0] not in ('',) and str(e), e
    raises(ValueError, ct.write, TMP / 'x.csv', [('T', [['序号', '1'], ['L', '1', '2']])])
    assert not (TMP / 'x.csv').exists(), '校验失败时不该写出半成品'


@case
def test_write_multiline_comment():
    p = TMP / 'c.csv'
    ct.write(p, [('T', [['序号', '1'], ['L', '23.6']])], comments=['第一行\n第二行'])
    assert ct.load(p)['T'][1] == [['L', '23.6']], '多行注释要逐行加 #, 否则自己都读不回来'


@case
def test_load_gbk_hint():
    p = w(TMP / 'gbk.csv', '# ---- T ----\n序号,1,2\n名称,甲,乙\n', enc='gb18030')
    e = raises(ValueError, ct.load, p)
    assert 'to_utf8.py' in str(e), '报错要直接告诉怎么修'


@case
def test_main_exit_code():
    assert ct.main([str(TMP / '不存在.csv')]) == 1, '读失败要返回 1'


# ---------------- to_utf8 ----------------

@case
def test_sniff():
    assert tu.sniff(b'abc,1\r\n') == 'ascii', '纯 ASCII 不需要 BOM'
    assert tu.sniff('\ufeff序号,1\n'.encode('utf-8')) == 'utf-8-bom'
    # UTF-8 的中文字节基本都能按 GB18030 解出生僻字, 这不算疑点, 别天天报警
    assert tu.sniff('序号,长度,测量次数\n'.encode('utf-8')) == 'utf-8'
    assert tu.sniff('序号,长度,测量次数\n'.encode('gb18030')) == 'gbk'
    # '一' 的 GBK 字节 D2 BB 恰好是合法 UTF-8(解成西里尔字母), 这必须标出来
    assert tu.sniff(b'# \xd2\xbb\n') == 'gbk?'
    assert tu.sniff(b'\xff\xfe\x00\x01') == 'unknown'


@case
def test_ambiguous_needs_confirmation():
    d = TMP / 'amb'
    d.mkdir(exist_ok=True)
    p = d / 'a.csv'
    p.write_bytes(b'# \xd2\xbb\n')                 # GBK 的 "# 一\n"
    before = read(p)

    rc, out = capture(tu.main, [str(d)])
    assert rc == 1 and read(p) == before, '认不准就不能改, 退出码 1'
    assert '--assume' in out and "gbk" in out, out

    rc, out = capture(tu.main, [str(d), '--assume', 'gbk'])
    assert rc == 0, out
    assert read(p).decode('utf-8-sig') == '# 一\n', read(p)

    p2 = d / 'b.csv'
    p2.write_bytes(b'# \xd2\xbb\n')
    rc, out = capture(tu.main, [str(p2), '--assume', 'utf8'])
    assert rc == 0 and read(p2).decode('utf-8-sig') == '# һ\n', read(p2)


@case
def test_check_is_dry_run():
    d = TMP / 'chk'
    d.mkdir(exist_ok=True)
    p = w(d / 'a.csv', '序号,长度\n1,23.60\n', enc='gb18030')
    before = read(p)
    rc, out = capture(tu.main, [str(d), '--check'])        # flag 放后面也必须还是 dry-run
    assert read(p) == before, '--check 一个字都不许改'
    assert not (d / 'a.csv.gbk.bak').exists(), '--check 不许写备份'
    assert rc == 1 and '<-- 需要转' in out, (rc, out)

    rc2, _ = capture(tu.main, ['--check', str(d)])
    assert rc2 == 1 and read(p) == before


@case
def test_convert_and_clean():
    d = TMP / 'conv'
    d.mkdir(exist_ok=True)
    p = w(d / 'a.csv', '序号,长度\n1,23.60\n', enc='gb18030')
    rc, out = capture(tu.main, [str(d)])
    assert rc == 0, out
    assert read(p).startswith(b'\xef\xbb\xbf')
    assert read(p).decode('utf-8-sig') == '序号,长度\n1,23.60\n', '内容要一字不差'
    assert (d / 'a.csv.gbk.bak').exists()
    assert '转出来长这样' in out, '要打印人眼可核对的一行'

    rc, out = capture(tu.main, ['--check', str(d)])
    assert rc == 0 and '<-- 需要转' not in out, out

    (d / 'a.csv').rename(d / 'b.csv')            # 改名后备份成了孤儿
    rc, out = capture(tu.main, ['--clean', str(d)])
    assert not (d / 'a.csv.gbk.bak').exists(), '改名后的孤儿备份也要删得到'
    assert rc == 0


@case
def test_convert_keeps_first_backup():
    d = TMP / 'keep'
    d.mkdir(exist_ok=True)
    p = w(d / 'a.csv', '序号,长度\n', enc='gb18030')
    capture(tu.main, [str(d)])
    first = read(d / 'a.csv.gbk.bak')
    p.write_bytes('序号,宽度\n'.encode('gb18030'))    # 被 Excel 又存回 GBK
    rc, out = capture(tu.main, [str(d)])
    assert read(d / 'a.csv.gbk.bak') == first, '最早那份备份不能被顶掉'
    assert '已有备份' in out, out


# ---------------- prep_photo ----------------

@case
def test_crop_coord_math():
    size = (400, 200)
    assert pp.parse_box('0.5,0.5,1,1', 'rel', size, 1600) == (200, 100, 400, 200)
    assert pp.parse_box('100,50,200,100', 'orig', size, 1600) == (100, 50, 200, 100)
    # 400x200 的图, --max-side 100 -> 总览是 0.25x, 总览上的 25,25,50,50 等于原图 100,100,200,200
    assert pp.parse_box('25,25,50,50', 'overview', size, 100) == (100, 100, 200, 200)
    raises(ValueError, pp.parse_box, '100,100,50,50', 'orig', size, 1600)
    raises(ValueError, pp.parse_box, '1,2,3', 'orig', size, 1600)
    raises(ValueError, pp.parse_box, '0.5,0.5,1,2', 'rel', size, 1600)


@case
def test_crop_clamp_warns():
    box, out = capture(pp.parse_box, '-50,-50,9999,9999', 'orig', (400, 200), 1600)
    assert box == (0, 0, 400, 200)
    assert '警告' in out and '超出图片' in out, '越界必须警告, 不能默默给一张整图'
    raises(ValueError, pp.parse_box, '500,500,600,600', 'orig', (400, 200), 1600)


@case
def test_autolevel_not_inverted():
    im = Image.new('L', (600, 400), 175)          # 灰纸
    d = ImageDraw.Draw(im)
    for y in range(20, 400, 20):
        d.rectangle([20, y, 560, y + 6], fill=140)   # 很淡的字迹
    im = im.filter(ImageFilter.GaussianBlur(1.0)).convert('RGB')
    out = pp.autolevel(im, radius=40)
    paper, ink = out.getpixel((590, 10)), out.getpixel((300, 23))
    assert paper > ink, f'纸({paper})必须比字({ink})亮 —— 反相了'
    assert paper - ink > 100, f'对比度没提上来: 纸{paper} 字{ink}'


@case
def test_overview_coord_crops_the_right_spot():
    """在总览上量的坐标必须裁到同一块内容 —— 这是最容易读错数字的一步。"""
    src = TMP / 'mark.jpg'
    im = Image.new('RGB', (400, 200), 'white')
    ImageDraw.Draw(im).rectangle([200, 100, 240, 140], fill='black')   # 要裁到的"字"
    im.save(src)

    def darkest(name):
        return Image.open(TMP / '_prep' / name).convert('L').getextrema()[0]

    # 总览 100 长边 => 0.25x, 黑块在总览上是 50,25 - 60,35
    rc, out = capture(pp.main, [str(src), '--max-side', '100',
                                '--crop', '45,20,70,45', '--coord', 'overview'])
    assert rc == 0 and '裁切区域(原图坐标) (180, 80, 280, 180)' in out, out
    assert 'x0.250' in out, '要把缩放比打给用户看: ' + out
    assert darkest('mark_c180-80-280-180_crop.jpg') < 60, '按总览坐标裁应该正好套住黑块'

    # 同样的四个数当原图坐标用(旧文档就是这么教的) => 裁到一片空白, 且不报错
    rc, out = capture(pp.main, [str(src), '--max-side', '100',
                                '--crop', '45,20,70,45', '--coord', 'orig'])
    assert rc == 0
    assert darkest('mark_c45-20-70-45_crop.jpg') > 200, '这正是"看着正常但是错的"那种裁法'


@case
def test_crop_files_dont_collide():
    src = TMP / 'photo.jpg'
    Image.new('RGB', (400, 200), 'white').save(src)
    for box in ('10,10,100,100', '200,10,300,100'):
        rc, _ = capture(pp.main, [str(src), '--crop', box, '--zoom', '2'])
        assert rc == 0
    made = sorted(x.name for x in (TMP / '_prep').glob('photo_c*_crop.jpg'))
    assert len(made) == 2, f'两次裁切写成了同一个名字: {made}'


@case
def test_exif_orientation():
    src = TMP / 'exif.jpg'
    im = Image.new('RGB', (400, 200), 'white')
    ex = im.getexif()
    ex[274] = 6                                   # 手机竖拍: 要顺时针 90 才正
    im.save(src, exif=ex)
    rc, out = capture(pp.main, [str(src)])
    assert rc == 0
    got = Image.open(TMP / '_prep' / 'exif_overview.jpg').size
    assert got == (200, 400), f'EXIF 没被应用, 还是 {got}'
    assert 'EXIF' in out, '要打印一行说明, 免得用户又手转一次'


@case
def test_bad_flags():
    src = TMP / 'photo.jpg'
    raises(SystemExit, capture, pp.main, [str(src), '--crop', '1,1,9,9', '--split'])
    raises(SystemExit, capture, pp.main, [str(src), '--rotate', '45'])
    rc, out = capture(pp.main, [str(src), '--zoom', '3'])
    assert rc == 0 and '只在 --crop 时生效' in out, out
    rc, out = capture(pp.main, [str(TMP / '不存在.jpg')])
    assert rc == 1, out


# ---------------- make_report + UI ----------------

def _params(**kw):
    p = {'实验名称': '测量金属的杨氏模量', '输出格式': 'typst', '姓名': '张三',
         '指导教师': '李四', '实验日期': '2026-09-26', '学号': '2026K8009900001',
         '分班分组及座号': '1-04-5', '实验地点': '西实验楼203', '同组人员': '王五',
         '补充说明': '今年要求写思考题'}
    p.update(kw)
    return p


@case
def test_norm_date_and_group():
    assert mr.norm_date('2026-09-26') == ('2026 年 9 月 26 日', ('2026', '9', '26'))
    assert mr.norm_date('2026年9月26日')[0] == '2026 年 9 月 26 日'
    assert mr.norm_date('') == ('', ('', '', ''))
    assert mr.norm_date('待定') == ('待定', ('', '', ''))
    assert mr.split_group('1-04-5') == ('1', '04', '5')
    assert mr.split_group('2－06－5') == ('2', '06', '5'), '全角连字符也要认'
    assert mr.split_group('1/04/5') == ('1', '04', '5')
    assert mr.split_group('') == ('', '', '')
    assert mr.split_group('1-04') == ('1-04', '', ''), '写不成三段就整串塞进分班, 别乱猜'
    assert mr.safe_name('a/b:c*d?"e') == 'a_b_c_d_e', '连续非法字符合成一个下划线'
    assert mr.safe_name('   ') == '未命名'
    assert mr.safe_name('1.杨氏模量') == '1.杨氏模量', '中文和点不能被改掉'


@case
def test_make_four_formats():
    root = TMP / 'gen'
    for fmt, fname in (('typst', '实验报告.typ'), ('latex', '实验报告.tex'),
                       ('docx', '实验报告.docx'), ('md', '实验报告.md')):
        r = mr.make(_params(输出格式=fmt), root)
        f = Path(r['报告文件'])
        assert f.name == fname and f.is_file() and f.stat().st_size > 0, (fmt, r)
        assert (Path(r['实验目录']) / '实验数据' / '报告参数.json').is_file()
        assert r['实验名称'] == '测量金属的杨氏模量'

    data = root / '测量金属的杨氏模量' / '实验数据'
    typ = (data / '实验报告.typ').read_text(encoding='utf-8')
    assert '#let exp_name = "测量金属的杨氏模量"' in typ, 'typst 报告头没填进去'
    assert '#let student = "张三"' in typ and '#let date = "2026 年 9 月 26 日"' in typ
    assert '今年要求写思考题' in typ, '补充说明要以注释形式带上'
    assert '[实验名称], table.cell(colspan: 3)[#fill(exp_name' in typ, \
        '报告头表格应该引用变量(实验名称跨列, 和统一报告头一致), 而不是写死'

    tex = (data / '实验报告.tex').read_text(encoding='utf-8')
    assert '\\newcommand{\\experiName}{测量金属的杨氏模量}' in tex, 'LaTeX 报告头没填'
    assert '\\newcommand{\\class}{1}' in tex and '\\newcommand{\\group}{04}' in tex
    assert '\\newcommand{\\dateYear}{2026}' in tex
    # 学长那份 main.tex 是写满的成品, 只能取导言区+报告头 —— 正文一句都不许带过来
    body = tex.split('\\begin{document}', 1)[1]
    assert '\\section{实验目的}' in body and '\\section{问题讨论}' in body, '分节骨架要在'
    for leaked in ('磁滞回线', '把大象放进冰箱', '掌握冰箱的使用'):
        assert leaked not in body, f'把学长正文抄进来了: {leaked}'
    assert 'Shing-Ho Lin' in tex, '原作者的署名要留在导言区注释里'

    with zipfile.ZipFile(data / '实验报告.docx') as z:
        assert z.testzip() is None
        doc = z.read('word/document.xml').decode('utf-8')
        assert '测量金属的杨氏模量' in doc and '张三' in doc and '2026 年 9 月 26 日' in doc
        for h in ('实验目的', '仪器用具', '实验原理', '实验内容', '实验数据', '数据处理与结果', '问题讨论'):
            assert h in doc, f'docx 缺分节 {h}'
        core = z.read('docProps/core.xml').decode('utf-8')
        assert '<dc:creator>张三</dc:creator>' in core, '文档属性里的作者要填上'

    md = (data / '实验报告.md').read_text(encoding='utf-8')
    assert '## 实验目的' in md and '测量金属的杨氏模量' in md

    raises(FileExistsError, mr.make, _params(), root)          # 不许无声覆盖
    assert mr.make(_params(), root, force=True)['覆盖已有'] is True


@case
def test_empty_fields_stay_blank():
    r = mr.make({'实验名称': '驻波实验', '输出格式': 'typst', '姓名': '', '指导教师': '',
                 '实验日期': ''}, TMP / 'gen2')
    typ = Path(r['报告文件']).read_text(encoding='utf-8')
    assert '#let student = ""' in typ and '#let date = ""' in typ, '留空就是留空, 不要瞎填'
    assert '#fill(student' in typ, '空的字段在报告里应画成下划线空格'


@case
def test_attachments_dont_pile_up():
    root = TMP / 'gen3'
    src = TMP / 'src'
    src.mkdir(exist_ok=True)
    a, b = src / '数据.csv', src / 'IMG_1.jpg'
    a.write_text('序号,1\n', encoding='utf-8')
    b.write_bytes(b'fake jpeg')
    p = {'实验名称': '驻波实验', '输出格式': 'md', '补充文件': [str(a)], '记录纸照片': [str(b)]}
    r1 = mr.make(p, root)
    assert r1['归档'] == ['补充文件/数据.csv', '照片/IMG_1.jpg'], r1['归档']
    r2 = mr.make(dict(p, 覆盖已有报告=True), root, force=True)
    assert r2['归档'] == r1['归档'], f'同名同内容不该再堆一份: {r2["归档"]}'
    b.write_bytes(b'fake jpeg v2')                      # 改了内容 -> 才允许新增一份
    r3 = mr.make(dict(p), root, force=True)
    assert '照片/IMG_1-2.jpg' in r3['归档'], r3['归档']


def _inject_body(fmt, f):
    """在"正文"的位置塞一个标记, 好验证 --head-only 之后它还在。"""
    if fmt in ('typst', 'md'):
        f.write_text(f.read_text(encoding='utf-8') + '\nBODYMARKER\n', encoding='utf-8')
    elif fmt == 'latex':
        t = f.read_text(encoding='utf-8')
        f.write_text(t.replace('\\end{document}', 'BODYMARKER\n\\end{document}'), encoding='utf-8')
    else:                                            # docx: 直接往 document.xml 里插一个段落
        tmp = f.with_name(f.name + '.tmp')
        with zipfile.ZipFile(f) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'word/document.xml':
                    data = data.replace(b'<w:sectPr>',
                                        b'<w:p><w:r><w:t>BODYMARKER</w:t></w:r></w:p><w:sectPr>')
                zout.writestr(item, data)
        tmp.replace(f)


def _report_text(fmt, f):
    """docx 是压缩包, 得先解出 document.xml 才看得到字。"""
    if fmt == 'docx':
        with zipfile.ZipFile(f) as z:
            return z.read('word/document.xml').decode('utf-8')
    return f.read_text(encoding='utf-8')


@case
def test_head_only_keeps_body():
    """--head-only 存在的唯一理由: 报告头能改, 已经写好的正文一个字都不许动。"""
    root = TMP / 'gen4'
    for fmt, fname in (('typst', '实验报告.typ'), ('latex', '实验报告.tex'),
                       ('md', '实验报告.md'), ('docx', '实验报告.docx')):
        r = mr.make(_params(输出格式=fmt), root)
        f = Path(r['报告文件'])
        assert f.name == fname, r
        _inject_body(fmt, f)                        # 假装正文已经写好了
        r2 = mr.make(_params(输出格式=fmt, 姓名='赵六', 学号='2026K8009900002',
                             分班分组及座号='2-06-7'), root, head_only=True)
        assert r2['只更新报告头'] is True, r2
        assert r2['覆盖已有'] is False, '只改报告头不叫覆盖正文'
        text = _report_text(fmt, f)
        assert 'BODYMARKER' in text, f'{fmt}: 正文被冲掉了'
        assert '赵六' in text, f'{fmt}: 新报告头没写进去'
        assert '张三' not in text, f'{fmt}: 旧报告头还留着'
        if fmt == 'latex':                          # LaTeX 那份把分组拆成三段了
            assert '\\newcommand{\\class}{2}' in text and '\\newcommand{\\group}{06}' in text, fmt
        else:
            assert '2-06-7' in text, f'{fmt}: 分组没更新'
        if fmt == 'typst':                          # 备注块不在报告头范围内, 不许越权删改/堆叠
            assert text.count('今年要求写思考题') == 1, '备注块被重复堆了一份'
        meta = json.loads((f.parent / '报告参数.json').read_text(encoding='utf-8'))
        assert meta['姓名'] == '赵六' and '只更新报告头' in meta['生成方式'], meta

        mr.make(_params(输出格式=fmt, 姓名='赵六'), root, head_only=True)   # 再跑一次要幂等
        text2 = _report_text(fmt, f)
        assert text2.count('BODYMARKER') == 1 and '赵六' in text2, fmt
        if fmt == 'typst':
            assert text2.count('#let exp_name') == 1, '报告头变量被写重复了'

    # 报告还没生成过时, 不许无声地造一份出来
    raises(FileNotFoundError, mr.make, _params(实验名称='还没做过的实验'), TMP / 'gen4',
           head_only=True)


@case
def test_head_only_cli():
    root = TMP / 'gen5'
    base = ['--exp', '驻波实验', '--fmt', 'md', '--root', str(root)]
    rc, out = capture(mr.main, base + ['--name', '张三', '--sid', '2026K8009900001'])
    assert rc == 0 and '生成成功' in out, out
    md_path = root / '驻波实验' / '实验数据' / '实验报告.md'

    rc, out = capture(mr.main, base + ['--name', '李四', '--head-only'])
    assert rc == 0 and '报告头已更新' in out, out
    md = md_path.read_text(encoding='utf-8')
    assert '李四' in md and '张三' not in md and '## 实验目的' in md, md[:300]
    assert '2026K8009900001' in md, '同一个实验的其它字段不该被重生成'

    # 只给要改的那一个字段, 其余必须沿用上次的 报告参数.json, 不许被清空
    rc, out = capture(mr.main, ['--exp', '驻波实验', '--root', str(root),
                                '--date', '2026-09-27', '--head-only'])
    assert rc == 0, out
    md = md_path.read_text(encoding='utf-8')
    assert '2026 年 9 月 27 日' in md and '李四' in md and '2026K8009900001' in md, md[:300]

    # 报告头都认不出来了就得报错, 不能瞎写
    md_path.write_text('# 我自己的报告\n\n随手写的\n', encoding='utf-8')
    rc, out = capture(mr.main, base + ['--name', '王五', '--head-only'])
    assert rc == 1 and '失败' in out, out

    rc, out = capture(mr.main, ['--exp', '另一个实验', '--fmt', 'md', '--root', str(root),
                                '--head-only'])
    assert rc == 1 and '失败' in out, out           # 没有报告可改就该失败, 别静默造一份

    try:                                            # --force 与 --head-only 语义相反, 不许同时给
        capture(mr.main, base + ['--force', '--head-only'])
    except SystemExit as e:
        assert e.code == 2, e.code
    else:
        raise AssertionError('--force 和 --head-only 同时给应该被 argparse 挡下')


@case
def test_appendix_follows_the_report():
    """预习报告/数据记录 : 必填、要归档、要当附录排在报告最后（四种格式各排一次）。"""
    root = TMP / 'gen6'
    src = TMP / 'appx'
    src.mkdir(exist_ok=True)
    pre = src / '预习报告 扫描版.pdf'        # 名字里带空格: 归档时要换成下划线(LaTeX 路径不能有空格)
    rec = src / '数据记录1.jpg'
    other = src / '说明.txt'
    pre.write_bytes(b'%PDF-1.4 fake')
    rec.write_bytes(b'fake jpeg')
    other.write_text('x', encoding='utf-8')
    p = _params(预习报告=[str(pre)], 数据记录=[str(rec), str(other)])
    for fmt in ('typst', 'latex', 'md', 'docx'):
        r = mr.make(dict(p, 输出格式=fmt), root)
        data = Path(r['报告文件']).parent
        assert (data / '预习报告/预习报告_扫描版.pdf').is_file(), '预习报告没归档'
        assert (data / '数据记录/数据记录1.jpg').is_file(), '数据记录没归档'
        assert (data / '数据记录/说明.txt').is_file(), '非图片的附件也要归档'
        text = _report_text(fmt, Path(r['报告文件']))
        flat = text.replace(r'\quad ', '：')      # LaTeX 那份把全角冒号排成了 \quad
        assert '附录 A：预习报告' in flat and '附录 B：数据记录' in flat, f'{fmt}: 附录没排上'
        if fmt == 'typst':
            # 限高: 附录图不能一张吃掉整页(报告总页数要压住)
            assert '#image("数据记录/数据记录1.jpg", height: 44%)' in text, '图片没嵌进附录或没限高'
            assert 'Typst 嵌不进去' in text, 'PDF 在 Typst 里要写明怎么办'
        elif fmt == 'latex':
            assert r'\includepdf[pages=-,fitpaper=true]{预习报告/预习报告_扫描版.pdf}' in text, 'PDF 没排上'
            assert r'\includegraphics[width=\linewidth,height=0.44\textheight,keepaspectratio]' \
                   r'{数据记录/数据记录1.jpg}' in text, '图片没排上或没限高'
            assert text.count(r'\clearpage') == 1, '附录里不该一图一页(那会让页数翻倍)'
            assert text.index(r'\includepdf') < text.index(r'\end{document}'), '附录要在正文之后、末尾之前'
        elif fmt == 'md':
            assert '[附录 A：预习报告（PDF）](预习报告/预习报告_扫描版.pdf)' in text, text[-400:]
            assert '![附录 B：数据记录](数据记录/数据记录1.jpg)' in text, text[-400:]
        else:
            with zipfile.ZipFile(r['报告文件']) as z:
                media = [n for n in z.namelist() if n.startswith('word/media/')]
                assert media == ['word/media/appendix1.jpg'], f'docx 里图片没真嵌进去: {media}'
                doc = z.read('word/document.xml').decode('utf-8')
                assert 'r:embed="rIdImg1"' in doc and 'wp:inline' in doc, 'docx 缺内嵌图片的 XML'
                rels = z.read('word/_rels/document.xml.rels').decode('utf-8')
                assert 'media/appendix1.jpg' in rels, 'docx 缺图片关系'
                assert 'Extension="jpg"' in z.read('[Content_Types].xml').decode('utf-8') \
                    or 'Extension="jpeg"' in z.read('[Content_Types].xml').decode('utf-8'), \
                    'docx 的 Content_Types 没声明图片后缀'
                assert '塞不进去' in doc, 'PDF 附件在 docx 里要写清楚单独交'
    # 没传就不该凭空生出一节空附录（命令行/agent 可能还没拿到这两个文件）
    r = mr.make(_params(), root / 'noappendix')
    assert '附录 A：预习报告' not in Path(r['报告文件']).read_text(encoding='utf-8')


@case
def test_header_is_the_official_one():
    """四种格式都用课程统一报告头: 同字段、同顺序, 含 调课/补课 与 成绩评定。"""
    root = TMP / 'gen7'
    fields = ['实验名称', '指导教师', '姓名', '学号', '分班分组及座号', '实验日期', '实验地点']
    p = _params(调课补课='是', 成绩评定='')
    paths = {fmt: Path(mr.make(dict(p, 输出格式=fmt), root)['报告文件'])
             for fmt in ('typst', 'latex', 'md', 'docx')}
    for fmt, path in paths.items():
        raw = _report_text(fmt, path).replace(r'\quad ', '：')
        # 剥掉注释再比顺序: 导言区/% 实验名称 这类注释里也有字段名, 会把位置搞乱
        flat = '\n'.join(re.sub(r'(%.*|//.*)$', '', ln) for ln in raw.splitlines()) \
            if fmt in ('latex', 'typst') else raw
        for f in fields:
            assert f in flat, f'{fmt} 缺官方字段 {f}'
        assert '调课/补课' in flat and '成绩评定' in flat, f'{fmt} 缺 调课/补课 或 成绩评定'
        pos = [flat.index(f) for f in fields]
        assert pos == sorted(pos), f'{fmt} 的字段顺序和统一报告头不一致: {pos}'
    # 调课/补课 打了勾: LaTeX 往方框里叠对号, Typst 打 ☑, Markdown 打 ☑
    assert r'\newcommand{\others}{$\square$\hspace{-1em}$\surd$}' in _report_text('latex', paths['latex'])
    assert '#let others = "是"' in _report_text('typst', paths['typst'])
    assert '☑ 是' in _report_text('md', paths['md'])
    assert '□ 是' in _report_text('docx', paths['docx']).replace('☑', '□'), 'docx 也该有勾选框'
    # 成绩评定留空也保留这一格(四个格式的字段集要一致)
    assert '成绩评定' in _report_text('md', paths['md'])


@case
def test_ui_server_end_to_end():
    import urllib.request
    import json as _json
    import threading as _threading
    sys.path.insert(0, str(ROOT.parent / 'ui'))
    import server as ui                                  # noqa: E402

    root = TMP / 'uiroot'
    httpd, port = ui.make_server(0, root)
    th = _threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = f'http://127.0.0.1:{port}'

    def call(path, data=None):
        req = urllib.request.Request(base + path, data=data,
                                     headers={'Content-Type': 'application/json'} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, _json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return e.code, _json.loads(e.read().decode('utf-8'))

    try:
        st, cfg = call('/api/config')
        assert st == 200 and len(cfg['experiments']) >= 15, cfg
        assert all('tool_ok' in f for f in cfg['formats']), cfg['formats']

        st, up = call('/api/upload?name=' + urllib.parse.quote('照片 1.jpg'), b'fake')
        assert st == 200 and up['name'] == '照片 1.jpg', up
        _st, up_pre = call('/api/upload?name=' + urllib.parse.quote('预习报告.pdf'), b'%PDF-1.4')
        _st, up_rec = call('/api/upload?name=' + urllib.parse.quote('数据记录.jpg'), b'fake jpeg')

        # 预习报告 / 数据记录 是必填项: 没传就得挡下来（不能生成一份没附录的报告）
        st, miss = call('/api/generate', _json.dumps({
            '实验名称': '测量金属的杨氏模量', '输出格式': 'md', '实验目录': str(root),
        }).encode('utf-8'))
        assert st == 400 and '必填' in _json.dumps(miss, ensure_ascii=False), miss

        body = _json.dumps({
            '实验名称': '测量金属的杨氏模量', '输出格式': 'md', '姓名': '张三',
            '实验目录': str(root), '记录纸照片': [up], '补充文件': [],
            '预习报告': [up_pre], '数据记录': [up_rec],
        }).encode('utf-8')
        st, gen = call('/api/generate', body)
        assert st == 200 and gen['ok'], gen
        rep = Path(gen['报告文件'])
        assert rep.is_file() and (rep.parent / '照片/照片 1.jpg').is_file(), gen
        assert (rep.parent / '预习报告/预习报告.pdf').is_file(), '附录 A 的文件没归档'
        assert (rep.parent / '数据记录/数据记录.jpg').is_file(), '附录 B 的文件没归档'
        assert '## 附录 A：预习报告' in rep.read_text(encoding='utf-8')
        assert not (rep.parent / '.上传暂存').exists(), '上传暂存要清干净'
        # 生成完要给一段可直接粘给 agent 的话（路径写全，省得它再问）
        talk = gen['给agent的话']
        assert str(rep.parent) in talk and '报告参数.json' in talk, talk
        assert '§1' in talk and 'TODO' in talk and '照片' in talk, talk

        st, again = call('/api/generate', body)
        assert st == 400 and '已存在' in _json.dumps(again, ensure_ascii=False), again

        # 勾了"只更新报告头": 正文不动, 报告头换成新的
        rep.write_text(rep.read_text(encoding='utf-8') + '\nBODYMARKER\n', encoding='utf-8')
        p2 = {'实验名称': '测量金属的杨氏模量', '输出格式': 'md', '姓名': '赵六',
              '实验目录': str(root), '记录纸照片': [up], '补充文件': [],
              '预习报告': [up_pre], '数据记录': [up_rec], '只更新报告头': True}
        st, upd = call('/api/generate', _json.dumps(p2).encode('utf-8'))
        assert st == 200 and upd['只更新报告头'] is True, upd
        t = rep.read_text(encoding='utf-8')
        assert 'BODYMARKER' in t and '赵六' in t and '张三' not in t, t[:200]
        assert '正文别动' in upd['给agent的话'], upd['给agent的话']

        st, bad = call('/api/generate', _json.dumps({'实验名称': '', '输出格式': 'md',
                                                     '实验目录': str(root)}).encode('utf-8'))
        assert st == 400, bad
    finally:
        httpd.shutdown()
        httpd.server_close()


def main():
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    bad = 0
    try:
        for fn in CASES:
            try:
                fn()
                print(f'  PASS  {fn.__name__}')
            except Exception as e:
                bad += 1
                print(f'  FAIL  {fn.__name__}: {type(e).__name__}: {e}')
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f'\n{len(CASES) - bad}/{len(CASES)} 通过')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
