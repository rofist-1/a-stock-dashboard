# -*- coding: utf-8 -*-
"""
容量核心·回测 v4.0 — 纯条件B策略
=================================================================
变更：
  1. 废除条件A（MA60≤EMA13均线多头回踩）
  2. 仅保留条件B作为唯一入场逻辑，含4项子条件：
     B1: MA60 > EMA13 (空头排列) 且 (MA60-EMA13)/MA60 < 3%
     B2: 信号日放量突破EMA13 (close>EMA13*1.01, vol>=vol5*1.5)
     B3: 入场价 >= MA60 * 0.98 (位置安全垫)
     B4: 板块热度 (三选一)

运行:
  python backtest_v3_akshare.py --run            # v4纯条件B
  python backtest_v3_akshare.py --old            # 原版入场(对比)
  python backtest_v3_akshare.py --compare        # 原版 vs v4
  python backtest_v3_akshare.py --list           # 只列信号
"""

import sys, os, json, math, pickle, glob, pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean, stdev

_script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_script_dir).startswith('百日新高'):
    DATA_DIR = _script_dir
else:
    DATA_DIR = os.path.join(_script_dir, '百日新高系统')
    if not os.path.isdir(DATA_DIR):
        DATA_DIR = _script_dir

OUTPUT_PATH = os.path.join(DATA_DIR, '回测结果_v4.json')

# ─── 工具函数 ───────────────────────────────────────────────

def calc_ema(vals, n):
    if len(vals) < n: return None
    k = 2 / (n + 1)
    e = sum(vals[-n:]) / n
    for v in vals[-(n-1):]:
        e = v * k + e * (1 - k)
    return e

def calc_sma(vals, n):
    if len(vals) < n: return None
    return sum(vals[-n:]) / n

def calc_atr(rows, n=14):
    if len(rows) < n + 1: return None
    trs = []
    for i in range(-n, 0):
        h, l, pc = rows[i]['high'], rows[i]['low'], rows[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)

def annualized_return(total_r, days):
    if days <= 0: return 0.0
    return (1 + total_r) ** (365 / days) - 1

def max_drawdown(equity_curve):
    peak = equity_curve[0]
    mdd = 0.0
    for v in equity_curve:
        if v > peak: peak = v
        dd = (peak - v) / peak
        if dd > mdd: mdd = dd
    return mdd

def sharpe_ratio(daily_returns, rf=0.02):
    if len(daily_returns) < 2: return 0.0
    avg_r = mean(daily_returns)
    std_r = stdev(daily_returns)
    if std_r == 0: return 0.0
    return (avg_r - rf/252) / std_r * math.sqrt(252)

# ─── 数据加载 ────────────────────────────────────────────────

def load_json_signals():
    stocks = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.startswith('底部放量_') or not fname.endswith('.json'):
            continue
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.getsize(fpath) < 100:
            continue
        try:
            data = json.load(open(fpath, encoding='utf-8'))
        except:
            continue
        date_str = fname.replace('底部放量_', '').replace('.json', '')
        for s in data.get('stocks', []):
            s['_signal_date'] = date_str
            stocks.append(s)
    return stocks

def load_stock_sector_map():
    """从所有JSON信号文件提取股票→行业映射"""
    mapping = {}
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.startswith('底部放量_') or not fname.endswith('.json'):
            continue
        try:
            data = json.load(open(os.path.join(DATA_DIR, fname), encoding='utf-8'))
        except:
            continue
        for s in data.get('stocks', []):
            code = (s.get('code') or '')[:6]
            sector = s.get('sector') or ''
            if code and sector:
                mapping[code] = sector
    return mapping

def load_kline_cache():
    """从本地 pkl cache 加载K线数据"""
    cache = {}
    cache_dir = os.path.join(DATA_DIR, 'kline_cache')
    if not os.path.isdir(cache_dir):
        return cache
    for fpath in glob.glob(os.path.join(cache_dir, '*.pkl')):
        try:
            fname = os.path.splitext(os.path.basename(fpath))[0]
            raw = pickle.load(open(fpath, 'rb'))
            if not isinstance(raw, dict) or 'df' not in raw:
                continue
            df = raw['df']
            if not isinstance(df, pd.DataFrame) or len(df) < 20:
                continue
            rows = []
            for _, r in df.iterrows():
                d = r.get('date', '')
                d_str = str(d)[:10].replace('-', '') if pd.notna(d) else ''
                rows.append({
                    'date': d_str,
                    'close': float(r.get('close', 0)),
                    'high': float(r.get('high', 0)),
                    'low': float(r.get('low', 0)),
                    'open': float(r.get('open', 0)),
                    'volume': float(r.get('volume', 0)),
                    'amount': float(r.get('amount', 0)),
                })
            code6 = fname[2:] if len(fname) > 2 and fname[:2] in ('sh','sz') else fname
            cache[code6] = rows
        except:
            pass
    return cache

