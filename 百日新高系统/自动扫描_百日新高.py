# -*- coding: utf-8 -*-
"""
百日新高自动扫描器 v2 — 真实数据版
===============================
使用新浪财经免费API获取A股真实行情，扫描百日新高成分股。

运行方式:
  python 自动扫描_百日新高.py              # 扫描内置关注池(快)
  python 自动扫描_百日新高.py --all         # 全市场扫描(慢但全)
  python 自动扫描_百日新高.py --teach       # 附带教学讲解

数据来源:
  实时行情: hq.sinajs.cn
  日K线: money.finance.sina.com.cn (免费、无需安装)
"""

import json
import csv
import os
import sys
import time
import io
import ssl
import urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# SSL (解决证书问题)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}

# ═══════════════════════════════════════════
#  股票池 (热门板块+活跃标的)
# ═══════════════════════════════════════════

STOCK_POOL = [
    # (代码, 名称, 板块, 新浪代码)
    # 芯片
    ("002371.SZ", "北方华创", "芯片", "sz002371"),
    ("603986.SH", "兆易创新", "芯片", "sh603986"),
    ("600171.SH", "上海贝岭", "芯片", "sh600171"),
    ("300661.SZ", "圣邦股份", "芯片", "sz300661"),
    ("688981.SH", "中芯国际", "芯片", "sh688981"),
    ("603501.SH", "韦尔股份", "芯片", "sh603501"),
    ("300782.SZ", "卓胜微", "芯片", "sz300782"),
    ("688012.SH", "中微公司", "芯片", "sh688012"),
    ("002049.SZ", "紫光国微", "芯片", "sz002049"),
    ("600703.SH", "三安光电", "芯片", "sh600703"),
    # 算力
    ("603019.SH", "中科曙光", "算力", "sh603019"),
    ("000977.SZ", "浪潮信息", "算力", "sz000977"),
    ("688041.SH", "海光信息", "算力", "sh688041"),
    ("002230.SZ", "科大讯飞", "算力", "sz002230"),
    ("600839.SH", "四川长虹", "算力", "sh600839"),
    # 通信
    ("603236.SH", "移远通信", "通信", "sh603236"),
    ("000063.SZ", "中兴通讯", "通信", "sz000063"),
    ("300308.SZ", "中际旭创", "通信", "sz300308"),
    ("688036.SH", "传音控股", "通信", "sh688036"),
    # 人工智能
    ("600570.SH", "恒生电子", "人工智能", "sh600570"),
    ("002415.SZ", "海康威视", "人工智能", "sz002415"),
    ("688111.SH", "金山办公", "人工智能", "sh688111"),
    ("300418.SZ", "昆仑万维", "人工智能", "sz300418"),
    # 机器人
    ("002747.SZ", "埃斯顿", "机器人", "sz002747"),
    ("600580.SH", "卧龙电驱", "机器人", "sh600580"),
    ("300124.SZ", "汇川技术", "机器人", "sz300124"),
    ("002527.SZ", "新时达", "机器人", "sz002527"),
    ("002896.SZ", "中大力德", "机器人", "sz002896"),
    ("688160.SH", "步科股份", "机器人", "sh688160"),
    # 锂电池
    ("300750.SZ", "宁德时代", "锂电池", "sz300750"),
    ("002460.SZ", "赣锋锂业", "锂电池", "sz002460"),
    ("002074.SZ", "国轩高科", "锂电池", "sz002074"),
    ("600884.SH", "杉杉股份", "锂电池", "sh600884"),
    ("002709.SZ", "天赐材料", "锂电池", "sz002709"),
    # 光伏
    ("601012.SH", "隆基绿能", "光伏", "sh601012"),
    ("600438.SH", "通威股份", "光伏", "sh600438"),
    ("601877.SH", "正泰电器", "光伏", "sh601877"),
    ("688599.SH", "天合光能", "光伏", "sh688599"),
    # 商业航天
    ("600118.SH", "中国卫星", "商业航天", "sh600118"),
    ("002025.SZ", "航天电器", "商业航天", "sz002025"),
    ("600879.SH", "航天电子", "商业航天", "sh600879"),
    ("688568.SH", "中科星图", "商业航天", "sh688568"),
    # 化工
    ("600160.SH", "巨化股份", "化工", "sh600160"),
    ("601678.SH", "滨化股份", "化工", "sh601678"),
    ("600141.SH", "兴发集团", "化工", "sh600141"),
    # 电力
    ("600900.SH", "长江电力", "电力", "sh600900"),
    ("601985.SH", "中国核电", "电力", "sh601985"),
    ("600886.SH", "国投电力", "电力", "sh600886"),
]

