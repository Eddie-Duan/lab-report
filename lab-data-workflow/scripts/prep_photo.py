# -*- coding: utf-8 -*-
"""把实验记录纸照片切成能看清字的小块。

手写照片直接整张读会糊，尤其是表格里的数字。先出总览图看版面，再按需要切半、
转正、放大某个区域。区域坐标用手写笔在总览图上量，单位是原图像素。

用法:
    python prep_photo.py 图片.jpg                          # 总览图(长边缩到 1200)
    python prep_photo.py 图片.jpg --rotate -90             # 转正; 顺时针 90 用 -90
    python prep_photo.py 图片.jpg --rotate -90 --split      # 转正后切上下两半
    python prep_photo.py 图片.jpg --crop 300,1600,1800,1900 --zoom 2.5
    python prep_photo.py 图片.jpg --region 表头             # 补光+二值化, 字迹淡时试

输出统一写到 图片.jpg 同目录的 _prep/ 下，文件名带参数后缀。
"""
import sys
import argparse
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter


def overview(im, max_side=1200):
    o = im.copy()
    o.thumbnail((max_side, max_side), Image.LANCZOS)
    return o


def halves(im, overlap=0.06):
    """切上下两半, 中间留一点重叠, 避免正好把一行字切开。"""
    W, H = im.size
    mid = int(H / 2)
    ov = int(H * overlap)
    return [('top', im.crop((0, 0, W, min(H, mid + ov)))),
            ('bot', im.crop((0, max(0, mid - ov), W, H)))]


def autolevel(im, radius=40):
    """补光: 除背景, 抬字迹对比度。照片偏暗/偏黄时用。"""
    gray = im.convert('L')
    bg = gray.filter(ImageFilter.GaussianBlur(radius))
    out = ImageOps.autocontrast(ImageOps.invert(bg).point(lambda v: v))
    return Image.blend(gray, out, 0.55)


def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('image')
    ap.add_argument('--rotate', type=int, default=0,
                    help='逆时针转多少度(90/180/270 的倍数); 顺时针 90 用 -90')
    ap.add_argument('--split', action='store_true', help='切上下两半')
    ap.add_argument('--crop', help='x0,y0,x1,y1 原图像素')
    ap.add_argument('--zoom', type=float, default=1.0, help='裁切后放大倍数')
    ap.add_argument('--region', choices=['', 'autolevel'], default='',
                    help='autolevel: 补光提对比度(字迹淡时试)')
    ap.add_argument('--max-side', type=int, default=1600)
    a = ap.parse_args(argv)

    src = Path(a.image)
    if not src.is_file():
        print(f'找不到 {src}')
        return 1
    out = src.parent / '_prep'
    out.mkdir(exist_ok=True)
    stem = src.stem[:20]

    im = Image.open(src)
    if im.mode != 'RGB':
        im = im.convert('RGB')
    if a.rotate:
        im = im.rotate(a.rotate, expand=True)
    if a.region == 'autolevel':
        im = autolevel(im)

    jobs = []
    if a.crop:
        try:
            x0, y0, x1, y1 = (int(v) for v in a.crop.split(','))
        except ValueError:
            print('--crop 需要 x0,y0,x1,y1 四个整数')
            return 1
        box = (max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1))
        if box[2] <= box[0] or box[3] <= box[1]:
            print(f'裁切区域超出图片范围 {im.size}')
            return 1
        jobs.append(('crop', im.crop(box), a.zoom))
    elif a.split:
        for name, piece in halves(im):
            jobs.append((name, piece, 1.0))
    else:
        jobs.append(('overview', im, 1.0))

    tag = ''.join(c for c in
                  (f'_r{a.rotate}' if a.rotate else '')
                  + ('_al' if a.region else '')
                  + (f'_x{a.zoom:g}' if a.crop else '') if c not in ' ')

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

    print(f'{im.size[0]}x{im.size[1]} -> {out}')
    for dst, size in made:
        print(f'  {dst.name}  {size[0]}x{size[1]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