# ─── 行业热度聚合 ────────────────────────────────────────────

def compute_sector_heat(cache, sector_map, date_str, lookback=5):
    """
    计算指定日期各行业热度。
    返回 dict[sector] = {pct_chg, turnover_pct, up_ratio, pct_chg_rank}
    """
    sector_stocks = defaultdict(list)
    total_market_amount = 0

    for code, klines in cache.items():
        sector = sector_map.get(code)
        if not sector or len(klines) < 60:
            continue
        idx = next((i for i, k in enumerate(klines) if k['date'] == date_str), None)
        if idx is None or idx < 1:
            continue
        prev = klines[idx-1]
        row = klines[idx]
        pct = (row['close'] - prev['close']) / prev['close'] * 100 if prev['close'] > 0 else 0
        sector_stocks[sector].append({
            'pct': pct,
            'amount': row.get('amount', 0),
            'close': row['close'],
        })
        total_market_amount += row.get('amount', 0)

    result = {}
    for sector, stocks in sector_stocks.items():
        if len(stocks) < 1:
            continue
        avg_pct = mean(s['pct'] for s in stocks)
        sector_amount = sum(s['amount'] for s in stocks)
        turnover_pct = (sector_amount / total_market_amount * 100) if total_market_amount > 0 else 0
        up_count = sum(1 for s in stocks if s['pct'] > 0)
        up_ratio = up_count / len(stocks) * 100
        result[sector] = {
            'pct_chg': round(avg_pct, 2),
            'turnover_pct': round(turnover_pct, 2),
            'up_ratio': round(up_ratio, 1),
            'stock_count': len(stocks),
        }

    # 计算涨幅排名
    ranked = sorted(result.items(), key=lambda x: -x[1]['pct_chg'])
    for rank, (sec_name, _) in enumerate(ranked, 1):
        result[sec_name]['pct_chg_rank'] = rank
        result[sec_name]['total_ranked'] = len(ranked)

    return result

# ─── 信号检测 ────────────────────────────────────────────────

def detect_signals_from_klines(cache, start_date='20260401', end_date='20260625'):
    """全市场检测容量核心信号（不变）"""
    signals = {}
    sd = datetime.strptime(start_date, '%Y%m%d')
    ed = datetime.strptime(end_date, '%Y%m%d')
    all_days = set()
    d = sd
    while d <= ed:
        if d.weekday() < 5:
            all_days.add(d.strftime('%Y%m%d'))
        d += timedelta(days=1)

    total = len(cache)
    found = 0
    for idx, (code, klines) in enumerate(cache.items()):
        if len(klines) < 80:
            continue
        if idx % 500 == 0 and idx > 0:
            print(f'    [{idx}/{total}] 发现 {found} 次信号')

        dates = [k['date'] for k in klines]
        closes = [k['close'] for k in klines]
        amounts = [k.get('amount', 0) for k in klines]
        volumes = [k.get('volume', 0) for k in klines]
        last_signal_date = ''

        for i in range(60, len(klines)):
            d = dates[i]
            if d not in all_days:
                continue
            if amounts[i] < 1e9:
                continue
            if i < 1: continue
            pct_chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if pct_chg < 5:
                continue
            avg_vol = sum(volumes[i-60:i]) / 60
            if avg_vol <= 0: continue
            vol_ratio = volumes[i] / avg_vol
            if vol_ratio < 2:
                continue
            ma60 = sum(closes[i-60:i]) / 60
            pct60 = (closes[i] - ma60) / ma60 * 100
            if not (-15 <= pct60 <= 15):
                continue
            if last_signal_date and (int(d) - int(last_signal_date)) < 5:
                continue

            # 计算信号日的EMA13和5日均量（用于条件B）
            ema13_signal = calc_ema(closes[:i+1], 13)
            vol5 = calc_sma(volumes[:i+1], 5)

            signal = {
                'signal_idx': i,
                'signal_date': d,
                'close': closes[i],
                'ma60': ma60,
                'pct_chg': round(pct_chg, 2),
                'vol_ratio': round(vol_ratio, 2),
                'amount_yi': round(amounts[i] / 1e8, 1),
                'ema13': round(ema13_signal, 4) if ema13_signal else None,
                'vol5': round(vol5, 2) if vol5 else None,
            }
            if code not in signals:
                signals[code] = []
            signals[code].append(signal)
            last_signal_date = d
            found += 1

    return signals

