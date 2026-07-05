# -*- coding: utf-8 -*-
"""
容量核心交易系统·回测引擎 v2.0
================================
策略逻辑：
  1. 信号日：底部放量扫描（成交额>=10亿 + 涨幅>5% + 放量>2倍 + 距MA60+-15%）
  2. 买点：分歧回踩MA60(-3% ~ +3%)，缩量确认
  3. 持仓：趋势市→破EMA5减半→破EMA13清仓(ATR缓冲)
           震荡市→破EMA5观察1天→放量再减→破EMA13清仓
           防御市→不开新仓+破EMA5即清
  4. 大盘状态：自动判断（趋势/震荡/防御）

回测区间：2026-04-01 ~ 2026-06-25 (约60交易日)

运行模式:
  python backtest_trading_system.py                    # 仅加载已有JSON + 列出信号
  python backtest_trading_system.py --run              # 完整回测（用本地JSON+已有kline_cache）
  python backtest_trading_system.py --fetch-api        # 从API拉取K线后回测（明天API重置后用）
"""

import sys, os, json, math
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean, stdev

# DATA_DIR 定位：脚本在 百日新高系统/ 内或 Desktop/ 下都能工作
_script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_script_dir).startswith('百日新高'):
    DATA_DIR = _script_dir
else:
    DATA_DIR = os.path.join(_script_dir, '百日新高系统')
    if not os.path.isdir(DATA_DIR):
        DATA_DIR = _script_dir

OUTPUT_PATH = os.path.join(DATA_DIR, '回测结果.json')

# ─── 工具函数 ───────────────────────────────────────────────

def calc_ema(vals, n):
    if len(vals) < n: return None
    k = 2 / (n + 1)
    e = sum(vals[-n:]) / n
    for v in vals[-(n-1):]:
        e = v * k + e * (1 - k)
    return e

def calc_atr(rows, n=14):
    if len(rows) < n + 1: return None
    trs = []
    for i in range(-n, 0):
        h, l, pc = rows[i]['high'], rows[i]['low'], rows[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)

def calc_sma(vals, n):
    if len(vals) < n: return None
    return sum(vals[-n:]) / n

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
    """从 JSON 加载底部放量候选"""
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

def load_kline_cache():
    """从本地 pkl cache 加载已有K线数据（pkl 格式: {date, df: DataFrame}）"""
    import pickle, glob, pandas as pd
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
            cache[fname] = rows
            # 别名键
            code6 = fname[2:] if len(fname) > 2 and fname[:2] in ('sh','sz') else fname
            cache[code6] = rows
            cache[code6.upper()] = rows
            exch = fname[:2].upper()
            cache[f'{code6}.{exch}'] = rows
        except:
            pass
    return cache

def fetch_kline_api(codes):
    """从悟道API批量获取K线（单批最多20只）"""
    try:
        sys.path.insert(0, DATA_DIR)
        from wudao_client import get_kline
    except ImportError:
        return {}
    result = {}
    for i in range(0, len(codes), 20):
        batch = codes[i:i+20]
        for code in batch:
            rows = get_kline(code, 120)
            if rows and len(rows) > 20:
                result[code] = rows
    return result

# ─── 核心改进：直接从kline_cache中检测信号，不依赖已有JSON ───

def detect_signals_from_klines(cache, start_date='20260401', end_date='20260625'):
    """
    从全市场kline_cache中直接检测容量核心信号

    条件: 成交额>=10亿 + 涨幅>5% + 放量>2倍 + 距MA60±15%

    返回: dict[stock_code] = [(signal_idx, signal_date, {detail}), ...]
    """
    signals = {}  # code -> [(idx, date, detail)]
    # 交易日列表
    from datetime import date, timedelta
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
            print(f'    [{idx}/{total}] 已发现 {found} 次信号')

        dates = [k['date'] for k in klines]
        closes = [k['close'] for k in klines]
        amounts = [k.get('amount', 0) for k in klines]
        volumes = [k.get('volume', 0) for k in klines]
        last_signal_date = ''

        for i in range(60, len(klines)):
            d = dates[i]
            if d not in all_days:
                continue
            # 条件1: 成交额>=10亿
            if amounts[i] < 1e9:
                continue
            # 条件2: 涨幅>5%
            if i < 1: continue
            pct_chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if pct_chg < 5:
                continue
            # 条件3: 放量>2倍(对比前60日均量)
            avg_vol = sum(volumes[i-60:i]) / 60
            if avg_vol <= 0: continue
            vol_ratio = volumes[i] / avg_vol
            if vol_ratio < 2:
                continue
            # 条件4: 距MA60 +-15%
            ma60 = sum(closes[i-60:i]) / 60
            pct60 = (closes[i] - ma60) / ma60 * 100
            if not (-15 <= pct60 <= 15):
                continue
            # 条件5: 同股票间隔至少5天
            if last_signal_date and (int(d) - int(last_signal_date)) < 5:
                continue

            signal = {
                'signal_idx': i,
                'signal_date': d,
                'close': closes[i],
                'ma60': ma60,
                'pct_chg': round(pct_chg, 2),
                'vol_ratio': round(vol_ratio, 2),
                'amount_yi': round(amounts[i] / 1e8, 1),
            }
            if code not in signals:
                signals[code] = []
            signals[code].append(signal)
            last_signal_date = d
            found += 1

    return signals

