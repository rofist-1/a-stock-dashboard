# -*- coding: utf-8 -*-
"""
2026年 百日新高策略回测
====================
1. 下载缺失K线数据 (至2025-01, 保留已有缓存)
2. 逐日扫描百日新高 + 多因子评分
3. 模拟组合买卖
4. 输出 HTML 回测报告

用法: python backtest_2026.py
"""

import os, sys, json, pickle, time, math, io, ssl
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import pandas as pd
import numpy as np
import akshare as ak

# ===== 配置 =====
ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = r'C:\Users\Rofis\Desktop\kline_cache'
STOCK_LIST = os.path.join(ROOT, 'stock_list.json')
SECTOR_FILE = os.path.join(ROOT, 'sector_map.json')
OUTPUT = os.path.join(ROOT, 'backtest_report.html')

DATA_START = '2025-06-01'
BACKTEST_START = '2026-01-05'
BACKTEST_END   = '2026-06-05'

SCORE_THRESHOLD = 50
MAX_ENTRY_CHG   = 7.0
HOLD_DAYS       = 10
STOP_LOSS       = -8.0
MAX_POSITIONS   = 8
POSITION_SIZE   = 0.12

SECTOR_KEYWORDS = {
    '芯片': ['芯片','半导体','集成电路','晶圆','硅片','光刻','中芯','华创','兆易','韦尔','紫光','三安','贝岭','华大'],
    '算力': ['算力','服务器','数据中心','光模块','中科曙光','浪潮','海光'],
    '人工智能': ['人工智能','AI','大模型','智能','海康威视','科大讯飞'],
    '机器人': ['机器人','减速器','伺服','埃斯顿','汇川技术'],
    '通信': ['通信','5G','6G','光通信','中兴通讯','中际旭创','新易盛'],
    '新能源汽车': ['新能源车','电动汽车','锂电','充电桩','比亚迪','赛力斯'],
    '锂电池': ['锂电池','锂矿','碳酸锂','宁德时代','赣锋锂业','天齐锂业'],
    '光伏': ['光伏','太阳能','逆变器','阳光电源','隆基绿能','通威'],
    '军工': ['军工','航天','航空','国防','北斗','中航','航发'],
    '医药': ['医药','医疗','生物','创新药','恒瑞','迈瑞','药明'],
    '消费电子': ['消费电子','手机','面板','显示器','歌尔','立讯精密'],
    '电力': ['电力','能源','电网','长江电力','国电','华能'],
    '环保': ['环保','碳中和','再生'],
    '金融': ['银行','证券','保险','招商银行','中信证券','东方财富'],
    '传媒': ['传媒','游戏','影视','分众','三七'],
}

def get_sector(code, name):
    code6 = code[2:]
    if os.path.exists(SECTOR_FILE):
        try:
            with open(SECTOR_FILE, 'r', encoding='utf-8') as f:
                sm = json.load(f)
            if code6 in sm:
                return sm[code6]
        except: pass
    for sector, kws in SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in name:
                return sector
    return '其他'

def get_hot_sectors(sector_list):
    if not sector_list: return set()
    c = defaultdict(int)
    for s in sector_list: c[s] += 1
    if not c: return set()
    mx = max(c.values())
    return {s for s, v in c.items() if v >= max(3, mx * 0.4)}

# ===== 1. 股票列表 =====
def get_stock_list():
    if os.path.exists(STOCK_LIST):
        with open(STOCK_LIST, 'r', encoding='utf-8') as f:
            return json.load(f)
    print("下载股票列表...")
    df = ak.stock_info_a_code_name()
    stocks = []
    for _, r in df.iterrows():
        c = str(r['code']).strip().zfill(6)
        code = ('sh' if c.startswith('6') else 'sz') + c
        stocks.append({'code': code, 'name': str(r['name'])})
    with open(STOCK_LIST, 'w', encoding='utf-8') as f:
        json.dump(stocks, f, ensure_ascii=False)
    return stocks