# ─── 入场过滤 v4（纯条件B）────────────────────────────────

def check_v4_entry(klines, entry_idx, signal_info, sector_heat, stock_sector):
    """
    v4 入场条件（全部满足才开仓）：

    B1 - 均线粘合: MA60 > EMA13 且 (MA60-EMA13)/MA60 < 3%
    B2 - 放量突破: 信号日收盘>EMA13*1.01 且 成交量≥5日均量*1.5
    B3 - 安全垫:   入场价 ≥ MA60 * 0.98
    B4 - 板块热度: 任选其一（数据不足时视为通过）
    """
    if entry_idx < 60:
        return False
    closes = [r['close'] for r in klines]
    volumes = [r.get('volume', 0) for r in klines]

    ma60 = calc_sma(closes[:entry_idx+1], 60)
    ema13 = calc_ema(closes[:entry_idx+1], 13)
    if ma60 is None or ema13 is None or ma60 <= 0:
        return False
    entry_price = closes[entry_idx]

    # B1: MA60 > EMA13 且间距 < 3%（分母用MA60）
    gap_pct = (ma60 - ema13) / ma60 * 100
    if not (ma60 > ema13 and gap_pct < 3):
        return False

    # B2: 信号日放量突破EMA13
    sig_ema13 = signal_info.get('ema13')
    sig_close = signal_info.get('close')
    sig_vol5 = signal_info.get('vol5')
    sig_idx = signal_info.get('signal_idx', 0)
    sig_vol = volumes[sig_idx] if sig_idx < len(volumes) else None
    if not (sig_ema13 and sig_close and sig_vol5 and sig_vol):
        return False
    if sig_close <= sig_ema13 * 1.01:
        return False
    if sig_vol < sig_vol5 * 1.5:
        return False

    # B3: 入场价 >= MA60 * 0.98
    if entry_price < ma60 * 0.98:
        return False

    # B4: 板块热度（三选一，数据不足时视为通过）
    sector = stock_sector or ''
    if sector and sector_heat:
        heat = sector_heat.get(sector)
        if heat:
            if heat.get('pct_chg_rank', 99) <= max(6, heat.get('total_ranked', 31) // 5):
                return True
            if heat['turnover_pct'] > 0:
                return True
            if heat['up_ratio'] >= 60:
                return True
            return False
    return True

def find_entry_v4(klines, signal_idx, signal_info, sector_heat_map, stock_sector):
    """
    v4入场扫描：分歧回踩MA60时校验全部B条件。
    不满足则继续往后扫描。
    """
    closes = [r['close'] for r in klines]
    for i in range(signal_idx + 1, len(klines)):
        if i < 60: continue
        ma60 = calc_sma(closes[:i+1], 60)
        if ma60 is None: continue
        pct60 = (closes[i] - ma60) / ma60 * 100
        if not (-3 <= pct60 <= 3):
            continue
        prev_vols = [klines[j].get('volume', 1) for j in range(max(0,i-20), i)]
        vol_ratio = klines[i].get('volume', 1) / (mean(prev_vols) or 1)
        if vol_ratio >= 1.5:
            continue
        if check_v4_entry(klines, i, signal_info, sector_heat_map, stock_sector):
            return i
        continue
    return None

# ─── 旧版入场（原find_entry，用于对比）────────────────────

def find_entry_old(klines, signal_idx):
    """原版：分歧回踩MA60(-3%~+3%) + 缩量"""
    for i in range(signal_idx + 1, len(klines)):
        if i < 60: continue
        closes = [r['close'] for r in klines]
        ma60 = calc_sma(closes[:i+1], 60)
        if ma60 is None: continue
        pct60 = (closes[i] - ma60) / ma60 * 100
        if -3 <= pct60 <= 3:
            prev_vols = [klines[j].get('volume', 1) for j in range(max(0,i-20), i)]
            vol_ratio = klines[i].get('volume', 1) / (mean(prev_vols) or 1)
            if vol_ratio < 1.5:
                return i
    return None

# ─── 持仓管理 ────────────────────────────────────────────────

def run_trade(klines, entry_idx, market_state='oscillating'):
    closes = [r['close'] for r in klines]
    entry_price = closes[entry_idx]
    entry_date = klines[entry_idx].get('date', '')
    position = 2
    exit_idx = None
    exit_reason = ''
    half_sold = False

    for i in range(entry_idx + 1, len(klines)):
        if i < 13: continue
        e5 = calc_ema(closes[:i+1], 5)
        e13 = calc_ema(closes[:i+1], 13)
        atr14 = calc_atr(klines[:i+1], 14)
        if None in (e5, e13, atr14): continue

        buff = atr14 * 0.5
        below_e5 = closes[i] < e5 - buff
        below_e13 = closes[i] < e13

        if market_state == 'uptrend':
            if below_e5 and position == 2:
                position = 1; half_sold = True
            if below_e13:
                exit_idx = i; exit_reason = '破EMA13清仓'; break
        elif market_state == 'oscillating':
            if below_e5 and position == 2:
                if i + 1 < len(klines):
                    nxt_c = closes[i+1]
                    nxt_v = klines[i+1].get('volume', 0)
                    avg_v = mean([klines[j].get('volume', 1) for j in range(max(0,i-4), i+1)])
                    if nxt_c < e5 - buff or (nxt_v > avg_v * 1.3 and nxt_c < e5):
                        position = 1; half_sold = True
            if below_e13:
                exit_idx = i; exit_reason = '震荡破EMA13'; break
        else:
            if below_e5:
                exit_idx = i; exit_reason = '防御破EMA5清仓'; break
            if below_e13:
                exit_idx = i; exit_reason = '防御破EMA13'; break

        if i - entry_idx > 60:
            exit_idx = i; exit_reason = '超60日平仓'; break

    if exit_idx is None:
        exit_idx = len(klines) - 1
        exit_reason = '期末平仓'

    exit_price = closes[exit_idx]
    exit_date = klines[exit_idx].get('date', '')
    hold_days = exit_idx - entry_idx

    if half_sold:
        half_idx = None
        for j in range(entry_idx + 1, exit_idx + 1):
            if j < 5: continue
            e5_j = calc_ema(closes[:j+1], 5)
            if e5_j and closes[j] < e5_j:
                half_idx = j; break
        if half_idx:
            hp = closes[half_idx]
            pnl_half = (hp - entry_price) / entry_price
            pnl_rest = (exit_price - entry_price) / entry_price
            total_pnl = pnl_half * 0.5 + pnl_rest * 0.5
        else:
            total_pnl = (exit_price - entry_price) / entry_price
    else:
        total_pnl = (exit_price - entry_price) / entry_price

    return {
        'entry_date': entry_date,
        'exit_date': exit_date,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'pnl_pct': round(total_pnl * 100, 2),
        'exit_reason': exit_reason,
        'hold_days': hold_days,
        'half_sold': half_sold,
    }

# ─── 回测主函数 ──────────────────────────────────────────────

def run_backtest(signals_dict, kline_cache, sector_map, use_v4_filter=False):
    """
    回测主循环。

    use_v4_filter=True  → v4纯条件B
    use_v4_filter=False → 原版入场（对比基准）
    """
    trades = []
    v4_stats = {'passed': 0, 'failed': 0, 'total_checked': 0}

    sector_heat_cache = {}

    for code, signal_list in signals_dict.items():
        klines = kline_cache.get(code, [])
        if len(klines) < 80:
            continue

        stock_sector = sector_map.get(code, '')

        for sig in signal_list:
            sig_idx = sig['signal_idx']
            if sig_idx >= len(klines) - 3:
                continue

            if not use_v4_filter:
                entry_idx = find_entry_old(klines, sig_idx)
                if entry_idx is None:
                    continue
                trade = run_trade(klines, entry_idx, 'oscillating')
                trade['code'] = code
                trade['signal_date'] = sig['signal_date']
                trade['signal_pct_chg'] = sig['pct_chg']
                trade['signal_amount_yi'] = sig['amount_yi']
                trades.append(trade)
                continue

            # ====== v4 ======
            v4_stats['total_checked'] += 1

            sig_date = sig['signal_date']
            if sig_date not in sector_heat_cache:
                sector_heat_cache[sig_date] = compute_sector_heat(
                    kline_cache, sector_map, sig_date
                )
            heat = sector_heat_cache[sig_date]

            entry_idx = find_entry_v4(klines, sig_idx, sig, heat, stock_sector)

            if entry_idx is None:
                v4_stats['failed'] += 1
                continue

            v4_stats['passed'] += 1

            trade = run_trade(klines, entry_idx, 'oscillating')
            trade['code'] = code
            trade['signal_date'] = sig['signal_date']
            trade['signal_pct_chg'] = sig['pct_chg']
            trade['signal_amount_yi'] = sig['amount_yi']
            trades.append(trade)

    return trades, v4_stats

# ─── 统计 ─────────────────────────────────────────────────────

def compute_stats(trades, signals_dict):
    if not trades:
        return None
    trades_sorted = sorted(trades, key=lambda t: t['exit_date'])
    pnls = [t['pnl_pct'] / 100 for t in trades_sorted]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(trades)
    avg_win = mean(wins) * 100 if wins else 0
    avg_loss = mean(losses) * 100 if losses else 0
    profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf')

    equity = [1.0]
    for p in pnls:
        equity.append(equity[-1] * (1 + p))
    total_return = equity[-1] - 1
    mdd = max_drawdown(equity)
    avg_hold = mean([t['hold_days'] for t in trades])

    date0 = min(t['signal_date'] for t in trades)
    date1 = max((t['exit_date'] or t['signal_date']) for t in trades)
    dr_days = max((datetime.strptime(date1,'%Y%m%d') - datetime.strptime(date0,'%Y%m%d')).days, 30)
    ann_ret = annualized_return(total_return, dr_days)

    daily_r = []
    for t in trades:
        if t['hold_days'] > 0:
            daily_r.append(t['pnl_pct'] / 100 / t['hold_days'])
    sr = sharpe_ratio(daily_r) if daily_r else 0

    # 早夭单统计
    early3 = [t for t in trades if t['hold_days'] < 3]
    early7 = [t for t in trades if t['hold_days'] < 7]

    return {
        'total_signals': sum(len(v) for v in signals_dict.values()),
        'total_trades': len(trades),
        'win_rate': round(win_rate*100, 1),
        'avg_win_pct': round(avg_win, 2),
        'avg_loss_pct': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2),
        'total_return_pct': round(total_return*100, 2),
        'max_drawdown_pct': round(mdd*100, 2),
        'sharpe_ratio': round(sr, 2),
        'avg_hold_days': round(avg_hold, 1),
        'early_exit_lt3d': len(early3),
        'early_exit_lt3d_pct': round(len(early3)/len(trades)*100, 1),
        'early_exit_lt7d': len(early7),
        'early_exit_lt7d_pct': round(len(early7)/len(trades)*100, 1),
        'date_range': f'{date0} ~ {date1}',
    }

