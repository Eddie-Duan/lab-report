# -*- coding: utf-8 -*-
"""Excel 中文版另存 CSV 默认是 GBK/ANSI，其它工具打开就是乱码。本脚本转成 UTF-8 with BOM。

用法:
    python to_utf8.py 文件或目录 [...]          就地转换, 原文件备份为 *.gbk.bak
    python to_utf8.py --check 文件或目录 [...]  只报告编码, 一个字都不改（dry-run）
    python to_utf8.py --clean 文件或目录 [...]  删除上次留下的 *.gbk.bak
    python to_utf8.py --assume gbk 文件          碰上有歧义的字节时按 GBK 处理

--check 和 --clean 放哪个位置都行。--check 查到"需要转"或"要人看一眼"时退出码是 1，
可以直接当闸门用（if python to_utf8.py --check 数据目录; then ...）。

某种字节串既可以读成 UTF-8 也可以读成 GBK 时（GBK 偶尔会撞上合法 UTF-8 序列），脚本**不猜**：
打印两种读法让人确认，确认后加 --assume gbk / --assume utf8 重跑。认不准就问，跟 §1.2 一个道理。

转换后再用 Excel 打开不会乱码(BOM 让 Excel 认出 UTF-8)；Python 读用 encoding='utf-8-sig'。
转完会打印前两行内容 —— 瞄一眼有没有变成乱码，一眼就能看出来。
"""
import sys
import re
import argparse
import shutil
from pathlib import Path

BOM = b'\xef\xbb\xbf'
BACKUP = '.gbk.bak'
CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')

if not sys.stdout.isatty():          # 被管道或 agent 捕获时按 UTF-8 输出, 免得中文变 ���
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _decodable(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def sniff(raw: bytes) -> str:
    """返回 'utf-8-bom' / 'ascii' / 'utf-8' / 'gbk' / 'gbk?' / 'unknown'。

    带 BOM、纯 ASCII、只解得出一种, 都没歧义。麻烦的是两种都解得出 —— UTF-8 的中文字节
    几乎总能按 GB18030 解出(只是变成生僻字), 所以这本身不算疑点, 一律按 UTF-8 处理。
    真正的疑点是反过来: 按 UTF-8 解出来一个汉字都没有, 按 GBK 解却全是汉字, 例如
    '一' 的 GBK 字节 D2 BB 恰好是合法 UTF-8(解成西里尔字母 'һ')。这种标成 'gbk?'，
    脚本**不会自动转**, 要人确认后加 --assume gbk/utf8。
    """
    if raw.startswith(BOM):
        return 'utf-8-bom' if _decodable(raw[len(BOM):], 'utf-8') else 'unknown'
    if raw.isascii():
        return 'ascii'
    utf8_ok = _decodable(raw, 'utf-8')
    gbk_ok = _decodable(raw, 'gb18030')
    if utf8_ok:
        if gbk_ok and not CJK.search(raw.decode('utf-8')) and CJK.search(raw.decode('gb18030')):
            return 'gbk?'
        return 'utf-8'
    return 'gbk' if gbk_ok else 'unknown'


OK_KINDS = ('utf-8-bom', 'ascii')


def targets(paths):
    """展开成待处理文件列表。目录取其中的 *.csv, 明确点名的文件原样收下。"""
    out = []
    for p in paths:
        q = Path(p)
        if q.is_dir():
            out += sorted(x for x in q.rglob('*.csv') if not x.name.endswith(BACKUP))
        elif q.is_file():
            out.append(q)
        else:
            print(f'跳过(不存在): {p}')
    return out


def preview(raw: bytes, kind: str, lines=2) -> str:
    """转出来长什么样, 打两行给眼睛看。"""
    text = raw.decode('gb18030' if kind == 'gbk' else 'utf-8', 'replace')
    got = [ln.strip() for ln in text.splitlines() if ln.strip()][:lines]
    return ' | '.join(ln[:60] for ln in got)


def clean(paths) -> int:
    """删掉 *.gbk.bak。按后缀全盘找, 不依赖对应的 csv 还在不在。"""
    n = 0
    for p in paths:
        q = Path(p)
        if q.is_dir():
            baks = sorted(q.rglob('*' + BACKUP))
        elif q.name.endswith(BACKUP) and q.is_file():
            baks = [q]
        elif q.is_file():
            baks = sorted(q.parent.glob(q.name + BACKUP))
        else:
            print(f'跳过(不存在): {p}')
            continue
        for b in baks:
            b.unlink()
            print(f'删除备份 {b}')
            n += 1
    print(f'\n共删除 {n} 个备份')
    return 0


def main(argv):
    ap = argparse.ArgumentParser(
        description='GBK/ANSI 的 CSV 转成 UTF-8 with BOM',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='*', help='文件或目录(目录会递归找 *.csv)')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='只报告编码, 不改动(dry-run)')
    mode.add_argument('--clean', action='store_true', help='删除 *.gbk.bak 备份')
    ap.add_argument('--assume', choices=['utf8', 'gbk'], default=None,
                    help='碰上"既像 UTF-8 又像 GBK"的文件时按哪种处理(默认不动, 要人确认)')
    a = ap.parse_args(argv)

    if not a.paths:
        print(__doc__)
        return 1
    if a.clean:
        return clean(a.paths)

    files = targets(a.paths)
    need = bad = 0
    for f in files:
        if f.name.endswith(BACKUP):
            continue
        raw = f.read_bytes()
        kind = sniff(raw)

        if kind == 'unknown':
            print(f'{f}  编码无法识别, 跳过')
            bad += 1
            continue
        if kind == 'gbk?' and not a.assume:
            print(f'{f}  两种读法都通: 按 UTF-8 是 {preview(raw, "utf-8")!r}, '
                  f'按 GBK 是 {preview(raw, "gbk")!r}')
            print('    -> 认不准就不猜。确认后加 --assume gbk 或 --assume utf8 重跑')
            bad += 1
            continue
        if kind == 'gbk?' and a.assume:
            kind = 'gbk' if a.assume == 'gbk' else 'utf-8'
        if kind in OK_KINDS:
            if a.check:
                print(f'{kind:10s} {f}')
            else:
                print(f'{f}  已是 {kind}, 跳过')
            continue

        need += 1
        if a.check:
            print(f'{kind:10s} {f}  <-- 需要转')
            continue

        bak = Path(str(f) + BACKUP)
        if bak.exists():
            print(f'{f}  已有备份 {bak.name}, 保留不动')
        else:
            shutil.copy2(f, bak)
        body = BOM + raw if kind == 'utf-8' else BOM + raw.decode('gb18030').encode('utf-8')
        f.write_bytes(body)
        print(f'{f}  {kind} -> UTF-8 with BOM  备份 {bak.name}')
        print(f'  转出来长这样: {preview(body, "utf-8")}')

    if a.check:
        print(f'\n{len(files)} 个文件, {need} 个需要转换, {bad} 个要人看一眼')
        return 1 if (need or bad) else 0
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