# ===== 2. K线下载/更新 =====
def download_one(sym, name=''):
    for _ in range(3):
        try:
            df = ak.stock_zh_a_daily(symbol=sym, adjust='qfq',
                                      start_date='20250101', end_date='20260605')
            if df is None or len(df) < 60:
                return None
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            df['pct_chg'] = df['close'].pct_change() * 100
            df = df.sort_values('date').reset_index(drop=True)
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(os.path.join(CACHE_DIR, f'{sym}.pkl'), 'wb') as f:
                pickle.dump({'date': datetime.now().strftime('%Y-%m-%d'), 'df': df}, f)
            return df
        except Exception as e:
            time.sleep(2)
    return None

def load_data(stock, force=False):
    f = os.path.join(CACHE_DIR, f"{stock['code']}.pkl")
    if not force and os.path.exists(f):
        try:
            with open(f, 'rb') as fp:
                data = pickle.load(fp)
            df = data['df']
            if pd.to_datetime(df['date'].min()) <= pd.Timestamp(DATA_START):
                return df
        except: pass
    df = download_one(stock['code'], stock['name'])
    return df

def fill_missing_data(stocks):
    print(f"\n检查数据覆盖 ({DATA_START} 起)...")
    need_dl = []
    ok_count = 0
    for s in stocks:
        f = os.path.join(CACHE_DIR, f"{s['code']}.pkl")
        if os.path.exists(f):
            try:
                with open(f, 'rb') as fp:
                    data = pickle.load(fp)
                df = data['df']
                if pd.to_datetime(df['date'].min()) <= pd.Timestamp(DATA_START):
                    ok_count += 1
                    continue
            except: pass
        need_dl.append(s)
    print(f"  已有充足数据: {ok_count}/{len(stocks)}")
    if not need_dl:
        return
    print(f"  需补充数据: {len(need_dl)} 只 (8线程)")
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        fut_map = {}
        for s in need_dl:
            fut = pool.submit(download_one, s['code'], s['name'])
            fut_map[fut] = s
            time.sleep(0.02)
        for fut in as_completed(fut_map):
            done += 1
            if done % 500 == 0:
                elapsed = time.time() - t0
                remaining = elapsed / done * (len(need_dl) - done)
                print(f"    {done}/{len(need_dl)} ({elapsed:.0f}s, 预计剩余 {remaining:.0f}s)")
    print(f"  完成! 耗时 {time.time()-t0:.0f}s")

def get_position_params(diff):
    """根据新高-新低差值动态调整仓位 (固定仓位比例)"""
    if diff >= 200:      # 🔥 狂热
        return 6, 0.14, '重仓出击'
    elif diff >= 50:     # ☀️ 强势
        return 4, 0.10, '正常仓位'
    elif diff >= -50:    # 🌥️ 震荡
        return 2, 0.05, '轻仓试探'
    else:                # ❄️ 弱势/冰点
        return 0, 0.0, '空仓休息'

