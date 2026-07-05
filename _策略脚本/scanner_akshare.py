# -*- coding: utf-8 -*-
"""
百日新高全市场扫描器
====================
依赖: pip install akshare pandas requests openpyxl

用法:
  python scanner_akshare.py                  # 全市场(首次约3分钟)
  python scanner_akshare.py                  # 后续(增量更新,约30秒)
"""

import sys, os, csv, json, time, io, ssl, urllib.request, pickle
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import akshare as ak
import pandas as pd

# ═══════════════════════════════
#  环境
# ═══════════════════════════════

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
HDR = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}
CACHE = 'kline_cache'
os.makedirs(CACHE, exist_ok=True)

# ═══════════════════════════════
#  工具
# ═══════════════════════════════

def to_full(c):
    c = str(c).strip().zfill(6)
    return f'{c}.{"SH" if c.startswith("6") else "SZ"}'

def to_sina(c):
    c = str(c).strip().zfill(6)
    return ('sh' if c.startswith('6') else 'sz') + c

SECTOR_MAP = {}  # code->sector (来自东方财富)
SECTOR_KEYWORDS = {
    '芯片': ['芯片','半导体','集成电路','晶圆','硅片','光刻','中芯','华创','兆易','韦尔','紫光','三安','贝岭'],
    '算力': ['算力','服务器','数据中心','光模块','中科曙光','浪潮','海光'],
    '人工智能': ['人工智能','AI','大模型','智能','海康威视','科大讯飞'],
    '机器人': ['机器人','减速器','伺服','埃斯顿','汇川'],
    '通信': ['通信','5G','6G','光通信','中兴','中际旭创'],
    '锂电池': ['锂电','电池','宁德','赣锋','国轩'],
    '光伏': ['光伏','太阳能','隆基','通威','天合','正泰'],
    '新能源车': ['新能源车','汽车','比亚迪','整车','自动驾驶'],
    '军工': ['军工','航天','卫星','船舶','中船'],
    '医药': ['医药','医疗','生物','药','医','健康','恒瑞','迈瑞'],
    '消费': ['消费','食品','饮料','白酒','家电','美的','格力','海尔','茅台','五粮液'],
    '金融': ['银行','券商','保险','证券','平安','中信','招商'],
    '化工': ['化工','化学','石化','万华'],
    '电力': ['电力','能源','电网','长江电力','核电'],
    '有色金属': ['有色','金属','黄金','铜','铝','锂矿','稀土'],
    '传媒': ['传媒','游戏','影视','广告'],
    '机械': ['机械','装备','制造','重工','三一','中联'],
    '电子': ['电子','光电','LED','光学'],
    '煤炭': ['煤炭','煤电','焦煤','平煤'],
    '环保': ['环保','生态'],
    '造纸': ['造纸'],
}

def load_sector_map():
    """加载东方财富板块映射"""
    global SECTOR_MAP
    map_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sector_map.json')
    if os.path.exists(map_file):
        try:
            with open(map_file, 'r', encoding='utf-8') as f:
                SECTOR_MAP = json.load(f)
            print(f'  ✓ 加载板块映射: {len(SECTOR_MAP)}只')
        except:
            pass

def classify(code, name):
    """确定股票所属板块: 先查东方财富映射, 再回退到关键字"""
    if not SECTOR_MAP:
        load_sector_map()
    c = str(code).strip().zfill(6)
    if c in SECTOR_MAP:
        return SECTOR_MAP[c]
    # 回退: 按名称关键字匹配
    for s, kws in SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in name:
                return s
    return '其他'

def load_prev_set():
    try:
        p = '百日新高_历史趋势.json'
        if not os.path.exists(p):
            return set()
        with open(p, 'r', encoding='utf-8') as f:
            h = json.load(f)
        if not h:
            return set()
        d = h[-1]['date'].replace('-', '')
        j = f'百日新高_{d}.json'
        if os.path.exists(j):
            with open(j, 'r', encoding='utf-8') as f:
                dat = json.load(f)
            return {s['code'] for s in dat.get('stocks', [])}
    except:
        pass
    return set()

# ═══════════════════════════════
#  Sina批量行情 (顺序批, 稳定)
# ═══════════════════════════════