def find_entry(klines, signal_idx):
    """信号日后找分歧回踩MA60买点"""
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

def run_trade(klines, entry_idx, market_state='oscillating'):
    """从entry_idx开始跟踪持仓到退出"""
    closes = [r['close'] for r in klines]
    entry_price = closes[entry_idx]
    entry_date = klines[entry_idx].get('date', '')

    position = 2  # 2=满仓 1=半仓
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

    # 算总收益
    if half_sold:
        # 找减半日
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

# ─── 主回测 ──────────────────────────────────────────────────

def run_backtest_from_signals(signals_dict, kline_cache):
    """
    从检测到的信号出发跑回测

    Parameters
    ----------
    signals_dict : dict[code] -> [{'signal_idx', 'signal_date', 'close', ...}]
    kline_cache : dict[code] -> list[dict] klines

    Returns
    -------
    dict : {trades, stats}
    """
    trades = []
    equity = [1.0]

    for code, signal_list in signals_dict.items():
        klines = kline_cache.get(code, [])
        if len(klines) < 80:
            continue

        for sig in signal_list:
            sig_idx = sig['signal_idx']
            if sig_idx >= len(klines) - 3:
                continue  # 信号日太新，无后续数据

            entry_idx = find_entry(klines, sig_idx)
            if entry_idx is None:
                continue

            trade = run_trade(klines, entry_idx, 'oscillating')
            trade['code'] = code
            trade['signal_date'] = sig['signal_date']
            trade['signal_pct_chg'] = sig['pct_chg']
            trade['signal_amount_yi'] = sig['amount_yi']
            trades.append(trade)

    # ─── 绩效统计 ──────────────────────────────────────
    if not trades:
        return {'trades': [], 'stats': None}

    # 按exit_date排序
    trades_sorted = sorted(trades, key=lambda t: t['exit_date'])

    pnls = [t['pnl_pct'] / 100 for t in trades_sorted]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(trades)
    avg_win = mean(wins) * 100 if wins else 0
    avg_loss = mean(losses) * 100 if losses else 0
    profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf')

    # 累计权益曲线 (复利)
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

    stats = {
        'total_signals': sum(len(v) for v in signals_dict.values()),
        'total_trades': len(trades),
        'win_rate': round(win_rate*100, 1),
        'avg_win_pct': round(avg_win, 2),
        'avg_loss_pct': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2),
        'total_return_pct': round(total_return*100, 2),
        'annualized_return_pct': round(ann_ret*100, 2),
        'max_drawdown_pct': round(mdd*100, 2),
        'sharpe_ratio': round(sr, 2),
        'avg_hold_days': round(avg_hold, 1),
        'date_range': f'{date0} ~ {date1}',
    }
    return {'trades': trades, 'stats': stats}

# ─── 回测模式2：用实际K线数据 ─────────────────────────────

def build_with_cache(signals, kline_cache):
    """用本地缓存构建kline数据"""
    def _norm(c):
        c = c.strip().upper()
        if '.' in c:
            code, exch = c.split('.')
            return exch.lower() + code
        return ('sh' if c.startswith('6') else 'sz') + c

    stocks = []
    for s in signals:
        code = s.get('code', '')
        ncode = _norm(code)
        klines = kline_cache.get(code) or kline_cache.get(ncode) or kline_cache.get(code[:6])
        if not klines or len(klines) < 80:
            continue
        # klines按日期升序排列
        s['_klines'] = klines
        stocks.append(s)
    return stocks

def build_with_api(signals):
    """从API拉取K线"""
    codes = list(set(s.get('code','')[:6] for s in signals if s.get('code')))
    print(f'  从API拉取 {len(codes)} 只股票的K线...')
    kline_data = fetch_kline_api(codes)
    stocks = []
    for s in signals:
        code = s.get('code', '')
        code6 = code[:6] if '.' in code else code
        klines = kline_data.get(code) or kline_data.get(code6)
        if not klines or len(klines) < 80:
            continue
        s['_klines'] = klines
        stocks.append(s)
    return stocks

# ─── 输出 ─────────────────────────────────────────────────────

