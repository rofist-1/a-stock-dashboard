# -*- coding: utf-8 -*-
"""本地 Web 服务器 — 自动清理旧进程 + 防端口冲突"""

import http.server
import sys
import os
import json
import socket
import subprocess
from datetime import datetime

PORT = 8080
# 服务桌面根目录，让综合看板和教学看板都可用
DIR = r'C:\Users\Rofis\Desktop'
DASHBOARDS = ('A股市场情绪综合看板17.html', '百日新高教学看板.html')

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def do_PUT(self):
        """接收看板数据写入 data.json"""
        if self.path == '/api/save-data':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            dest = os.path.join(DIR, 'data.json')
            try:
                with open(dest, 'wb') as f:
                    f.write(body)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                ts = datetime.now().strftime('%H:%M:%S')
                sys.stderr.write(f'  [{ts}] data.json saved ({len(body)} bytes)\n')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'{{"ok":false,"error":"{e}"}}'.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/api/list-bottom-surge':
            try:
                import glob
                pattern = os.path.join(DIR, '百日新高系统', '底部放量_*.json')
                files = glob.glob(pattern)
                dates = [os.path.basename(f).replace('底部放量_', '').replace('.json', '') for f in files]
                dates.sort(reverse=True)
                body = json.dumps({'dates': dates}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Error: {e}'.encode())
            return
        return super().do_GET()

    def do_POST(self):
        self.do_PUT()

    def log_message(self, fmt, *args):
        if len(args) >= 1 and isinstance(args[0], str) and 'favicon' in args[0]:
            return
        ts = datetime.now().strftime('%H:%M:%S')
        sys.stderr.write(f'  [{ts}] {" ".join(str(a) for a in args)}\n')
        sys.stderr.flush()

def kill_old_server():
    """杀掉占用 PORT 的旧进程"""
    import subprocess, signal
    if sys.platform == 'win32':
        r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if f':{PORT}' in line and 'LISTENING' in line:
                pid = line.strip().split()[-1]
                try:
                    subprocess.run(['taskkill', '/f', '/pid', pid], capture_output=True)
                except:
                    pass

def main():
    kill_old_server()

    sys.stderr.write(f'''
  ==========================================
    百日新高 · 本地服务器
  ==========================================

  服务目录: {DIR}
  综合看板: http://localhost:{PORT}/{DASHBOARDS[0]}
  教学看板: http://localhost:{PORT}/{DASHBOARDS[1]}
   API:      PUT /api/save-data → data.json
   API:      GET /api/list-bottom-surge → 底部放量日期列表

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