# ===== 3. 回测引擎 =====
def run_backtest(all_kline, sector_map):
    print(f"\n运行回测 ({BACKTEST_START} ~ {BACKTEST_END})...")

    all_dates = set()
    for code, df in all_kline.items():
        for d in df['date'].values:
            d_str = str(d)[:10]
            if BACKTEST_START <= d_str <= BACKTEST_END:
                all_dates.add(d_str)
    trading_days = sorted(all_dates)
    print(f"交易日: {trading_days[0]} ~ {trading_days[-1]}, 共 {len(trading_days)} 天")

    cash = 1_000_000
    positions = []
    closed_trades = []
    equity = []
    daily_log = []  # 每日操作流水

    for di, today in enumerate(trading_days):
        log_buy = []
        log_sell = []
        log_skip = []

        # --- A. 找出今日百日新高 & 百日新低 ---
        high_count = 0
        low_count = 0
        first_count = 0
        prev_highs = set()
        if di > 0:
            prev_day = trading_days[di-1]
            for c, df in all_kline.items():
                if prev_day in df['date'].values:
                    pi = df[df['date'] == prev_day].index[0]
                    if pi >= 100 and df.iloc[pi]['close'] >= df.iloc[pi-100:pi+1]['close'].max():
                        prev_highs.add(c)

        highs = {}
        sector_list = []
        for code, df in all_kline.items():
            if today not in df['date'].values:
                continue
            row = df[df['date'] == today].iloc[0]
            idx = row.name
            if idx < 100:
                continue
            window = df.iloc[idx-100:idx+1]

            is_high = row['close'] >= window['close'].max()
            is_low  = row['close'] <= window['close'].min()
            if is_high:
                high_count += 1
            if is_low:
                low_count += 1
            if not is_high:
                continue

            name = row.get('name', code)
            sector = get_sector(code, name)
            sector_list.append(sector)
            consecutive = 2 if code in prev_highs else 1
            is_first = consecutive <= 1
            if is_first:
                first_count += 1

            vol = row.get('volume', 1)
            avg_vol = df.iloc[max(0,idx-20):idx]['volume'].mean() if idx >= 20 else vol
            vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0

            chg = row.get('pct_chg', 0)
            chg = float(chg) if not pd.isna(chg) else 0

            score = 0
            score += min(vol_ratio * 10, 25)
            score += min(abs(chg) * 2, 30)
            if chg >= 9.5: score += 10
            if is_first: score += 20
            if consecutive >= 3: score += 5
            score = min(score, 100)

            highs[code] = {
                'name': name, 'sector': sector, 'row': row,
                'consecutive': consecutive, 'vol_ratio': vol_ratio,
                'chg': chg, 'score': score, 'is_first': is_first,
            }

        # --- B. 热门板块 ---
        hot = get_hot_sectors(sector_list)
        for h in highs.values():
            if h['sector'] in hot:
                h['score'] = min(h['score'] + 15, 100)

        # --- C. 卖出 ---
        still_held = []
        for p in positions:
            p['days_held'] += 1
            df = all_kline.get(p['code'])
            exit_this = False
            exit_reason = ''
            if df is not None and today in df['date'].values:
                row = df[df['date'] == today].iloc[0]
                cur_price = row['close']
                pnl_pct = (cur_price - p['entry_price']) / p['entry_price'] * 100
                p['pnl_pct'] = pnl_pct
                p['cur_price'] = cur_price
                if p['days_held'] >= HOLD_DAYS:
                    exit_this = True
                    exit_reason = '到期卖出'
                elif pnl_pct <= STOP_LOSS:
                    exit_this = True
                    exit_reason = '止损卖出'
            else:
                exit_this = True
                exit_reason = '数据缺失'

            if exit_this:
                exit_price = p.get('cur_price', p['entry_price'])
                pnl = (exit_price - p['entry_price']) * p['shares']
                pnl_pct = (exit_price / p['entry_price'] - 1) * 100
                cash += exit_price * p['shares']
                closed = {
                    **p, 'exit_date': today, 'exit_price': exit_price,
                    'pnl': round(pnl, 2), 'pnl_pct': round(pnl_pct, 2),
                    'exit_reason': exit_reason,
                }
                closed_trades.append(closed)
                log_sell.append(closed)
            else:
                still_held.append(p)
        positions = still_held

        # --- D. 买入 (动态仓位) ---
        diff = high_count - low_count
        max_pos, pos_size, regime_label = get_position_params(diff)
        available = len(positions)
        to_buy = sorted(
            [h for h in highs.items() if h[1]['score'] >= SCORE_THRESHOLD and h[1]['chg'] < MAX_ENTRY_CHG
             and not any(p['code'] == h[0] for p in positions)],
            key=lambda x: -x[1]['score']
        )[:max_pos - available]

        for code, h in to_buy:
            price = h['row']['close']
            alloc = min(1_000_000 * pos_size, cash)  # 固定仓位比例，现金不足则停
            shares = int(alloc / price / 100) * 100
            if shares < 100: continue
            cost = shares * price
            if cash < cost: continue
            cash -= cost
            pos = {
                'code': code, 'name': h['name'], 'sector': h['sector'],
                'entry_date': today, 'entry_price': price, 'shares': shares,
                'score': round(h['score'], 1), 'days_held': 0,
                'vol_ratio': round(h['vol_ratio'], 2), 'chg': round(h['chg'], 2),
                'is_first': h['is_first'], 'consecutive': h['consecutive'],
                'in_hot_sector': h['sector'] in hot,
            }
            positions.append(pos)
            log_buy.append(pos)

        # --- E. 总资产 ---
        total = cash
        for p in positions:
            df = all_kline.get(p['code'])
            if df is not None and today in df['date'].values:
                row = df[df['date'] == today].iloc[0]
                total += row['close'] * p['shares']
            else:
                total += p['entry_price'] * p['shares']
        equity.append((today, round(total, 2)))
        prev_total = equity[-2][1] if len(equity) >= 2 else total
        daily_pnl_pct = (total / prev_total - 1) * 100

        # --- F. 记录每日流水 ---
        daily_log.append({
            'date': today,
            'high_count': high_count,
            'low_count': low_count,
            'diff': diff,
            'first_count': first_count,
            'daily_pnl_pct': round(daily_pnl_pct, 2),
            'total_asset': round(total, 2),
            'regime': regime_label,
            'buys': log_buy,
            'sells': log_sell,
            'position_count': len(positions),
        })

        if (di + 1) % 10 == 0 or di == 0 or di == len(trading_days) - 1:
            print(f"  {today} | 新高: {high_count} (首次{first_count}) | "
                  f"买入: {len(log_buy)} 卖出: {len(log_sell)} | "
                  f"持仓: {len(positions)} | 资产: ¥{total:,.0f}")

    # 强制平仓
    for p in positions:
        exit_price = p.get('cur_price', p['entry_price'])
        pnl = (exit_price - p['entry_price']) * p['shares']
        pnl_pct = (exit_price / p['entry_price'] - 1) * 100
        closed_trades.append({
            **p, 'exit_date': BACKTEST_END, 'exit_price': exit_price,
            'pnl': round(pnl, 2), 'pnl_pct': round(pnl_pct, 2),
            'exit_reason': '期末强制平仓',
        })
        cash += exit_price * p['shares']

    return equity, closed_trades, cash, daily_log

