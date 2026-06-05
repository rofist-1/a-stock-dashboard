# -*- coding: utf-8 -*-
"""本地 Web 服务器 — 让浏览器能正常加载本地 JSON 文件"""

import http.server
import sys
import os
from datetime import datetime

PORT = 8080
DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = '百日新高教学看板.html'

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def log_message(self, fmt, *args):
        # Suppress favicon 404 noise
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
    百日新高 · 本地服务器
  ==========================================

  服务目录: {DIR}
  仪表盘地址:
  {url}

  请复制上面的地址到浏览器打开
  按 Ctrl+C 停止服务器
  ==========================================
  '''.lstrip() + '\n')
    sys.stderr.flush()

    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write('\n  服务器已停止\n')
        server.server_close()

if __name__ == '__main__':
    main()
