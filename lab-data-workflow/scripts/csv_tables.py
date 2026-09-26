# -*- coding: utf-8 -*-
"""读/写带分段标记的原始数据 CSV。

约定（照抄记录纸，不做任何单位换算）:

    # 任意注释行, 以 # 开头
    # ---- 横梁的几何尺寸 ----        <- 分段标记, 名字随意; 同名分段会报错, 不静默覆盖
    测量次数,1,2,3,4,5,6              <- 该段第一行是表头
    长度d/cm,23.60,23.55,23.57,...
    宽度b/mm,22.16,22.80,...

    # ---- 读数显微镜示数 ----
    序号,1,2,3,4,5,6,7,8
    Mi/g,19.9,40.0,60.5,...
    Zi,01.9,16.5,29.4,...

一行里某个格子留空表示记录纸上没有这个数（读出来是 None），不要填 0。

**只写字符串**：write() 拒绝 float 和 bool。原始读数本来就该是 '23.60' 这样的字符串 ——
传 float 会丢有效位(23.60 -> 23.6)，传算式会写出浮点误差(0.1+0.2 -> 0.30000000000000004)，
而 §1.3 的纪律是 CSV 里只有记录纸上的原值。

读的时候也**不吞错**：格子空着 -> None；格子有东西但读不成数字 -> 直接报错（那是写错或读错
的值，不能和"记录纸上没有"混为一谈）。行列数对不上也会报错/警告，不会静默截断。

作为模块用:
    import sys; sys.path.insert(0, r'<skill>/scripts')
    import csv_tables as ct
    t = ct.load('2_霍尔法.csv')
    ct.row(t['横梁的几何尺寸'], '宽度b')   # -> [22.16, 22.8, 22.02, 22.0, 23.04, 22.74]

命令行用（检查一个 CSV 能不能正确解析）:
    python csv_tables.py 2_霍尔法.csv        # 有问题时退出码 1
"""
import re
import sys
from pathlib import Path

RAW = b'\xef\xbb\xbf'
MARK = re.compile(r'^#\s*-{2,}\s*(?P<name>.*?)\s*-{2,}\s*$')

if not sys.stdout.isatty():          # 被管道或 agent 捕获时按 UTF-8 输出, 免得中文变 ���
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _decode(raw: bytes, path) -> str:
    if raw.startswith(RAW):
        raw = raw[len(RAW):]
    elif not raw.isascii():
        print(f'警告: {path} 没有 BOM, Excel 打开可能乱码; 跑一下 to_utf8.py')
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError as e:
        try:
            raw.decode('gb18030')
            hint = '是 GBK/ANSI'
        except UnicodeDecodeError:
            hint = '编码无法识别'
        raise ValueError(f'{path}: {hint}, 不是 UTF-8。先跑 to_utf8.py {path}') from e


def load(path):
    """返回 {段名: (表头 list, 数据行 list[list[str]])}。

    分段名重复 / 某行比表头列多 / 编码不是 UTF-8 -> ValueError。
    某行比表头列少 -> 按末尾空格子补齐, 并打印带行号的警告（不补齐会让 zip 静默截断）。
    """
    text = _decode(Path(path).read_bytes(), path)
    out = {}
    name = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = MARK.match(line)
        if m:
            name = m.group('name').strip()
            if not name:
                raise ValueError(f'{path}:{lineno} 分段标记没有名字: {line}')
            if name in out:
                raise ValueError(f'{path}:{lineno} 分段名重复: {name!r} '
                                 f'(后一段会把前一段整段盖掉, 请改成两个不同的名字)')
            out[name] = (None, [])
        elif line and not line.startswith('#'):
            if name is None:
                raise ValueError(f'{path}:{lineno} 有一行不在 "# ---- 分段 ----" 之内: {line}')
            header, rows = out[name]
            cells = [c.strip() for c in line.split(',')]
            if header is None:
                out[name] = (cells, rows)
                continue
            if len(cells) > len(header):
                raise ValueError(f'{path}:{lineno} 这行 {len(cells)} 列, 表头只有 {len(header)} 列'
                                 f'(值里是不是有逗号?): {line}')
            if len(cells) < len(header):
                print(f'警告: {path}:{lineno} 这行只有 {len(cells)} 列, 表头 {len(header)} 列, '
                      f'末尾按空格子补齐: {line}')
                cells += [''] * (len(header) - len(cells))
            rows.append(cells)
    return out