# ===== 4. 绩效分析 =====
def analyze(equity, trades):
    if not equity: return {}
    vals = [v for _, v in equity]
    dates = [d for d, _ in equity]

    init, final = vals[0], vals[-1]
    total_ret = (final / init - 1) * 100
    days = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days
    ann_ret = ((final / init) ** (365 / max(days, 1)) - 1) * 100 if days > 0 else 0

    peak = vals[0]; mdd = 0; dd_start = dates[0]; mdd_s = mdd_e = dates[0]
    for i, v in enumerate(vals):
        if v > peak: peak = v; dd_start = dates[i]
        dd = (peak - v) / peak * 100
        if dd > mdd: mdd = dd; mdd_s = dd_start; mdd_e = dates[i]

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0

    daily_r = [vals[i]/vals[i-1]-1 for i in range(1, len(vals)) if vals[i-1]>0]
    sharpe = np.mean(daily_r)/np.std(daily_r)*np.sqrt(252) if daily_r and np.std(daily_r)>0 else 0

    total_pnl = sum(t['pnl'] for t in trades)

    # 按板块统计
    sector_pnl = defaultdict(float)
    sector_wins = defaultdict(int)
    sector_total = defaultdict(int)
    for t in trades:
        s = t.get('sector', '其他')
        sector_pnl[s] += t['pnl']
        sector_total[s] += 1
        if t['pnl'] > 0: sector_wins[s] += 1

    return {
        'init': init, 'final': final, 'total_ret': total_ret, 'ann_ret': ann_ret,
        'mdd': mdd, 'mdd_s': mdd_s, 'mdd_e': mdd_e,
        'win_rate': win_rate, 'total_trades': len(trades),
        'wins': len(wins), 'losses': len(losses),
        'avg_win': avg_win, 'avg_loss': avg_loss,
        'sharpe': sharpe, 'total_pnl': total_pnl,
        'dates': dates, 'values': vals,
        'sector_pnl': dict(sector_pnl),
        'sector_wins': dict(sector_wins),
        'sector_total': dict(sector_total),
    }


