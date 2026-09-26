# -*- coding: utf-8 -*-
"""三个脚本的回归自测。改完脚本跑一遍，全绿再提交。

    python selftest.py

不依赖 pytest，只用标准库。临时文件建在**当前目录**的 .selftest_tmp/ 下，跑完删掉
（不用系统临时目录：Windows 上那个目录常被策略挡住，写不进去）。
"""
import io
import shutil
import sys
import contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import csv_tables as ct      # noqa: E402
import to_utf8 as tu         # noqa: E402
import prep_photo as pp      # noqa: E402
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