def get_batch_quotes(sina_codes):
    """顺序获取所有行情, 每批80只, 带重试"""
    results = {}
    total = len(sina_codes)
    for i in range(0, total, 80):
        batch = sina_codes[i:i+80]
        url = 'https://hq.sinajs.cn/list=' + ','.join(batch)
        for _ in range(3):
            try:
                req = urllib.request.Request(url, headers=HDR)
                resp = urllib.request.urlopen(req, timeout=10, context=ctx)
                for line in resp.read().decode('gbk').strip().split('\n'):
                    line = line.strip()
                    if not line or '="' not in line:
                        continue
                    vn = line.split('="')[0].replace('var hq_str_', '')
                    vals = line.split('="')[1].rstrip('";').split(',')
                    if len(vals) >= 32:
                        p = float(vals[3]) if vals[3] else 0
                        pc = float(vals[2]) if vals[2] else 0
                        h = float(vals[4]) if vals[4] else 0
                        v = int(vals[8]) if vals[8] else 0
                        results[vn] = {'price': p, 'pc': pc, 'high': h, 'vol': v}
                break
            except Exception:
                time.sleep(0.5)
    return results

# ═══════════════════════════════
#  K线获取 + 百日新高检查
# ═══════════════════════════════

def check_stock(sina_code, info, prev_set):
    """获取K线 -> 检查百日新高 -> 缓存结果"""
    cache_file = os.path.join(CACHE, f'{sina_code}.pkl')
    today_str = str(datetime.now().date())

    # 尝试从缓存读取
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'rb') as f:
                cached = pickle.load(f)
            if isinstance(cached, dict) and cached.get('date') == today_str:
                df = cached.get('df')
                if df is not None and len(df) > 20:
                    return _do_check(df, info, prev_set)
        except:
            pass

    # API获取
    try:
        start = (datetime.now() - timedelta(days=240)).strftime('%Y%m%d')
        end = datetime.now().strftime('%Y%m%d')
        df = ak.stock_zh_a_daily(symbol=sina_code, start_date=start, end_date=end, adjust='qfq')
        if df is None or len(df) < 20:
            return None
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({'date': today_str, 'df': df}, f)
        except:
            pass
        return _do_check(df, info, prev_set)
    except Exception:
        return None


def _do_check(df, info, prev_set):
    """从DataFrame检查百日新高"""
    try:
        highs = df['high'].tolist()
        closes = df['close'].tolist()
        vols = df['volume'].tolist() if 'volume' in df.columns else []
        if len(highs) < 20:
            return None

        th = float(highs[-1])  # today high
        tc = float(closes[-1])  # today close

        # 排除今日, 前100天最高
        if len(highs) > 100:
            past = highs[-101:-1]
        else:
            past = highs[:-1]
        if not past:
            return None
        h100 = max(past)
        if th < h100 or h100 <= 0:
            return None

        # 涨幅
        pc = closes[-2] if len(closes) > 1 else tc
        chg = round((tc - pc) / pc * 100, 2) if pc else 0

        # 量比
        if len(vols) >= 6:
            avg5 = sum(vols[-6:-1]) / 5
            vr = round(vols[-1] / max(avg5, 1), 2) if avg5 > 0 else 1.0
        else:
            vr = 1.0

        full_code = to_full(info['code'])
        return {
            'code': full_code,
            'name': info.get('name', ''),
            'close': round(tc, 2),
            'change': chg,
            'volume_ratio': vr,
            'is_first': full_code not in prev_set,
            'sector': classify(info.get('code', ''), info.get('name', '')),
        }
    except:
        return None

# ═══════════════════════════════
#  主流程
# ═══════════════════════════════