def regime_analysis(daily_log, trades, equity):
    """按 新高-新低 差值分组，统计各阶段的交易胜率和收益率"""
    if not daily_log or not trades:
        return []

    # 给每笔交易打上所属阶段的标签
    trade_by_entry = defaultdict(list)
    for t in trades:
        trade_by_entry[t['entry_date']].append(t)

    # 对每天，记录该日的 diff 和当日/未来收益
    regimes = []  # [(diff, daily_pnl, trade_count, win_count)]
    for d in daily_log:
        diff = d['diff']
        pnl = d['daily_pnl_pct']
        day_trades = trade_by_entry.get(d['date'], [])
        wins = sum(1 for t in day_trades if t['pnl'] > 0)
        regimes.append({
            'date': d['date'],
            'diff': diff,
            'high': d['high_count'],
            'low': d['low_count'],
            'pnl': pnl,
            'trades': len(day_trades),
            'wins': wins,
        })

    # 按差值分桶
    buckets = [
        (-99999, -200, '❄️ 冰点', '新高远少于新低'),
        (-200, -50, '🌧️ 弱势', '新高少于新低'),
        (-50, 50, '🌥️ 震荡', '新高新低相近'),
        (50, 200, '☀️ 强势', '新多多于新低'),
        (200, 99999, '🔥 狂热', '新低远多于新低'),
    ]
    results = []
    for lo, hi, label, desc in buckets:
        days = [r for r in regimes if lo <= r['diff'] < hi]
        if not days:
            continue
        avg_diff = np.mean([r['diff'] for r in days])
        avg_pnl = np.mean([r['pnl'] for r in days])
        total_trades = sum(r['trades'] for r in days)
        total_wins = sum(r['wins'] for r in days)
        win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
        results.append({
            'label': label, 'desc': desc,
            'days': len(days),
            'avg_diff': round(avg_diff, 1),
            'avg_pnl': round(avg_pnl, 2),
            'trades': total_trades,
            'wins': total_wins,
            'win_rate': round(win_rate, 1),
        })

    return results