TEACHING = {
    "first_high": {
        "title": "首次新高",
        "meaning": "该股近5个交易日首次创出百日新高",
        "significance": "首次新高意味着股价刚刚突破长期平台，通常有较强的上涨惯性。这是最值得关注的一类。",
        "action": "重点关注，若叠加板块热点+放量，是较好的买入观察标的。",
    },
    "volume_ratio": {
        "title": "量比",
        "meaning": "今日成交量 / 近5日平均成交量",
        "significance": "量比 > 1.5 放量明显，说明有资金介入；量比 > 2.5 可能出现异常放量，需警惕出货",
        "action": "量比1.5-2.5配合新高 = 健康放量突破；量比 > 3 需结合涨幅判断",
    },
    "sector": {
        "title": "板块效应",
        "meaning": "同一板块出现多只百日新高个股，说明板块整体走强",
        "significance": "板块效应是持续性最重要的保障。单打独斗的个股持续性较差。",
        "action": "优先选择板块新高家数排名靠前的板块；板块内选最强",
    },
}

# ═══════════════════════════════════════════
#  网络API
# ═══════════════════════════════════════════

def sina_batch_quote(sina_codes):
    """批量获取实时行情"""
    results = {}
    # 分批次，每批最多80只
    batch_size = 80
    for i in range(0, len(sina_codes), batch_size):
        batch = sina_codes[i:i+batch_size]
        joined = ','.join(batch)
        url = f'https://hq.sinajs.cn/list={joined}'
        for retry in range(3):
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                resp = urllib.request.urlopen(req, timeout=10, context=ctx)
                text = resp.read().decode('gbk')
                for line in text.strip().split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split('="')
                    if len(parts) < 2:
                        continue
                    var_name = parts[0].replace('var hq_str_', '')
                    vals = parts[1].rstrip('";').split(',')
                    if len(vals) >= 32:
                        results[var_name] = {
                            'name': vals[0],
                            'open': float(vals[1]) if vals[1] else 0,
                            'prev_close': float(vals[2]) if vals[2] else 0,
                            'price': float(vals[3]) if vals[3] else 0,
                            'high': float(vals[4]) if vals[4] else 0,
                            'low': float(vals[5]) if vals[5] else 0,
                            'volume': int(vals[8]) if vals[8] else 0,
                            'amount': float(vals[9]) if vals[9] else 0,
                        }
                break
            except Exception:
                if retry < 2:
                    time.sleep(0.5)
                continue
    return results


def check_new_high(sina_code):
    """检查单只股票是否为百日新高"""
    try:
        url = (f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php'
               f'/CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen=110')
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        data = json.loads(resp.read().decode('gbk'))
        if not data or len(data) < 20:
            return None

        highs = [float(d['high']) for d in data if d.get('high')]
        closes = [float(d['close']) for d in data if d.get('close')]
        volumes = [float(d.get('volume', 0)) for d in data]
        if len(highs) < 2:
            return None

        today = data[-1]
        today_high = float(today['high'])
        today_close = float(today['close'])
        hundred_day_high = max(highs[:-1])
        if today_high < hundred_day_high or hundred_day_high <= 0:
            return None

        # 涨幅
        prev_close = closes[-2] if len(closes) > 1 else today_close
        change_pct = round((today_close - prev_close) / prev_close * 100, 2) if prev_close else 0

        # 量比 (今日量 / 前5日均量)
        today_vol = volumes[-1] if volumes else 0
        avg_vol_5 = sum(volumes[-6:-1]) / max(len(volumes[-6:-1]), 1) if len(volumes) > 6 else 1
        vol_ratio = round(today_vol / max(avg_vol_5, 1), 2) if avg_vol_5 > 0 else 1

        # 是否首次新高 (前5日未创百日新高)
        five_day_highs = highs[-6:-1]
        is_first = today_high > max(five_day_highs) if five_day_highs else True

        return {
            'close': round(today_close, 2),
            'change': change_pct,
            'volume_ratio': vol_ratio,
            'is_first': is_first,
        }
    except Exception:
        return None