def _pick(rows, prefix, strict, what):
    """先按整段标签精确匹配, 再退回前缀匹配。多命中就报错, 不要猜。"""
    hits = [r for r in rows if r[0] == prefix] or [r for r in rows if r[0].startswith(prefix)]
    if not hits:
        raise KeyError(f'{prefix} 没找到; 该段的行标签有: {[r[0] for r in rows]}')
    if len(hits) > 1:
        if strict:
            raise ValueError(f'{prefix} 命中多行: {[r[0] for r in hits]}; '
                             f'{what}请写全标签, 或用 strict=False 明确接受第一个')
        hits = hits[:1]
    return hits[0]


def _num(label, cell, strict):
    if cell == '':
        return None
    try:
        return float(cell)
    except ValueError:
        if strict:
            raise ValueError(f'{label} 的格子 {cell!r} 读不成数字 —— '
                             f'是读错/写错的值吗? 记录纸上没有的话请留空') from None
        return None


def row(table, prefix, strict=True):
    """按首列标签取一行, 返回 float 列表。空格子 -> None。

    strict=True（默认）: 标签多命中时报错; 非空但读不成数字的格子也报错。
    """
    _, rows = table
    r = _pick(rows, prefix, strict, 'row() ')
    return [_num(r[0], c, strict) for c in r[1:]]


def col(table, i, strict=True):
    """按列号取一列(0 起, 不含标签列), 返回 float 列表。"""
    _, rows = table
    return [_num(r[0] if r else f'第{i + 1}列', r[i + 1] if i + 1 < len(r) else '', strict)
            for r in rows]


def _cell(v, where):
    if v is None:
        return ''
    if isinstance(v, bool):
        raise ValueError(f'{where}: 别写 bool ({v!r}), 原始数据只收字符串或整数')
    if isinstance(v, float):
        raise ValueError(f'{where}: 别写 float ({v!r}) —— 23.60 会写成 23.6, 0.1+0.2 会写成 '
                         f"0.30000000000000004。请传字符串如 '23.60'")
    s = v if isinstance(v, str) else str(v)
    if any(ch in s for ch in ',\r\n'):
        raise ValueError(f'{where}: {s!r} 里有逗号或换行, 会写坏 CSV')
    if s.startswith('#'):
        raise ValueError(f'{where}: {s!r} 以 # 开头, 读回来会被当成注释')
    return s


def write(path, sections, comments=()):
    """写一个符合约定的 CSV（UTF-8 with BOM + CRLF）。

    sections: [('段名', [表头list, 行list, ...]), ...]
    列数与表头不一致、值里有逗号/换行、值传了 float -> ValueError，不写出半成品。
    """
    parts = []
    for c in comments:
        for ln in str(c).splitlines() or ['']:
            parts.append(f'# {ln}'.rstrip())
    if comments:
        parts.append('#')
    for name, rows in sections:
        if not name or '----' in name or '\n' in name:
            raise ValueError(f'段名不合法: {name!r} (不能为空/含 ----/含换行)')
        if not rows:
            raise ValueError(f'分段 {name!r} 没有内容')
        parts.append(f'# ---- {name} ----')
        n = len(rows[0])
        for i, r in enumerate(rows):
            if len(r) != n:
                raise ValueError(f'分段 {name!r} 第 {i + 1} 行 {len(r)} 列, 表头 {n} 列: {r}')
            parts.append(','.join(_cell(v, f'{name} 第 {i + 1} 行第 {j + 1} 列')
                                  for j, v in enumerate(r)))
    Path(path).write_bytes(RAW + ('\r\n'.join(parts) + '\r\n').encode('utf-8'))
    return path


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    bad = 0
    for p in argv:
        print(f'===== {p} =====')
        try:
            tabs = load(p)
        except Exception as e:
            print(f'  读失败: {e}')
            bad += 1
            continue
        for name, (header, rows) in tabs.items():
            print(f'  [{name}]  {len(rows)} 行  表头 {header}')
            for r in rows:
                print(f'      {r}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