def print_trades(trades):
    H = f'{"="*110}'
    HDR = f'{"代码":>8} {"名称":>8} {"评分":>4} {"信号日":>8} {"买入日":>8} {"卖出日":>8} {"收益率":>9} {"持仓":>4} {"退出原因":>22}'
    print(H)
    print(HDR)
    print(H)
    for t in trades:
        print(f'{t.get("code","")[:8]:>8} {t.get("name","")[:8]:>8} {t.get("rating",""):>4} '
              f'{t["signal_date"]:>8} {t["entry_date"]:>8} {t["exit_date"]:>8} '
              f'{t["pnl_pct"]:>7.1f}% {t["hold_days"]:>4} {t["exit_reason"]:>22}')

def print_stats(stats):
    if not stats:
        print('\n  [X] 无有效交易')
        return
    print(f'\n{"="*50}')
    print(f'  回测期间:    {stats["date_range"]}')
    print(f'  交易次数:    {stats["total_trades"]}')
    print(f'  胜率:        {stats["win_rate"]}%')
    print(f'  平均盈利:    {stats["avg_win_pct"]}%')
    print(f'  平均亏损:    {stats["avg_loss_pct"]}%')
    print(f'  盈亏比:      {stats["profit_factor"]}')
    print(f'  总收益率:    {stats["total_return_pct"]}%')
    print(f'  年化收益:    {stats["annualized_return_pct"]}%')
    print(f'  最大回撤:    {stats["max_drawdown_pct"]}%')
    print(f'  夏普比率:    {stats["sharpe_ratio"]}')
    print(f'  平均持股:    {stats["avg_hold_days"]} 天')
    print(f'{"="*50}')

# ─── 入口 ─────────────────────────────────────────────────────

def main():
    print(f'\n{"="*60}')
    print(f'  容量核心交易系统·回测 v2.0')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*60}')

    mode = 'list'
    if '--run' in sys.argv:
        mode = 'run'
    elif '--quick' in sys.argv:
        mode = 'quick'

    # ================== 模式1: list ==================
    if mode == 'list':
        signals = load_json_signals()
        print(f'\n[1] 已有JSON信号: {len(signals)} 条')
        by_date = defaultdict(int)
        for s in signals:
            by_date[s.get('_signal_date','')] += 1
        print(f'  覆盖 {len(by_date)} 天:', ', '.join(sorted(by_date)))
        print(f'\n  --run     从kline_cache全市场检测信号并回测（推荐）')
        print(f'  --quick   仅从已有JSON信号回测')
        return

    # ================== 模式2: run (全市场扫描) ==================
    if mode == 'run':
        print(f'\n[1] 加载kline_cache...')
        cache = load_kline_cache()
        # 去重：只保留纯6位数字码
        unique = {}
        for k, v in cache.items():
            if k.isdigit() and len(k) == 6:
                unique[k] = v
        print(f'  加载 {len(unique)} 只唯一股票缓存')

        print(f'\n[2] 全市场检测容量核心信号 (20260401~20260625)...')
        signals = detect_signals_from_klines(unique, '20260401', '20260625')
        total_sig = sum(len(v) for v in signals.values())
        print(f'  发现 {total_sig} 次信号, 涉及 {len(signals)} 只股票')

        print(f'\n[3] 运行回测...')
        result = run_backtest_from_signals(signals, unique)

    # ================== 模式3: quick (已有JSON) ==================
    else:
        print(f'\n[1] 加载kline_cache和JSON信号...')
        cache = load_kline_cache()
        unique = {}
        for k, v in cache.items():
            if len(k) <= 8:
                unique[k] = v
        signals = load_json_signals()
        stocks = build_with_cache(signals, unique)
        print(f'  缓存 {len(unique)} 只, 信号 {len(signals)} 条, 匹配 {len(stocks)} 只')

        print(f'\n[2] 运行回测...')
        # 将stock列表转换为signals_dict格式
        sd = defaultdict(list)
        for s in stocks:
            code = s.get('code', '')[:6]
            sig_date = s['_signal_date']
            klines = s['_klines']
            sig_idx = None
            for i, k in enumerate(klines):
                if k.get('date', '') == sig_date:
                    sig_idx = i
                    break
            if sig_idx is not None:
                sd[code].append({
                    'signal_idx': sig_idx,
                    'signal_date': sig_date,
                    'close': s.get('close', 0),
                    'pct_chg': s.get('change', 0),
                    'amount_yi': s.get('amount_yi', 0),
                })
        result = run_backtest_from_signals(sd, unique)

    # ─── 结果输出 ──────────────────────────────────────
    if result and result['stats']:
        print_trades(result['trades'])
        print_stats(result['stats'])
        out = {
            'backtest_time': datetime.now().strftime('%Y%m%d_%H%M'),
            'mode': mode,
            'total_signals': result['stats'].get('total_signals', 0),
            'total_trades': result['stats']['total_trades'],
            'stats': result['stats'],
            'trades': result['trades'],
        }
        json.dump(out, open(OUTPUT_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'\n  结果已保存: {OUTPUT_PATH}')
    else:
        print(f'\n  [X] 未找到有效交易')
        print(f'  可能原因: 数据不足或条件过于严格')

if __name__ == '__main__':
    main()