# ===== 5. HTML报告 =====
def gen_report(stats, trades, daily_log, regimes=None):
    v = stats
    ret_cls = 'up' if v['total_ret'] >= 0 else 'down'

    # 按时间排序的交易表
    rows_time = ''
    for t in sorted(trades, key=lambda x: x['entry_date']):
        c = t['code'][2:] if len(t['code']) > 6 else t['code']
        cls = 'up' if t['pnl'] > 0 else 'down'
        hold = (pd.Timestamp(t['exit_date']) - pd.Timestamp(t['entry_date'])).days
        rows_time += f'<tr><td>{t["entry_date"]}</td><td>{c}</td><td>{t["name"]}</td>'
        rows_time += f'<td>{t["sector"]}</td><td>¥{t["entry_price"]:.2f}</td><td>¥{t["exit_price"]:.2f}</td>'
        rows_time += f'<td>{hold}天</td><td>{t["exit_reason"]}</td>'
        rows_time += f'<td class="{cls}">{t["pnl_pct"]:+.2f}%</td><td class="{cls}">¥{t["pnl"]:+,.0f}</td></tr>'

    # 按盈亏排序
    rows_pnl = ''
    for t in sorted(trades, key=lambda x: -abs(x['pnl'])):
        c = t['code'][2:] if len(t['code']) > 6 else t['code']
        cls = 'up' if t['pnl'] > 0 else 'down'
        rows_pnl += f'<tr><td>{t["entry_date"]}</td><td>{c}</td><td>{t["name"]}</td>'
        rows_pnl += f'<td>¥{t["entry_price"]:.2f}</td><td>¥{t["exit_price"]:.2f}</td>'
        rows_pnl += f'<td>{t["score"]}</td><td class="{cls}">{t["pnl_pct"]:+.2f}%</td><td class="{cls}">¥{t["pnl"]:+,.0f}</td></tr>'

    # 市场阶段分析
    regime_rows = ''
    regime_best = ''
    regime_worst = ''
    if regimes:
        best = max(regimes, key=lambda r: r['win_rate'])
        worst = min(regimes, key=lambda r: r['win_rate'])
        for r in regimes:
            cls = 'up' if r['avg_pnl'] >= 0 else 'down'
            wcls = 'up' if r['win_rate'] >= 50 else 'down'
            bar = f'<div style="width:{r["win_rate"]}%;height:6px;background:{"#22c55e" if r["win_rate"]>=50 else "#ef4444"};border-radius:3px"></div>'
            regime_rows += f'<tr><td>{r["label"]}</td><td>{r["desc"]}</td>'
            regime_rows += f'<td>{r["days"]}</td><td>差值{r["avg_diff"]:+.0f}</td>'
            regime_rows += f'<td class="{cls}">{r["avg_pnl"]:+.2f}%</td>'
            regime_rows += f'<td class="{wcls}">{r["win_rate"]:.0f}%</td><td>{bar}</td></tr>'
        regime_best = f'最佳阶段: {best["label"]} 胜率{best["win_rate"]:.0f}% |'
        regime_worst = f'需休息: {worst["label"]} 胜率{worst["win_rate"]:.0f}%'

    # 每日操作流水
    daily_rows = ''
    for d in daily_log:
        buys = d['buys']
        sells = d['sells']
        buy_txt = ' '.join(f'{b["code"][2:]}{b["name"]}({b["score"]}分)' for b in buys) if buys else '—'
        sell_txt = ' '.join(f'{s["code"][2:]}{s["name"]}({s["pnl_pct"]:+.1f}%)' for s in sells) if sells else '—'
        pnl_cls = 'up' if d['daily_pnl_pct'] >= 0 else 'down'
        d_diff = d['diff']
        daily_rows += f'<tr><td>{d["date"]}</td><td>{d["high_count"]}</td><td>{d["low_count"]}</td>'
        daily_rows += f'<td>{"%+d" % d_diff}</td>'
        daily_rows += f'<td class="{pnl_cls}">{d["daily_pnl_pct"]:+.2f}%</td>'
        daily_rows += f'<td style="color:#22c55e">{buy_txt}</td>'
        daily_rows += f'<td style="color:#ef4444">{sell_txt}</td>'
        daily_rows += f'<td>{d["position_count"]}</td></tr>'

    # 板块盈亏
    sector_rows = ''
    for s in sorted(v['sector_pnl'].keys(), key=lambda x: -v['sector_pnl'][x]):
        pnl = v['sector_pnl'][s]
        w = v['sector_wins'].get(s, 0)
        t = v['sector_total'].get(s, 0)
        cls = 'up' if pnl > 0 else 'down'
        sector_rows += f'<tr><td>{s}</td><td>{t}</td><td class="{cls}">¥{pnl:+,.0f}</td><td>{w/t*100:.0f}%</td></tr>'

    # 资金曲线 SVG
    vals = v['values']; dates = v['dates']
    w = max(600, len(vals) * 2)
    h = 280
    mn, mx = min(vals), max(vals)
    rng = mx - mn if mx > mn else 1
    pts = []
    for i, (d, val) in enumerate(zip(dates, vals)):
        x = 40 + i * (w - 80) / len(vals)
        y = h - 25 - (val - mn) / rng * (h - 50)
        pts.append(f'{x:.1f},{y:.1f}')

    # Y轴刻度
    yticks = ''
    for i in range(5):
        val = mn + rng * i / 4
        y = h - 25 - (val - mn) / rng * (h - 50)
        yticks += f'<text x="35" y="{y+4}" fill="#64748b" font-size="10" text-anchor="end">¥{val:,.0f}</text>'

    polyline = ' '.join(pts)

    # 最大回撤标注
    mdd_idx_s = dates.index(v['mdd_s']) if v['mdd_s'] in dates else 0
    mdd_idx_e = dates.index(v['mdd_e']) if v['mdd_e'] in dates else len(dates)-1
    x_mdd_s = 40 + mdd_idx_s * (w - 80) / len(dates)
    x_mdd_e = 40 + mdd_idx_e * (w - 80) / len(dates)
    y_mdd_s = h - 25 - (vals[mdd_idx_s] - mn) / rng * (h - 50)
    y_mdd_e = h - 25 - (vals[mdd_idx_e] - mn) / rng * (h - 50)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>百日新高策略 2026回测报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Microsoft YaHei','PingFang SC',sans-serif;background:#0f172a;color:#e2e8f0;padding:2rem 1rem;max-width:1400px;margin:0 auto}}