# ─── 输出 ─────────────────────────────────────────────────────

def print_stats(stats, label=''):
    if not stats:
        print(f'\n  [{label}] 无有效交易')
        return
    print(f'\n{"="*55}')
    print(f'  {label}')
    print(f'{"="*55}')
    print(f'  回测期间:    {stats["date_range"]}')
    print(f'  信号总数:    {stats["total_signals"]}')
    print(f'  交易次数:    {stats["total_trades"]}')
    print(f'  胜率:        {stats["win_rate"]}%')
    print(f'  平均盈利:    {stats["avg_win_pct"]}%')
    print(f'  平均亏损:    {stats["avg_loss_pct"]}%')
    print(f'  盈亏比:      {stats["profit_factor"]}')
    print(f'  总收益率:    {stats["total_return_pct"]}%')
    print(f'  最大回撤:    {stats["max_drawdown_pct"]}%')
    print(f'  夏普比率:    {stats["sharpe_ratio"]}')
    print(f'  平均持股:    {stats["avg_hold_days"]} 天')
    print(f'  早夭<3天:    {stats["early_exit_lt3d"]}笔 ({stats["early_exit_lt3d_pct"]}%)')
    print(f'  早夭<7天:    {stats["early_exit_lt7d"]}笔 ({stats["early_exit_lt7d_pct"]}%)')