def main():
    t0 = time.time()
    print(f'\n  ═══════════════════════════════════════')
    print(f'  百日新高全市场扫描器')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  ═══════════════════════════════════════\n')

    # 0. 加载板块映射
    print('  [0/4] 加载板块映射...')
    load_sector_map()

    # 1. 股票列表
    print('  [1/4] 获取股票列表...')
    all_stocks = []
    try:
        df_list = ak.stock_info_a_code_name()
        if df_list is not None and len(df_list) > 0:
            for _, row in df_list.iterrows():
                c = str(row.get('code', '')).strip().zfill(6)
                n = str(row.get('name', '')).strip()
                if c and n:
                    all_stocks.append({'code': c, 'name': n, 'sina': to_sina(c)})
    except Exception as e:
        print(f'  ⚠ EastMoney API失败: {e}')
    if not all_stocks:
        fallback = 'stock_list.json'
        if os.path.exists(fallback):
            print(f'  ↳ 改用本地列表: {fallback}')
            with open(fallback, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            for s in raw:
                c = str(s['code']).strip().zfill(6)
                n = str(s.get('name', '')).strip()
                if c and n:
                    all_stocks.append({'code': c, 'name': n, 'sina': to_sina(c)})
        else:
            print(f'  ✗ 无在线列表也无本地文件，无法继续')
            return
    print(f'  ✓ {len(all_stocks)}只\n')

    # 2. 批量获取实时行情 (过滤候选)
    print('  [2/4] 获取实时行情...')
    sina_codes = [s['sina'] for s in all_stocks]
    quotes = get_batch_quotes(sina_codes)
    print(f'  ✓ 获取{len(quotes)}只行情')

    # 过滤: 今日涨幅 > -3% 或 成交量 > 0
    prev_set = load_prev_set()
    todo = []
    for s in all_stocks:
        q = quotes.get(s['sina'])
        if not q or q['price'] <= 0:
            continue
        chg = ((q['price'] - q['pc']) / q['pc'] * 100) if q['pc'] else 0
        if chg < -3:
            continue  # 大跌的不可能新高
        s['change_pct'] = chg
        s['price'] = q['price']
        todo.append(s)
    print(f'  ✓ 候选{len(todo)}只 (过滤跌幅>3%)\n')

    # 3. 检查百日新高
    print(f'  [3/4] 检查百日新高 (并发4线程)...')
    new_highs = []
    checked = 0
    t1 = time.time()

    with ThreadPoolExecutor(max_workers=4) as pool:
        fut_map = {}
        for s in todo:
            f = pool.submit(check_stock, s['sina'], s, prev_set)
            fut_map[f] = s

        for f in as_completed(fut_map):
            checked += 1
            if checked % 300 == 0 or checked == len(todo):
                pct = int(checked / len(todo) * 100)
                print(f'    进度: {checked}/{len(todo)} ({pct}%)  {time.time()-t1:.0f}s  发现{len(new_highs)}只', end='\r')
            try:
                r = f.result()
                if r:
                    new_highs.append(r)
            except:
                pass

    print()
    elapsed = time.time() - t0

    # 4. 输出
    print(f'\n  [4/4] 输出结果...')
    new_highs.sort(key=lambda x: (not x['is_first'], -x['change'], -x['volume_ratio']))

    print(f'\n  ═══════════════════════════════════════')
    print(f'  完成! ({elapsed:.0f}秒)')
    print(f'  ═══════════════════════════════════════')
    print(f'  百日新高: {len(new_highs)}只  (首次:{sum(1 for r in new_highs if r["is_first"])}只)\n')

    if new_highs:
        print(f'  {"代码":<12} {"名称":<8} {"涨幅%":<7} {"量比":<6} {"标签":<10} {"板块":<8}')
        print(f'  {"─"*51}')
        for r in new_highs[:30]:
            tag = '⭐首次' if r['is_first'] else '持续'
            print(f'  {r["code"]:<12} {r["name"][:4]:<8} {r["change"]:+.1f}%  {r["volume_ratio"]:<5.1f} {tag:<10} {r["sector"]}')
        if len(new_highs) > 30:
            print(f'  ... 还有{len(new_highs)-30}只 (详见CSV/JSON)')

        sec = defaultdict(lambda: [0, 0])
        for r in new_highs:
            sec[r['sector']][0] += 1
            if r['is_first']:
                sec[r['sector']][1] += 1
        if sec:
            print(f'\n  ┌─ 板块分布 ─────────────────────────┐')
            for s, v in sorted(sec.items(), key=lambda x: -x[1][0])[:10]:
                bar = '█' * v[0]
                print(f'  │ {s:<8} {v[0]:>2}只 (首次{v[1]}只)')
            print(f'  └────────────────────────────────────┘')

        save(new_highs)
    else:
        print('  今日无百日新高个股')
    print()


def save(new_highs):
    now = datetime.now()
    d = now.strftime('%Y%m%d')
    ds = now.strftime('%Y-%m-%d')

    # CSV
    p = f'百日新高_{d}.csv'
    with open(p, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['代码','名称','收盘价','涨幅%','量比','标签','板块'])
        for r in new_highs:
            w.writerow([r['code'], r['name'], r['close'], r['change'],
                       r['volume_ratio'], '首次★' if r['is_first'] else '持续', r['sector']])
    print(f'  >> CSV: {p}')

    # JSON
    jp = f'百日新高_{d}.json'
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump({
            'date': ds, 'total': len(new_highs),
            'first_count': sum(1 for r in new_highs if r['is_first']),
            'stocks': new_highs,
        }, f, ensure_ascii=False, indent=2)
    print(f'  >> JSON: {jp}')

    # 历史趋势
    hp = '百日新高_历史趋势.json'
    h = []
    if os.path.exists(hp):
        try:
            with open(hp, 'r', encoding='utf-8') as f:
                h = json.load(f)
        except:
            pass
    h = [x for x in h if x.get('date') != ds]
    h.append({'date': ds, 'total': len(new_highs), 'first_count': sum(1 for r in new_highs if r['is_first'])})
    h.sort(key=lambda x: x['date'])
    with open(hp, 'w', encoding='utf-8') as f:
        json.dump(h, f, ensure_ascii=False, indent=2)
    print(f'  >> 趋势: {hp}')


if __name__ == '__main__':
    main()
