# -*- coding: utf-8 -*-
"""实验报告生成器的小界面（本地网页）。

    python <SKILL>/ui/server.py                 # 默认 http://127.0.0.1:8722
    python <SKILL>/ui/server.py --port 8800 --root "D:\\文件\\教材\\物理实验" --open

页面上填：实验名称（从 experiments.json 里搜）、输出格式、姓名/教师/日期（可留空）、
记录纸照片、补充文件、补充说明，然后生成 → 落到 `<root>/<实验目录>/实验数据/`。

只用标准库（http.server），不联网、不装依赖。上传走内存 + 一次性落盘，不污染实验目录。
"""
import argparse
import json
import shutil
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REPO = SKILL.parent
sys.path.insert(0, str(SKILL / 'scripts'))
import make_report as mr  # noqa: E402

if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

UPLOADS = {}          # id -> (文件名, bytes, 时间)
UPLOAD_LOCK = threading.Lock()
STATE = {'root': Path('.').resolve(), 'counter': 0}

# 各输出格式靠什么编译; 界面上标一下本机有没有, 免得选完才发现跑不起来
TOOLS = {'typst': 'typst', 'latex': 'xelatex', 'docx': 'winword', 'md': None}


def tools_available():
    got = {}
    for fmt, exe in TOOLS.items():
        if exe is None:
            got[fmt] = True                        # md 不用编译
        elif exe == 'winword':
            got[fmt] = True                        # docx 交给 Word/WPS 打开, 只生成文件
        else:
            got[fmt] = shutil.which(exe) is not None
    return got


def scan_sample_names():
    """顺手把 sample/ 和实验目录下已经存在的子目录名也收进候选, 方便搜索。"""
    names = []
    for base in (REPO / 'sample', STATE['root']):
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if p.is_dir() and not p.name.startswith(('.', '_')) and p.name not in ('模板', '参考', '范例报告', 'my_sample'):
                names.append(p.name)
    return names


def config():
    exps = mr.load_experiments()
    listed = {e['name'] for e in exps}
    extra = [n for n in scan_sample_names() if n not in listed]
    return {
        'experiments': exps,
        'extra_dirs': sorted(set(extra)),
        'formats': [{'value': k, 'label': v[1], 'file': v[0], 'tool_ok': tools_available()[k]}
                    for k, v in mr.FORMATS.items()],
        'root': str(STATE['root']),
        'skill_dir': str(SKILL),
        'sample_dir': str(REPO / 'sample'),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = 'lab-report-ui'

    def log_message(self, fmt, *a):
        sys.stderr.write(f'  {self.address_string()} {fmt % a}\n')

    # ---- 小工具 ----
    def _send(self, code, body: bytes, ctype='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def _body(self) -> bytes:
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    # ---- 路由 ----
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ('/', '/index.html'):
            page = (HERE / 'index.html').read_bytes()
            self._send(200, page, 'text/html; charset=utf-8')
        elif path == '/api/config':
            self._json(config())
        else:
            self._json({'error': f'没有这个地址: {path}'}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path, q = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            if path == '/api/upload':
                self._upload(q)
            elif path == '/api/generate':
                self._generate()
            elif path == '/api/reveal':
                self._reveal()
            else:
                self._json({'error': f'没有这个地址: {path}'}, 404)
        except Exception as e:                       # 任何异常都回给前端显示, 不要静默
            self._json({'error': f'{type(e).__name__}: {e}'}, 400)

    def _upload(self, q):
        name = (q.get('name') or ['未命名'])[0]
        data = self._body()
        with UPLOAD_LOCK:
            STATE['counter'] += 1
            uid = f'u{STATE["counter"]}'
            UPLOADS[uid] = (Path(name).name, data, time.time())
            # 顺手清掉两小时前没人用的, 免得内存里越攒越多
            for k in [k for k, v in UPLOADS.items() if time.time() - v[2] > 7200]:
                UPLOADS.pop(k, None)
        self._json({'id': uid, 'name': Path(name).name, 'size': len(data)})

    def _generate(self):
        params = json.loads(self._body().decode('utf-8'))
        root = Path(params.pop('实验目录', '') or STATE['root']).expanduser()
        force = bool(params.pop('覆盖已有报告', False))
        fmt = params.get('输出格式', 'typst')

        exp_dir, data_dir = mr.target_dirs(params, root)
        stage = data_dir / '.上传暂存'
        staged = {'补充文件': [], '记录纸照片': []}
        try:
            for key in staged:
                for item in params.pop(key, []) or []:
                    uid = item.get('id') if isinstance(item, dict) else item
                    with UPLOAD_LOCK:
                        # 注意是 get 不是 pop: 生成失败(比如文件已存在)后用户勾一下覆盖再点一次,
                        # 文件还得在 —— 否则会莫名其妙报"上传已过期"
                        got = UPLOADS.get(uid)
                    if not got:
                        raise ValueError(f'上传的 {key} 已经过期，请重新选一次文件')
                    name, blob = got[0], got[1]
                    d = stage / ('照片' if key == '记录纸照片' else '补充文件')
                    d.mkdir(parents=True, exist_ok=True)
                    f = mr.unique(d / mr.safe_name(name))
                    f.write_bytes(blob)
                    staged[key].append(str(f))
            params['补充文件'] = staged['补充文件']
            params['记录纸照片'] = staged['记录纸照片']
            result = mr.make(params, root, force=force)
        finally:
            shutil.rmtree(stage, ignore_errors=True)   # 先清干净再回响应, 免得客户端看到残留
        result['输出格式中文'] = mr.FORMATS[fmt][1]
        self._json(result)

    def _reveal(self):
        """在资源管理器里打开生成的目录（只在 Windows 上有意义）。"""
        target = Path(json.loads(self._body().decode('utf-8'))['path'])
        if not target.exists():
            raise FileNotFoundError(f'目录不存在: {target}')
        import subprocess
        subprocess.Popen(['explorer', str(target)])
        self._json({'ok': True})


def make_server(port: int, root):
    """建好服务但不开始 serve —— 测试脚本也要用, 所以跟 main() 分开。"""
    STATE['root'] = Path(root).expanduser().resolve()
    STATE['root'].mkdir(parents=True, exist_ok=True)
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', p), Handler)
            return srv, srv.server_address[1]      # port=0 时返回真实端口
        except OSError:
            continue
    raise OSError(f'{port} 起往后 20 个端口都被占了，换个 --port')


def main(argv):
    ap = argparse.ArgumentParser(description='实验报告生成界面')
    ap.add_argument('--port', type=int, default=8722)
    ap.add_argument('--root', default='.', help='实验目录的上级目录(默认当前目录)')
    ap.add_argument('--open', action='store_true', help='启动后自动打开浏览器')
    a = ap.parse_args(argv)

    try:
        httpd, port = make_server(a.port, a.root)
    except OSError as e:
        print(e)
        return 1
    url = f'http://127.0.0.1:{port}/'
    tool = tools_available()
    print(f'实验报告生成界面已启动: {url}')
    print(f'  实验目录(生成到这里的 <实验>/实验数据/): {STATE["root"]}')
    print(f'  实验名清单: {mr.EXPERIMENTS}')
    print(f'  编译工具: ' + '  '.join(f'{k}={"有" if v else "没有"}' for k, v in tool.items()))
    print('  按 Ctrl+C 退出')
    if a.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已退出')
    finally:
        httpd.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
