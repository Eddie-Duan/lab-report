# -*- coding: utf-8 -*-
"""读/写带分段标记的原始数据 CSV。

约定（照抄记录纸，不做任何单位换算）:

    # 任意注释行, 以 # 开头
    # ---- 横梁的几何尺寸 ----        <- 分段标记, 名字随意
    测量次数,1,2,3,4,5,6              <- 该段第一行是表头
    长度d/cm,23.60,23.55,23.57,...
    宽度b/mm,22.16,22.80,...

    # ---- 读数显微镜示数 ----
    序号,1,2,3,4,5,6,7,8
    Mi/g,19.9,40.0,60.5,...
    Zi,01.9,16.5,29.4,...

一行里某个格子留空表示记录纸上没有这个数（读出来是 None），不要填 0。

作为模块用:
    import sys; sys.path.insert(0, r'<skill>/scripts')
    import csv_tables as ct
    t = ct.load('2_霍尔法.csv')
    ct.row(t['横梁的几何尺寸'], '宽度b')   # -> [22.16, 22.8, 22.02, 22.0, 23.04, 22.74]

命令行用（检查一个 CSV 能不能正确解析）:
    python csv_tables.py 2_霍尔法.csv
"""
import sys
from pathlib import Path

RAW = b'\xef\xbb\xbf'


def load(path):
    """返回 {段名: (表头 list, 数据行 list[list[str]])}"""
    data = Path(path).read_bytes()
    if not data.startswith(RAW):
        print(f'警告: {path} 没有 BOM, Excel 打开可能乱码; 跑一下 to_utf8.py')

    out = {}
    name = None
    for raw in data.decode('utf-8-sig').splitlines():
        line = raw.strip()
        if line.startswith('# ----'):
            name = line.strip('# -').strip()
            out[name] = (None, [])
        elif line and not line.startswith('#'):
            if name is None:
                raise ValueError(f'{path}: 有一行不在 "# ---- 分段 ----" 之内: {line}')
            header, rows = out[name]
            if header is None:
                out[name] = (line.split(','), rows)
            else:
                rows.append([c.strip() for c in line.split(',')])
    return out


def row(table, prefix):
    """按首列标签取一行, 返回 float 列表。空格子 -> None。"""
    _, rows = table
    for r in rows:
        if r[0].startswith(prefix):
            vals = []
            for c in r[1:]:
                try:
                    vals.append(float(c))
                except ValueError:
                    vals.append(None)
            return vals
    raise KeyError(f'{prefix} 没找到; 该段的行标签有: {[r[0] for r in rows]}')


def col(table, i):
    """按列号取一列(0 起, 不含标签列), 返回 float 列表。"""
    _, rows = table
    vals = []
    for r in rows:
        try:
            vals.append(float(r[i + 1]))
        except (IndexError, ValueError):
            vals.append(None)
    return vals


def write(path, sections, comments=()):
    """写一个符合约定的 CSV（UTF-8 with BOM + CRLF）。

    sections: [('段名', [表头list, 行list, ...]), ...]
    """
    parts = [f'# {c}' for c in comments]
    if comments:
        parts.append('#')
    for name, rows in sections:
        parts.append(f'# ---- {name} ----')
        for r in rows:
            parts.append(','.join('' if v is None else str(v) for v in r))
    Path(path).write_bytes(RAW + ('\r\n'.join(parts) + '\r\n').encode('utf-8'))
    return path


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    for p in argv:
        print(f'===== {p} =====')
        try:
            tabs = load(p)
        except Exception as e:
            print(f'  读失败: {e}')
            continue
        for name, (header, rows) in tabs.items():
            print(f'  [{name}]  表头 {header}')
            for r in rows:
                print(f'      {r}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
