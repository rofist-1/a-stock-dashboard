# -*- coding: utf-8 -*-
"""A股市场情绪综合看板18 · 本地服务器

功能：
  1. 静态服务看板 HTML（A股市场情绪综合看板18.html）
  2. PUT /api/save-data  -> 把看板数据写入同目录 data.json（供 git 同步）
  3. GET  /api/list-bottom-surge -> 列出底部放量数据日期（兼容旧接口）

用法：
  python run_server.py
  然后浏览器打开 http://localhost:8080/A股市场情绪综合看板18.html
  在看板里点「同步到仓库」按钮即可把数据写入 data.json
  最后 git commit/push 上传 data.json
"""

import http.server
import sys
import os
import json
from datetime import datetime

PORT = 8080
DIR = os.path.dirname(os.path.abspath(__file__))  # 百日新高系统 目录
DASHBOARD = 'A股市场情绪综合看板18.html'
DATA_FILE = os.path.join(DIR, 'data.json')


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
        if self.path == '/api/save-data' or self.path == '/api/save-data/':
            try:
                length = int(self.headers.get('Content-Length', 0))
                raw = self.rfile.read(length)
                data = json.loads(raw.decode('utf-8'))
                if not isinstance(data, list):
                    self._send_json({'ok': False, 'error': '数据必须是数组'}, 400)
                    return
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self._send_json({'ok': True, 'file': 'data.json', 'records': len(data)})
            except Exception as e:
                self._send_json({'ok': False, 'error': str(e)}, 500)
            return
        self._send_json({'ok': False, 'error': 'not found'}, 404)

    def do_GET(self):
        if self.path == '/api/list-bottom-surge':
            import glob as _g
            import re as _r
            files = _g.glob(os.path.join(DIR, '底部放量_*.json'))
            dates = []
            for f in files:
                m = _r.search(r'底部放量_(\d{8})\.json', f)
                if m:
                    dates.append(m.group(1))
            dates.sort(reverse=True)
            self._send_json({'dates': dates})
            return
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def log_message(self, fmt, *args):
        if len(args) >= 1 and isinstance(args[0], str) and 'favicon' in args[0]:
            return
        ts = datetime.now().strftime('%H:%M:%S')
        parts = ' '.join(str(a) for a in args)
        sys.stderr.write(f'  [{ts}] {parts}\n')
        sys.stderr.flush()


def main():
    url = f'http://localhost:{PORT}/{DASHBOARD}'
    sys.stderr.write(f'''
  ==========================================
     A股市场情绪综合看板18 · 本地服务器
  ==========================================

   服务目录: {DIR}
   看板地址:
   {url}

   数据文件: {DATA_FILE}
   （在看板点「同步到仓库」写入 data.json）

   按 Ctrl+C 停止服务器
  ==========================================
  '''.lstrip() + '\n')
    sys.stderr.flush()

    server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write('\n  服务器已停止\n')
        server.server_close()


if __name__ == '__main__':
    main()
