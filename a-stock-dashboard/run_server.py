# -*- coding: utf-8 -*-
"""A股波段看板 · 本地一键服务器（主看板 a-stock-dashboard）

功能：
  1. 静态服务看板 index.html
  2. PUT /api/save-data  -> 把看板发来的数据写入三副本 data.json，
     并自动 git add + commit + push origin main
  3. GET /api/health    -> 健康检查

用法：
  python run_server.py
  或双击桌面「启动看板服务器.bat」
  浏览器打开 http://localhost:8080/
  在看板里填数据后点「同步到仓库」即可，全自动落盘+推送。
"""

import http.server
import sys
import os
import json
import subprocess
import time
from datetime import datetime

PORT = 8080
DIR = os.path.dirname(os.path.abspath(__file__))   # a-stock-dashboard
ROOT = os.path.dirname(DIR)                        # Desktop（git 仓库根）

DATA_MAIN = os.path.join(DIR, 'data.json')
DATA_SYS = os.path.join(ROOT, '百日新高系统', 'data.json')


def sort_records(records):
    return sorted(records, key=lambda r: str(r.get('date', '')))


def desktop_json_path(latest_date):
    return os.path.join(ROOT, 'a股波段看板_%s.json' % latest_date)


def commit_message(rec):
    d = str(rec.get('date', ''))
    mmdd = (d[5:7] + d[8:10]) if len(d) >= 10 else d.replace('-', '')
    lu = rec.get('limitUp', 0)
    nh = rec.get('newHigh', 0)
    nl = rec.get('newLow', 0)
    rise = rec.get('rise', 0)
    fall = rec.get('fall', 0)
    return '看板数据更新 %s（涨停%s/新高%s/新低%s/涨%s跌%s）' % (mmdd, lu, nh, nl, rise, fall)


def run_git(args):
    return subprocess.run(['git'] + args, cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8')


def do_git_sync(files, rec):
    """只 add 指定文件，不碰仓库里其它未提交改动。"""
    log = []
    r = run_git(['add'] + files)
    if r.returncode != 0:
        return {'ok': False, 'stage': 'add', 'detail': r.stderr.strip() or r.stdout.strip()}
    # 是否有暂存改动
    chk = run_git(['diff', '--cached', '--quiet'])
    if chk.returncode == 0:
        log.append('无新增改动，跳过 commit')
        return {'ok': True, 'note': 'no changes', 'log': log}
    msg = commit_message(rec)
    r = run_git(['commit', '-m', msg])
    if r.returncode != 0:
        return {'ok': False, 'stage': 'commit', 'detail': (r.stderr or r.stdout).strip()}
    log.append('commit: %s' % msg)
    last = ''
    for i in range(3):
        r = run_git(['push', 'origin', 'main'])
        if r.returncode == 0:
            log.append('push ok')
            return {'ok': True, 'log': log, 'commit': msg, 'pushed': True}
        last = (r.stderr or r.stdout).strip()
        if i < 2:
            time.sleep(2)
    log.append('push FAILED x3')
    return {'ok': False, 'stage': 'push', 'detail': last, 'log': log,
            'committed': True, 'commit': msg, 'pushed': False}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    def do_PUT(self):
        if self.path not in ('/api/save-data', '/api/save-data/'):
            self._send_json({'ok': False, 'error': 'not found'}, 404)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode('utf-8'))
            if not isinstance(data, list) or not data:
                self._send_json({'ok': False, 'error': '数据必须是非空数组'}, 400)
                return

            records = sort_records(data)
            latest_date = str(records[-1].get('date', ''))
            # 原版 data.json 为紧凑单行、ensure_ascii=False、无末尾换行
            payload = json.dumps(records, ensure_ascii=False)

            # 三副本写入
            with open(DATA_MAIN, 'w', encoding='utf-8') as f:
                f.write(payload)
            with open(DATA_SYS, 'w', encoding='utf-8') as f:
                f.write(payload)
            desk = desktop_json_path(latest_date)
            with open(desk, 'w', encoding='utf-8') as f:
                f.write(payload)

            files = [
                'a-stock-dashboard/data.json',
                '百日新高系统/data.json',
                'a股波段看板_%s.json' % latest_date,
            ]
            git = do_git_sync(files, records[-1])

            self._send_json({
                'ok': True,
                'records': len(records),
                'latest': latest_date,
                'files': files,
                'git': git,
            })
        except Exception as e:
            self._send_json({'ok': False, 'error': str(e)}, 500)

    def do_GET(self):
        if self.path in ('/api/health', '/api/health/'):
            self._send_json({'ok': True, 'time': datetime.now().isoformat()})
            return
        return super().do_GET()

    def log_message(self, fmt, *args):
        if len(args) >= 1 and isinstance(args[0], str) and 'favicon' in args[0]:
            return
        ts = datetime.now().strftime('%H:%M:%S')
        sys.stderr.write('  [%s] %s\n' % (ts, ' '.join(str(a) for a in args)))
        sys.stderr.flush()


def main():
    url = 'http://localhost:%d/' % PORT
    sys.stderr.write('''
  ==========================================
     A股波段看板 · 本地一键服务器（全自动）
  ==========================================

    看板地址: %s
    数据文件: %s
    同步副本: %s

    流程：填数据 -> 点「同步到仓库」-> 自动写三副本 + git commit/push

    按 Ctrl+C 停止
  ==========================================
''' % (url, DATA_MAIN, DATA_SYS))
    sys.stderr.flush()

    server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write('\n  服务器已停止\n')
        server.server_close()


if __name__ == '__main__':
    main()
