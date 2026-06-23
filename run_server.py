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

    def do_GET(self):
        if self.path == '/api/list-bottom-surge':
            import glob as _g, re as _r, json as _j
            data_dir = os.path.join(DIR, '百日新高系统')
            files = _g.glob(os.path.join(data_dir, '底部放量_*.json'))
            dates = []
            for f in files:
                m = _r.search(r'底部放量_(\d{8})\.json', f)
                if m: dates.append(m.group(1))
            dates.sort(reverse=True)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(_j.dumps({'dates': dates}).encode('utf-8'))
            return
        if self.path.startswith('/api/stock-ma'):
            import urllib.parse as _up
            import pickle as _pk
            import json as _j
            CACHE = os.path.join(DIR, '百日新高系统', 'kline_cache')
            qs = _up.urlparse(self.path).query
            params = _up.parse_qs(qs)
            codes_raw = params.get('codes', [''])[0]
            req_codes = [c.strip().upper() for c in codes_raw.split(',') if c.strip()]
            date_str = params.get('date', [None])[0]  # optional YYYY-MM-DD or YYYYMMDD
            result = {}
            for rc in req_codes:
                cand = []
                if rc.startswith('6'):
                    cand.append('sh' + rc[-6:])
                elif rc.startswith('0') or rc.startswith('3'):
                    cand.append('sz' + rc[-6:])
                elif rc.startswith('4') or rc.startswith('8'):
                    cand.append('bj' + rc[-6:])
                else:
                    cand.append(rc.lower())
                found = None
                for c in cand:
                    fp = os.path.join(CACHE, c + '.pkl')
                    if os.path.exists(fp):
                        found = fp; break
                if not found:
                    cc = rc.replace('.SH','').replace('.SZ','').replace('.BJ','')[-6:]
                    for prefix in ['sh','sz','bj']:
                        fp = os.path.join(CACHE, prefix + cc + '.pkl')
                        if os.path.exists(fp):
                            found = fp; break
                if not found:
                    result[rc] = {'error': 'not_found'}; continue
                try:
                    with open(found, 'rb') as f:
                        kdata = _pk.load(f)
                    df = kdata.get('df')
                    if df is None or len(df) < 20:
                        result[rc] = {'error': 'insufficient_data'}; continue
                    # Determine end index: if date_str given, find it; else use last
                    dates_col = df['date'].tolist()
                    # dates may be int (YYYYMMDD) or string
                    end_idx = len(dates_col) - 1  # default: latest
                    if date_str:
                        target = date_str.replace('-', '')
                        try:
                            target_int = int(target)
                            for i in range(len(dates_col) - 1, -1, -1):
                                d = dates_col[i]
                                if isinstance(d, str):
                                    d_clean = d.replace('-', '')[:8]
                                elif hasattr(d, 'strftime'):
                                    d_clean = d.strftime('%Y%m%d')
                                else:
                                    d_clean = str(d)[:8].replace('-','')
                                if int(d_clean) == target_int:
                                    end_idx = i; break
                        except:
                            pass
                    if end_idx < 13:
                        result[rc] = {'error': 'date_too_early'}; continue
                    closes = df['close'].tolist()[:end_idx+1]
                    highs = df['high'].tolist()[:end_idx+1]
                    lows = df['low'].tolist()[:end_idx+1]
                    today_close = closes[-1]
                    today_date = str(dates_col[end_idx])
                    # SMA
                    ma5 = sum(closes[-5:])/5 if len(closes) >= 5 else None
                    ma13 = sum(closes[-13:])/13 if len(closes) >= 13 else None
                    ma60 = sum(closes[-60:])/60 if len(closes) >= 60 else None
                    # EMA
                    def ema(vals, n):
                        k = 2/(n+1); e = sum(vals[-n:])/n
                        for v in vals[-(n-1):]: e = v*k + e*(1-k)
                        return e
                    ema5 = ema(closes, 5) if len(closes) >= 5 else None
                    ema13 = ema(closes, 13) if len(closes) >= 13 else None
                    # ATR
                    def atr(h, l, c, n=14):
                        tr = []
                        for i in range(1, len(c)):
                            tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
                        return sum(tr[-n:])/n if len(tr) >= n else sum(tr)/len(tr)
                    atr14 = atr(highs, lows, closes, 14) if len(closes) > 14 else None
                    # direction helpers
                    def dir_str(val, ago_val, thr=0.5):
                        if ago_val is None: return '--'
                        chg = (val - ago_val)/ago_val*100
                        return '上升' if chg > thr else ('下降' if chg < -thr else '走平')
                    ma5_dir = dir_str(ma5, sum(closes[-10:-5])/5 if len(closes) >= 10 else None) if ma5 else '--'
                    ma13_dir = dir_str(ma13, sum(closes[-23:-10])/13 if len(closes) >= 23 else None) if ma13 else '--'
                    ema5_dir = dir_str(ema5, ema(closes[:-1], 5) if len(closes) > 5 else None, 0.3) if ema5 else '--'
                    ema13_dir = dir_str(ema13, ema(closes[:-1], 13) if len(closes) > 13 else None, 0.3) if ema13 else '--'
                    result[rc] = {
                        'close': round(today_close, 2), 'date': today_date,
                        'ma5': round(ma5, 2) if ma5 else None, 'ma13': round(ma13, 2) if ma13 else None,
                        'ma60': round(ma60, 2) if ma60 else None,
                        'ema5': round(ema5, 2) if ema5 else None, 'ema13': round(ema13, 2) if ema13 else None,
                        'atr14': round(atr14, 2) if atr14 else None,
                        'ma5_dir': ma5_dir, 'ma13_dir': ma13_dir,
                        'ema5_dir': ema5_dir, 'ema13_dir': ema13_dir,
                    }
                except Exception as e:
                    result[rc] = {'error': str(e)}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(_j.dumps(result).encode('utf-8'))
            return
        if self.path.startswith('/api/three-step-analyze'):
            import urllib.parse as _up
            import json as _j
            import sys as _sys
            _sys.path.insert(0, os.path.join(DIR, '百日新高系统'))
            from three_step_analyzer import analyze_stock as _analyze
            qs = _up.urlparse(self.path).query
            params = _up.parse_qs(qs)
            stock = params.get('stock', [''])[0]
            if not stock:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(_j.dumps({'error': 'Missing stock parameter'}).encode('utf-8'))
                return
            out = _analyze(stock)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(_j.dumps(out, ensure_ascii=False).encode('utf-8'))
            return
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

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