def print_filter_stats(fs, label=''):
    if not fs or fs['total_checked'] == 0:
        return
    total = fs['total_checked']
    print(f'\n  --- {label} ---')
    print(f'  共检查 {total} 次入场机会')
    print(f'  条件通过: {fs["passed"]} ({round(fs["passed"]/total*100, 1)}%)')
    print(f'  条件未通过: {fs["failed"]} ({round(fs["failed"]/total*100, 1)}%)')

# ─── 主入口 ───────────────────────────────────────────────────

def main():
    print(f'\n{"="*60}')
    print(f'  容量核心·回测 v4.0 (纯条件B)')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*60}')

    use_old = '--old' in sys.argv
    mode = 'list' if '--list' in sys.argv else ('old' if use_old else 'run')
    compare = '--compare' in sys.argv

    print(f'\n[1] 加载kline_cache...')
    cache = load_kline_cache()
    unique = {}
    for k, v in cache.items():
        if k.isdigit() and len(k) == 6:
            unique[k] = v
    print(f'  加载 {len(unique)} 只唯一股票缓存')

    print(f'\n[2] 加载行业映射...')
    sector_map = load_stock_sector_map()
    print(f'  映射 {len(sector_map)} 只股票到行业')

    print(f'\n[3] 检测信号 (20260401~20260625)...')
    signals = detect_signals_from_klines(unique, '20260401', '20260625')
    total_sig = sum(len(v) for v in signals.values())
    print(f'  发现 {total_sig} 次信号, 涉及 {len(signals)} 只股票')

    stats = None
    trades = []

    if mode == 'list':
        return

    if compare:
        print(f'\n[4a] 旧版入场 (原find_entry, 无过滤)...')
        trades_old, _ = run_backtest(signals, unique, sector_map, use_v4_filter=False)
        stats_old = compute_stats(trades_old, signals)
        print_stats(stats_old, '旧版 (原入场逻辑)')

        print(f'\n[4b] v4纯条件B入场...')
        trades_new, fs = run_backtest(signals, unique, sector_map, use_v4_filter=True)
        stats_new = compute_stats(trades_new, signals)
        print_stats(stats_new, 'v4 (纯条件B)')
        print_filter_stats(fs, 'v4入场过滤')

        if stats_old and stats_new:
            print(f'\n{"="*55}')
            print(f'  旧版 vs v4 对比')
            print(f'{"="*55}')
            print(f'  交易数:      {stats_old["total_trades"]} -> {stats_new["total_trades"]} ({stats_new["total_trades"]/stats_old["total_trades"]*100-100:+.1f}%)')
            print(f'  胜率:        {stats_old["win_rate"]}% -> {stats_new["win_rate"]}% ({float(stats_new["win_rate"])-float(stats_old["win_rate"]):+.1f}pp)')
            print(f'  盈亏比:      {stats_old["profit_factor"]} -> {stats_new["profit_factor"]}')
            print(f'  平均持股:    {stats_old["avg_hold_days"]}天 -> {stats_new["avg_hold_days"]}天')
            print(f'  早夭<3天:    {stats_old["early_exit_lt3d_pct"]}% -> {stats_new["early_exit_lt3d_pct"]}%')
            print(f'  最大回撤:    {stats_old["max_drawdown_pct"]}% -> {stats_new["max_drawdown_pct"]}%')

    elif mode == 'old':
        print(f'\n[4] 旧版入场...')
        trades, _ = run_backtest(signals, unique, sector_map, use_v4_filter=False)
        stats = compute_stats(trades, signals)
        print_stats(stats, '旧版 (原入场逻辑)')
    else:
        print(f'\n[4] v4纯条件B入场...')
        trades, fs = run_backtest(signals, unique, sector_map, use_v4_filter=True)
        stats = compute_stats(trades, signals)
        print_stats(stats, 'v4 (纯条件B)')
        print_filter_stats(fs, 'v4入场过滤')

    if stats:
        ver = 'v4_compare' if compare else ('v4' if not use_old else 'v4_old')
        out = {
            'backtest_time': datetime.now().strftime('%Y%m%d_%H%M'),
            'version': ver,
            'stats': stats,
            'trades': trades,
        }
        json.dump(out, open(OUTPUT_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'\n  结果已保存: {OUTPUT_PATH}')

if __name__ == '__main__':
    main()