# ═══════════════════════════════════════════
#  扫描
# ═══════════════════════════════════════════

def scan_pool(pool, max_workers=8):
    """扫描股票池中的百日新高"""
    now = datetime.now()
    print(f"\n  ═══════════════════════════════════════")
    print(f"   百日新高扫描器 v2 · 实时数据")
    print(f"  ═══════════════════════════════════════")
    print(f"  扫描时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  数据来源: 新浪财经API (实时行情)")

    # Step 1: 批量获取实时行情
    sina_codes = [s[3] for s in pool]
    print(f"  股票池: {len(pool)} 只, 正在获取实时行情...")
    quotes = sina_batch_quote(sina_codes)
    print(f"  获取到 {len(quotes)} 只行情数据")

    # Step 2: 过滤候选 (涨跌幅>0 或 今日最高接近52周高)
    candidates = []
    for code, name, sector, sc in pool:
        q = quotes.get(sc)
        if not q:
            continue
        chg = ((q['price'] - q['prev_close']) / q['prev_close'] * 100) if q['prev_close'] else 0
        if chg > -2:  # 跌幅不超过2%的也检查
            candidates.append((code, name, sector, sc, q, chg))

    print(f"  候选标的: {len(candidates)} 只 (涨跌幅>-2%)")

    # Step 3: 并发检查百日新高
    print(f"  正在检查百日新高 (并发{max_workers}线程)...")
    new_highs = []
    checked = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool_exec:
        fut_map = {pool_exec.submit(check_new_high, sc): (code, name, sector, sc, q)
                   for code, name, sector, sc, q, _ in candidates}
        for f in as_completed(fut_map):
            code, name, sector, sc, q = fut_map[f]
            checked += 1
            if checked % 20 == 0:
                print(f"    进度: {checked}/{len(candidates)}", end='\r')
            result = f.result()
            if result:
                chg = ((q['price'] - q['prev_close']) / q['prev_close'] * 100) if q['prev_close'] else 0
                new_highs.append({
                    'code': code,
                    'name': name,
                    'close': result['close'],
                    'change': result['change'],
                    'volume_ratio': result['volume_ratio'],
                    'is_first': result['is_first'],
                    'sector': sector,
                })

    # 排序
    new_highs.sort(key=lambda x: (not x['is_first'], -x['volume_ratio'], -x['change']))
    return new_highs


# ═══════════════════════════════════════════
#  输出
# ═══════════════════════════════════════════

