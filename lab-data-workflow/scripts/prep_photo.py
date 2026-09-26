# -*- coding: utf-8 -*-
"""把实验记录纸照片切成能看清字的小块。

手写照片直接整张读会糊，尤其是表格里的数字。先出总览图看版面，再按需要切半、
转正、放大某个区域。区域坐标在总览图上量，用 `--coord overview` 自动换算成原图坐标。

用法:
    python prep_photo.py 图片.jpg                                  # 总览图(长边缩到 --max-side)
    python prep_photo.py 图片.jpg --rotate -90                      # 转正; 逆时针 90 用 90
    python prep_photo.py 图片.jpg --rotate -90 --split               # 转正后切上下两半
    python prep_photo.py 图片.jpg --crop 330,1600,1760,1850 --coord overview --zoom 1.6
    python prep_photo.py 图片.jpg --crop 0.11,0.53,0.59,0.62 --coord rel --zoom 1.6
    python prep_photo.py 图片.jpg --region autolevel                 # 去背景+提对比度(字迹淡时试)

坐标一律按**转正、补光之后**的图算。--coord 三种取法:
    orig      原图(转正后)像素 —— 默认
    overview  总览图像素。总览 = 原图长边缩到 --max-side 的那张, 脚本会打印缩放比
    rel       0~1 的相对比例, 跟分辨率无关, 最不容易搞错

读不出来、或者坐标被裁到图外时, 脚本会明确警告 —— 不要忽略, 那通常意味着读错了数字。
输出写到 图片.jpg 同目录的 _prep/ 下, 文件名带参数后缀(含裁切区域, 不同裁切不会互相覆盖)。
"""
import sys
import argparse
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter

try:
    import numpy as np
except ImportError:      # 只有 autolevel 的除背景要用; 没有就退化成全局对比度拉伸
    np = None

if not sys.stdout.isatty():          # 被管道或 agent 捕获时按 UTF-8 输出, 免得中文变 ���
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def overview(im, max_side=1600):
    o = im.copy()
    o.thumbnail((max_side, max_side), Image.LANCZOS)
    return o


def overview_scale(size, max_side):
    """总览图 = 原图 * 这个比例(thumbnail 只缩不放)。"""
    return min(1.0, max_side / max(size))


def halves(im, overlap=0.06):
    """切上下两半, 中间留一点重叠, 避免正好把一行字切开。"""
    W, H = im.size
    mid = int(H / 2)
    ov = int(H * overlap)
    return [('top', im.crop((0, 0, W, min(H, mid + ov)))),
            ('bot', im.crop((0, max(0, mid - ov), W, H)))]


def autolevel(im, radius=40):
    """去背景 + 提对比度: 大半径模糊估出背景, 逐像素除以背景, 再拉伸色阶。返回灰度图。

    照片偏暗/偏黄/纸面光照不匀时用。**不要**写成 invert(bg) 再叠加 —— 那是把背景反相后
    相加, 纸会被压到深灰、字反而比纸亮, 得到一张负片, 对比度更差。
    """
    gray = im.convert('L')
    bg = gray.filter(ImageFilter.GaussianBlur(radius))
    if np is not None:
        a = np.asarray(gray, dtype=np.float32)
        b = np.asarray(bg, dtype=np.float32)
        gray = Image.fromarray(np.clip(a / np.maximum(b, 1.0) * 235.0, 0, 255).astype('uint8'))
    return ImageOps.autocontrast(gray, cutoff=1)


def parse_box(spec, coord, size, max_side):
    """把 --crop 的四个数按 --coord 语义换算成原图(转正后)像素的整数 box。"""
    try:
        vals = [float(v) for v in spec.split(',')]
    except ValueError:
        raise ValueError('--crop 需要 x0,y0,x1,y1 四个数, 每个都可以带小数') from None
    if len(vals) != 4:
        raise ValueError(f'--crop 需要 x0,y0,x1,y1 四个数, 现在给了 {len(vals)} 个')
    W, H = size
    if coord == 'rel':
        if not all(0.0 <= v <= 1.0 for v in vals):
            raise ValueError('--coord rel 的四个数都要落在 0~1 之间')
        box = [vals[0] * W, vals[1] * H, vals[2] * W, vals[3] * H]
    elif coord == 'overview':
        f = overview_scale(size, max_side)
        box = [v / f for v in vals]
    else:
        box = list(vals)
    box = [int(round(v)) for v in box]
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f'裁切区域是空的: {tuple(box)}')
    used = (max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3]))
    if list(used) != box:
        print(f'警告: 裁切区域 {tuple(box)} 超出图片 {W}x{H}, 实际只裁了 {used}'
              f'  <- 坐标量错了吗? 在总览上量的请加 --coord overview')
    if used[2] <= used[0] or used[3] <= used[1]:
        raise ValueError(f'裁切区域完全在图片外: {tuple(box)}, 图片 {W}x{H}')
    return used