h1{{color:#f97316;font-size:1.8rem;margin-bottom:.3rem}}
.sub{{color:#64748b;margin-bottom:2rem}}
.card{{background:#1e293b;border-radius:12px;padding:1.5rem;margin-bottom:1.5rem;box-shadow:0 4px 12px rgba(0,0,0,.3)}}
.card2{{background:#1e293b;border-radius:12px;padding:1.5rem;margin-bottom:1.5rem;overflow-x:auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem}}
.stat .label{{color:#94a3b8;font-size:.8rem}}
.stat .val{{font-size:1.6rem;font-weight:700;line-height:1.4}}
.stat .subval{{font-size:.8rem;color:#64748b}}
.up{{color:#22c55e}} .down{{color:#ef4444}}
table{{width:100%;border-collapse:collapse;font-size:.8rem;min-width:600px}}
th{{color:#94a3b8;padding:.5rem .4rem;text-align:right;border-bottom:2px solid #334155;position:sticky;top:0;background:#1e293b;white-space:nowrap}}
td{{padding:.4rem;text-align:right;border-bottom:1px solid #0f172a;white-space:nowrap}}
tr:hover td{{background:#334155}}
.table-wrap{{max-height:500px;overflow-y:auto}}
.table-wrap-full{{overflow-x:auto}}
.section-title{{color:#f97316;margin-bottom:.8rem;font-size:1.1rem;display:flex;align-items:center;gap:1rem}}
.tabs{{display:flex;gap:0;margin-bottom:1rem}}
.tab{{padding:.5rem 1rem;cursor:pointer;border-radius:6px 6px 0 0;background:#334155;color:#94a3b8;font-size:.8rem}}
.tab.active{{background:#f97316;color:#fff}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}
.stats-grid{{display:flex;gap:2rem;flex-wrap:wrap}}
.stats-grid>div{{flex:1;min-width:200px}}
.chart-box{{width:100%;overflow-x:auto}}
.badge{{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.7rem;margin-left:3px}}
.badge-hot{{background:#f97316;color:#fff}}
.badge-first{{background:#22c55e;color:#fff}}
.daily-cell{{max-width:250px;overflow:hidden;text-overflow:ellipsis}}
</style></head>
<body>
<h1>📊 百日新高策略 · 2026年回测</h1>
<p class="sub">{v['dates'][0]} ~ {v['dates'][-1]} | 初始资金 ¥{v['init']:,.0f}</p>

<div class="card">
<div class="grid">
  <div class="stat"><div class="val {ret_cls}">{v['total_ret']:+.2f}%</div><div class="label">总收益率</div></div>
  <div class="stat"><div class="val">{v['ann_ret']:+.2f}%</div><div class="label">年化收益率</div></div>
  <div class="stat"><div class="val down">{v['mdd']:.2f}%</div><div class="label">最大回撤 <span class="subval">{v['mdd_s']}~{v['mdd_e']}</span></div></div>
  <div class="stat"><div class="val">{v['sharpe']:.2f}</div><div class="label">夏普比率</div></div>
  <div class="stat"><div class="val">{v['win_rate']:.1f}%</div><div class="label">胜率 <span class="subval">{v['wins']}/{v['total_trades']}</span></div></div>
  <div class="stat"><div class="val">{v['total_trades']}</div><div class="label">交易次数</div></div>
  <div class="stat"><div class="val {ret_cls}">¥{v['total_pnl']:+,.0f}</div><div class="label">净利润</div></div>
  <div class="stat"><div class="val up">¥{v['avg_win']:+,.0f}</div><div class="label">平均盈利</div></div>
</div></div>

<div class="card">
<div class="section-title">📈 资金曲线</div>
<div class="chart-box">
<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" fill="#0f172a" rx="4"/>
  {yticks}
  <polyline points="{polyline}" fill="none" stroke="#f97316" stroke-width="2"/>
  <line x1="{x_mdd_s}" y1="{y_mdd_s}" x2="{x_mdd_e}" y2="{y_mdd_e}" stroke="#ef4444" stroke-width="1" stroke-dasharray="4,3"/>
  <text x="{x_mdd_s}" y="{y_mdd_s-8}" fill="#ef4444" font-size="10">↘ 最大回撤 {v['mdd']:.1f}%</text>
</svg></div></div>

<div class="card">
<div class="section-title">📋 交易记录</div>
<div class="tabs">
  <div class="tab active" onclick="switchTab('tab-time')">按时间顺序</div>
  <div class="tab" onclick="switchTab('tab-pnl')">按盈亏排序</div>
</div>
<div id="tab-time" class="tab-content active">
<div class="table-wrap"><table><thead><tr>
  <th>买入日</th><th>代码</th><th>名称</th><th>板块</th><th>买入价</th><th>卖出价</th><th>持仓</th><th>理由</th><th>收益率</th><th>盈亏</th>
</tr></thead><tbody>{rows_time}</tbody></table></div></div>
<div id="tab-pnl" class="tab-content">
<div class="table-wrap"><table><thead><tr>
  <th>买入日</th><th>代码</th><th>名称</th><th>买入价</th><th>卖出价</th><th>评分</th><th>收益率</th><th>盈亏</th>
</tr></thead><tbody>{rows_pnl}</tbody></table></div></div></div>

<div class="card">
<div class="section-title">📅 每日操作流水</div>
<div class="table-wrap" style="max-height:400px">
<table><thead><tr>
  <th>日期</th><th>新高</th><th>新低</th><th>差值</th><th>当日收益</th><th style="color:#22c55e">买入</th><th style="color:#ef4444">卖出</th><th>持仓</th>
</tr></thead><tbody>{daily_rows}</tbody></table></div></div>

<div class="card">
<div class="section-title">📊 市场阶段分析 (按新高-新低差值分组)</div>
<p style="color:#64748b;font-size:.85rem;margin-bottom:1rem">{regime_best} {regime_worst}</p>
<table><thead><tr>
  <th>阶段</th><th>描述</th><th>天数</th><th>平均差值</th><th>日均收益</th><th>胜率</th><th>分布</th>
</tr></thead><tbody>{regime_rows}</tbody></table></div>

<div class="card2">
<div class="section-title">🏭 板块盈亏</div>
<table><thead><tr>
  <th>板块</th><th>交易次数</th><th>净利润</th><th>胜率</th>
</tr></thead><tbody>{sector_rows}</tbody></table></div>

<h1 style="font-size:.9rem;color:#64748b;text-align:center;margin-top:2rem">
由 百日新高系统 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}</h1>

<script>
function switchTab(id) {{
  document.querySelectorAll('.tab-content').forEach(e => e.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(e => e.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}
</script>
</body></html>'''
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n报告已生成: {OUTPUT}")

# ===== Main =====
def main():
    t_start = time.time()
    print("=" * 50)

    print("股票列表...")
    stocks = get_stock_list()
    print(f"  {len(stocks)} 只")

    fill_missing_data(stocks)

    print("\n加载K线数据到内存...")
    all_kline = {}
    for s in stocks:
        f = os.path.join(CACHE_DIR, f"{s['code']}.pkl")
        if os.path.exists(f):
            try:
                with open(f, 'rb') as fp:
                    data = pickle.load(fp)
                df = data['df']
                if 'name' not in df.columns:
                    df['name'] = s['name']
                all_kline[s['code']] = df
            except: pass
    print(f"  加载 {len(all_kline)} 只")

    equity, trades, final_cash, daily_log = run_backtest(all_kline, get_sector)

    stats = analyze(equity, trades)
    stats['final'] = final_cash

    regimes = regime_analysis(daily_log, trades, equity)

    print(f"\n{'='*50}")
    print(f"  回测结果")
    print(f"{'='*50}")
    print(f"  初始资金: ¥{stats['init']:,.0f}")
    print(f"  最终资产: ¥{stats['final']:,.0f}")
    print(f"  总收益率: {stats['total_ret']:+.2f}%")
    print(f"  年化收益: {stats['ann_ret']:+.2f}%")
    print(f"  最大回撤: {stats['mdd']:.2f}%  ({stats['mdd_s']} ~ {stats['mdd_e']})")
    print(f"  夏普比率: {stats['sharpe']:.2f}")
    print(f"  胜率:     {stats['win_rate']:.1f}% ({stats['wins']}/{stats['total_trades']})")
    print(f"  净利润:   ¥{stats['total_pnl']:+,.0f}")
    print(f"{'='*50}")
    print(f"\n市场阶段分析 (按新高-新低差值):")
    for r in regimes:
        arrow = '⬆' if r['avg_pnl'] > 0 else '⬇'
        print(f"  {r['label']} (差值{r['avg_diff']:+.0f}) {r['days']}天 | "
              f"日均收益{r['avg_pnl']:+.2f}%{arrow} | "
              f"胜率{r['win_rate']:.1f}% ({r['wins']}/{r['trades']})")

    gen_report(stats, trades, daily_log, regimes)

    print(f"\n总耗时: {time.time()-t_start:.0f} 秒")

if __name__ == '__main__':
    main()