def print_results(results):
    if not results:
        print("\n  今日未发现百日新高个股")
        return

    first_count = sum(1 for r in results if r['is_first'])
    print(f"\n  ┌─ 扫描结果 ─────────────────────────────┐")
    print(f"  │ 数据日期: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"  │ 发现 {len(results)} 只百日新高标的")
    print(f"  │ ★ 首次新高: {first_count} 只 (重点关注)")
    print(f"  │ 持续新高: {len(results) - first_count} 只")
    print(f"  └────────────────────────────────────────┘\n")

    print(f"  {'代码':<12} {'名称':<8} {'收盘':<8} {'涨幅%':<6} {'量比':<6} {'状态':<10} {'板块':<8}")
    print(f"  {'─'*58}")
    for r in results[:30]:
        tag = "★ 首次" if r['is_first'] else "持续"
        print(f"  {r['code']:<12} {r['name'][:4]:<8} {r['close']:<8} {r['change']:>+5.1f} {'':<1} {r['volume_ratio']:<5.1f} {tag:<10} {r['sector'][:4]:<8}")

    if len(results) > 30:
        print(f"  ... 还有 {len(results)-30} 只 (见完整文件)")

    # 板块统计
    sectors = {}
    for r in results:
        s = r['sector']
        sectors.setdefault(s, {'total': 0, 'first': 0})
        sectors[s]['total'] += 1
        if r['is_first']:
            sectors[s]['first'] += 1
    if sectors:
        print(f"\n  ┌─ 板块分布 ─────────────────────────────┐")
        for s, v in sorted(sectors.items(), key=lambda x: -x[1]['total']):
            print(f"  │ {s:<8} {v['total']}只 (首次{v['first']}只)")
        print(f"  └────────────────────────────────────────┘")


def print_teaching(results):
    if not results:
        return
    today = datetime.now().strftime('%Y-%m-%d')
    first_count = sum(1 for r in results if r['is_first'])
    print(f"""
  ═══════════════════════════════════════
  📖 百日新高 · 教学讲解
  ═══════════════════════════════════════

  ▎{today} 概况
    百日新高共 {len(results)} 只
    首次新高 {first_count} 只，持续新高 {len(results) - first_count} 只

  ▎为什么要关注首次新高？
    {TEACHING['first_high']['significance']}

  ▎板块效应为什么重要？
    {TEACHING['sector']['significance']}

  ▎今日教学要点""")
    firsts = [r for r in results if r['is_first']]
    if firsts:
        print(f"\n    ★ 重点观察 — 首次新高 ({len(firsts)}只):")
        for r in firsts[:5]:
            print(f"      {r['name'][:4]:<6} ({r['code']:<10}) 涨幅{r['change']:+.1f}%  量比{r['volume_ratio']}  板块:{r['sector']}")
    print(f"""
  ▎操作提示
    1. 看板块: 优先选择板块新高家数最多的板块
    2. 看量比: 1.5-2.5 的健康放量最理想
    3. 看首次: 首次新高比持续新高更有安全边际
""")


def save_results(results):
    now = datetime.now()
    today = now.strftime("%Y%m%d")

    csv_path = f"百日新高_{today}.csv"
    def write_csv(p=None):
        p = p or csv_path
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["代码", "名称", "收盘价", "涨幅%", "量比", "是否首次新高", "板块"])
            for r in results:
                w.writerow([r['code'], r['name'], r['close'], r['change'],
                           r['volume_ratio'], "首次" if r['is_first'] else "持续", r['sector']])
    actual_csv = _try_write(csv_path, write_csv)
    print(f"  >> 已保存: {actual_csv}")

    json_path = f"百日新高_{today}.json"
    def write_json(p=None):
        p = p or json_path
        json_data = {
            "date": now.strftime("%Y-%m-%d"),
            "total": len(results),
            "first_count": sum(1 for r in results if r['is_first']),
            "stocks": results,
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
    actual_json = _try_write(json_path, write_json)
    print(f"  >> 已保存: {actual_json}")

    update_history(results)
    return actual_csv, actual_json


def _try_write(path, write_fn):
    for attempt in range(10):
        try:
            write_fn()
            return path
        except PermissionError:
            time.sleep(0.5)
    base, ext = os.path.splitext(path)
    alt = f"{base}_{datetime.now().strftime('%H%M%S')}{ext}"
    write_fn(alt)
    return alt


def update_history(results):
    hist_file = "百日新高_历史趋势.json"
    record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total": len(results),
        "first_count": sum(1 for r in results if r['is_first']),
    }
    history = []
    if os.path.exists(hist_file):
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            pass
    history = [h for h in history if h.get("date") != record["date"]]
    history.append(record)
    history.sort(key=lambda x: x["date"])
    for attempt in range(5):
        try:
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            print(f"  >> 已更新: {hist_file}")
            return
        except PermissionError:
            time.sleep(0.3)


# ═══════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════

def main():
    is_teach = "--teach" in sys.argv

    results = scan_pool(STOCK_POOL)

    print_results(results)

    if is_teach:
        print_teaching(results)

    if results:
        save_results(results)

    print(f"\n  ✓ 扫描完成\n")


if __name__ == "__main__":
    main()