def make_tag(a, box):
    """文件名后缀: 含裁切区域, 免得两次不同裁切写同一个名字互相覆盖。"""
    tag = ''
    if a.rotate:
        tag += f'_r{a.rotate}'
    if a.region:
        tag += '_al'
    if box is not None:
        tag += '_c' + '-'.join(str(v) for v in box)
        if a.zoom != 1.0:
            tag += f'_x{a.zoom:g}'
    return tag


def main(argv):
    ap = argparse.ArgumentParser(add_help=True, description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('--rotate', type=int, default=0,
                    help='逆时针转多少度, 只支持 90 的倍数(顺时针 90 用 -90)')
    what = ap.add_mutually_exclusive_group()
    what.add_argument('--split', action='store_true', help='切上下两半')
    what.add_argument('--crop', help='x0,y0,x1,y1; 单位由 --coord 决定')
    ap.add_argument('--coord', choices=['orig', 'overview', 'rel'], default='orig',
                    help='--crop 的坐标是在哪张图上量的(默认 orig)')
    ap.add_argument('--zoom', type=float, default=1.0, help='裁切后放大倍数(只对 --crop 有效)')
    ap.add_argument('--region', choices=['', 'autolevel'], default='',
                    help='autolevel: 去背景+提对比度(字迹淡/照片发灰时试)')
    ap.add_argument('--max-side', type=int, default=1600,
                    help='总览图长边上限(默认 1600); 放大图长边上限是它的 2 倍')
    a = ap.parse_args(argv)

    if a.rotate % 90:
        ap.error('--rotate 只支持 90 的倍数(90/180/270/-90...)')
    if a.zoom != 1.0 and not a.crop:
        print('警告: --zoom 只在 --crop 时生效, 这次忽略了')

    src = Path(a.image)
    if not src.is_file():
        print(f'找不到 {src}')
        return 1
    try:
        im = Image.open(src)
        im.load()
    except Exception as e:
        print(f'打不开 {src}: {type(e).__name__}: {e}')
        return 1

    ori = im.getexif().get(274, 1)
    im = ImageOps.exif_transpose(im) or im      # 手机竖拍的照片靠这个才是正的
    if im.mode != 'RGB':
        im = im.convert('RGB')
    if ori != 1:
        print(f'已按 EXIF 方向(274={ori})转正, 尺寸 {im.size[0]}x{im.size[1]}')
    if a.rotate:
        im = im.rotate(a.rotate, expand=True, fillcolor='white')
    if a.region == 'autolevel':
        im = autolevel(im)

    box = None
    jobs = []
    if a.crop:
        try:
            box = parse_box(a.crop, a.coord, im.size, a.max_side)
        except ValueError as e:
            print(f'--crop 有错: {e}')
            return 1
        jobs.append(('crop', im.crop(box), a.zoom))
    elif a.split:
        for name, piece in halves(im):
            jobs.append((name, piece, 1.0))
    else:
        jobs.append(('overview', im, 1.0))

    out = src.parent / '_prep'
    out.mkdir(exist_ok=True)
    stem = src.stem[:20]
    tag = make_tag(a, box)

    made = []
    for name, piece, scale in jobs:
        if name == 'overview':
            piece = overview(piece, a.max_side)
        else:
            w, h = piece.size
            s = min(scale, a.max_side * 2 / max(w, h))
            piece = piece.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
        dst = out / f'{stem}{tag}_{name}.jpg'
        piece.save(dst, quality=94)
        made.append((dst, piece.size))

    W, H = im.size
    f = overview_scale(im.size, a.max_side)
    print(f'{src.name}: {W}x{H} -> {out}')
    if f < 1.0:
        print(f'  总览 {round(W * f)}x{round(H * f)} = 原图 x{f:.3f};'
              f' 在总览上量的坐标 x{1 / f:.3f} 才是原图坐标, 或直接加 --coord overview')
    if box is not None:
        print(f'  裁切区域(原图坐标) {box}  {box[2] - box[0]}x{box[3] - box[1]}')
    for dst, size in made:
        print(f'  {dst.name}  {size[0]}x{size[1]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
