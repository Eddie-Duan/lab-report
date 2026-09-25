# -*- coding: utf-8 -*-
"""Excel 中文版另存 CSV 默认是 GBK/ANSI，其它工具打开就是乱码。本脚本转成 UTF-8 with BOM。

用法:
    python to_utf8.py 文件或目录 [...]          就地转换, 原文件备份为 *.gbk.bak
    python to_utf8.py --check 文件或目录 [...]  只报告编码, 不改动
    python to_utf8.py --clean 文件或目录 [...]  删除上次留下的 *.gbk.bak

转换后再用 Excel 打开不会乱码(BOM 让 Excel 认出 UTF-8)；Python 读用 encoding='utf-8-sig'。
"""
import sys
import shutil
from pathlib import Path

BOM = b'\xef\xbb\xbf'


def sniff(raw: bytes) -> str:
    """返回 'utf-8-bom' / 'utf-8' / 'gbk' / 'unknown'"""
    if raw.startswith(BOM):
        try:
            raw[3:].decode('utf-8')
            return 'utf-8-bom'
        except UnicodeDecodeError:
            return 'unknown'
    try:
        raw.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass
    try:
        raw.decode('gb18030')
        return 'gbk'
    except UnicodeDecodeError:
        return 'unknown'


def targets(paths):
    out = []
    for p in paths:
        q = Path(p)
        if q.is_dir():
            out += sorted(q.rglob('*.csv'))
        elif q.is_file():
            out.append(q)
        else:
            print(f'跳过(不存在): {p}')
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    mode = 'convert'
    if argv[0] in ('--check', '--clean'):
        mode = argv.pop(0)[2:]

    bad = 0
    for f in targets(argv):
        if f.suffix == '.bak':
            continue
        raw = f.read_bytes()
        kind = sniff(raw)

        if mode == 'check':
            flag = '' if kind in ('utf-8-bom',) else '  <-- 需要转'
            print(f'{kind:10s} {f}{flag}')
            bad += kind != 'utf-8-bom'
            continue

        if mode == 'clean':
            baks = list(f.parent.glob(f.name + '.gbk.bak'))
            for b in baks:
                b.unlink()
                print(f'删除备份 {b}')
            continue

        if kind == 'utf-8-bom':
            print(f'{f}  已是 UTF-8 with BOM, 跳过')
            continue
        if kind == 'unknown':
            print(f'{f}  编码无法识别, 跳过')
            bad += 1
            continue

        shutil.copy2(f, Path(str(f) + '.gbk.bak'))
        text = raw.decode('gb18030' if kind == 'gbk' else 'utf-8')
        f.write_bytes(BOM + text.encode('utf-8'))
        print(f'{f}  {kind} -> UTF-8 with BOM  (备份 {f.name}.gbk.bak)')

    if mode == 'check':
        print(f'\n{len(targets(argv))} 个文件, {bad} 个需要转换')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
