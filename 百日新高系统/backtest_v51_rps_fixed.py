# -*- coding: utf-8 -*-
"""
量化回测 v5.1 — 修复Layer2板块RPS筛选
"""
import os, sys, pickle, glob, warnings, json
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

CONFIG = {
    'start_date': '2024-06-01', 'end_date': '2026-07-03',
    'initial_capital': 1_000_000, 'commission_rate': 0.00025, 'slippage': 0.001,
    'max_daily_buy': 2, 'single_position': 0.15,
    'output_dir': '百日新高系统',
}
CACHE_DIR = os.path.join(CONFIG['output_dir'], 'kline_cache')
SECTOR_MAP_FILE = os.path.join(CONFIG['output_dir'], 'sector_map.json')

# ============================================================
# 1. 数据加载
# ============================================================
def load_index_data():
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol='sh000001')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df = df[(df['date'] >= CONFIG['start_date']) & (df['date'] <= CONFIG['end_date'])]
    return df.set_index('date')

def load_all_stock_data():
    """加载kline_cache中所有>200行的完整数据"""
    files = glob.glob(os.path.join(CACHE_DIR, '*.pkl'))
    stocks = {}
    for f in files:
        try:
            with open(f, 'rb') as fh:
                data = pickle.load(fh)
            df = data.get('df', data) if isinstance(data, dict) else data
            if hasattr(df, 'iloc') and len(df) > 200:
                code = os.path.basename(f).replace('.pkl', '')
                stocks[code] = df
        except:
            pass
    return stocks

def load_sector_map():
    """加载行业映射，补全缺失的用stock的industry字段"""
    sector_map = {}
    if os.path.exists(SECTOR_MAP_FILE):
        with open(SECTOR_MAP_FILE, 'r', encoding='utf-8') as f:
            sector_map = json.load(f)
    return sector_map

def prepare_universe(stock_data, index_df, sector_map):
    """对齐个股到统一日期"""
    trade_dates = index_df.index.tolist()
    universe = {}

    for code, df in stock_data.items():
        try:
            df = df.copy()
            cols_lower = {c.lower(): c for c in df.columns}
            date_col = cols_lower.get('date', None)
            if date_col is None:
                continue

            df['date'] = pd.to_datetime(df[date_col])
            df = df.sort_values('date').drop_duplicates('date').set_index('date')

            # 挑一个公共日期子集
            common = df.index.intersection(trade_dates)
            if len(common) < 60:
                continue
            df = df.loc[common]

            # 标准化列
            for target, origins in [('open',['open']), ('high',['high']), ('low',['low']),
                                     ('close',['close']), ('volume',['volume','vol']), ('amount',['amount'])]:
                for o in origins:
                    if o in cols_lower:
                        df[target] = pd.to_numeric(df[cols_lower[o]], errors='coerce')
                        break

            if all(c in df.columns for c in ['open','high','low','close']):
                df = df.dropna(subset=['close'])
                if len(df) >= 60:
                    # 补充 sector
                    clean_code = code.replace('sh','').replace('sz','').replace('bj','')
                    sector = sector_map.get(code, sector_map.get(clean_code, ''))
                    if not sector:
                        # 尝试从原始数据的industry字段
                        for c in df.columns:
                            if c.lower() == 'industry':
                                sector = str(df[c].iloc[-1]) if pd.notna(df[c].iloc[-1]) else ''
                                break
                    if sector:
                        universe[code] = {'df': df, 'sector': sector}
        except:
            continue
    return universe

# ============================================================
# 2. Layer 1: 大盘状态
# ============================================================
def market_state_detector(date, index_df, prev_state, consecutive):
    """三锚表决: >=2锚True=上涨, 0锚True=下跌, 其余=震荡"""
    idx = index_df.index.get_loc(date)
    if idx < 60:
        return '震荡', 0.3, 0

    closes = index_df['close']
    ma20 = closes.rolling(20).mean()

    # 锚1: 上证收盘>MA20 且 MA20连续3日走高
    anchor1 = closes.iloc[idx] > ma20.iloc[idx]
    ma20_rising = (ma20.iloc[idx] > ma20.iloc[idx-1] > ma20.iloc[idx-2])

    # 锚2: 全A等权 proxy (同上证，无独立数据)
    anchor2 = anchor1

    # 锚3: 涨跌比 proxy (用成交额趋势)
    volumes = index_df.get('volume', closes)
    vol_ma5 = volumes.rolling(5).mean() if 'volume' in index_df.columns else None
    anchor3 = True  # 无涨跌家数数据，默认过

    votes = sum([anchor1 and ma20_rising, anchor2 and ma20_rising, anchor3])
    # Note: anchor1和anchor2都是 compound condition (close>MA20 AND MA20走高)

    if votes >= 2:
        target = '上涨'; pos = 0.7
    elif votes == 0:
        target = '下跌'; pos = 0.0
    else:
        target = '震荡'; pos = 0.3

    if target == prev_state:
        consecutive += 1
    else:
        consecutive = 1

    if consecutive >= 2:
        current = target
        ratio = pos
    else:
        current = prev_state if prev_state else target
        ratio = 0.3
    return current, ratio, consecutive

# ============================================================
# 3. Layer 2: 板块RPS筛选 (修复版)
# ============================================================
def calc_sector_rps(universe, date, window):
    """
    计算每个板块在指定窗口的相对RPS
    RPS = 板块涨幅在所有板块中的分位数 × 100
    """
    sector_returns = defaultdict(list)

    for code, info in universe.items():
        df = info['df']
        sector = info['sector']
        if not sector or date not in df.index:
            continue

        idx = df.index.get_loc(date)
        if idx < window:
            continue

        close_now = df['close'].iloc[idx]
        close_past = df['close'].iloc[idx - window]

        if pd.notna(close_now) and pd.notna(close_past) and close_past > 0:
            ret = (close_now - close_past) / close_past * 100
            sector_returns[sector].append(ret)

    # 计算每个板块平均涨幅
    sector_avg = {}
    for sec, returns in sector_returns.items():
        if len(returns) >= 3:  # 至少3只成分股
            sector_avg[sec] = np.mean(returns)

    if len(sector_avg) < 5:
        return set()

    # 计算RPS分位值
    values = np.array(list(sector_avg.values()))
    percentiles = {}

    # 排位式计算 RPS
    sectors_list = list(sector_avg.keys())
    returns_list = [sector_avg[s] for s in sectors_list]
    ranks = np.argsort(np.argsort(returns_list))  # 0=最差, n-1=最好

    for i, sec in enumerate(sectors_list):
        percentile = ranks[i] / max(len(ranks) - 1, 1) * 100
        if sec not in percentiles:
            percentiles[sec] = []
        percentiles[sec].append(percentile)

    return percentiles, sector_avg

def get_core_sectors(date, universe, rps_threshold):
    """获取满足RPS(10)>=85, RPS(20)>=85, RPS(60)>=85的板块"""
    rps_results = {}
    for w in [10, 20, 60]:
        rps, _ = calc_sector_rps(universe, date, w)
        for sec, pct in rps.items():
            if sec not in rps_results:
                rps_results[sec] = {}
            rps_results[sec][w] = pct

    # 三项全部>=阈值
    qualified = []
    for sec, windows in rps_results.items():
        if all(max(windows.get(w, [0])) >= rps_threshold for w in [10, 20, 60]):
            qualified.append(sec)

    # top5 by 百日新高
    new_high_sectors = get_top5_new_high(date, universe)

    # 交集
    core = [s for s in qualified if s in new_high_sectors]
    return core, qualified, new_high_sectors

def get_top5_new_high(date, universe):
    """各板块3日累计百日新高数，取前5"""
    sector_nh = defaultdict(int)
    for code, info in universe.items():
        df = info['df']
        sector = info['sector']
        if not sector or date not in df.index:
            continue
        idx = df.index.get_loc(date)
        if idx < 100:
            continue
        close100 = df['close'].iloc[idx-100:idx+1]
        if df['close'].iloc[idx] >= close100.max():
            # 检查前2天是否也是新高
            for back in range(3):
                if idx - back >= 100:
                    c100 = df['close'].iloc[idx-back-100:idx-back+1]
                    if df['close'].iloc[idx-back] >= c100.max():
                        sector_nh[sector] += 1

    sorted_sec = sorted(sector_nh.items(), key=lambda x: x[1], reverse=True)
    return [s[0] for s in sorted_sec[:5]]

def calibrate_rps_threshold(core_sectors, current_threshold):
    """周度校准"""
    n = len(core_sectors)
    if n < 2:
        return 82
    elif n > 10:
        return 88
    return current_threshold

# ============================================================
# 4. Layer 3: 个股筛选
# ============================================================
def stock_filter(date, code, info, core_sectors):
    """筛选符合条件的个股"""
    df = info['df']
    sector = info['sector']
    if date not in df.index:
        return False, None

    idx = df.index.get_loc(date)
    if idx < 60:
        return False, None

    # 板块过滤
    if core_sectors and sector not in core_sectors:
        return False, None

    closes = df['close']
    volumes = df.get('volume', None)
    close_today = closes.iloc[idx]

    # MA60
    ma60_vals = closes.iloc[idx-60:idx+1]
    ma60 = ma60_vals.mean()
    if close_today <= ma60:
        return False, None

    # MA60连续3日走高
    ma60_1 = closes.iloc[idx-1-60:idx].mean()
    ma60_2 = closes.iloc[idx-2-61:idx-1].mean()
    if not (ma60 > ma60_1 > ma60_2):
        return False, None

    # 量比 >= 1.5
    vol_ratio = 1.5
    if volumes is not None and idx >= 5:
        avg5 = volumes.iloc[idx-5:idx].mean()
        if avg5 > 0:
            vol_ratio = volumes.iloc[idx] / avg5
            if vol_ratio < 1.5:
                return False, None

    # 前20日涨幅 <= 30%
    if idx >= 20:
        chg20 = (closes.iloc[idx] - closes.iloc[idx-20]) / closes.iloc[idx-20] * 100
        if chg20 > 30:
            return False, None

    # 距MA60 0%~20%
    dist = (close_today - ma60) / ma60 * 100
    if dist < 0 or dist > 20:
        return False, None

    return True, {'ma60': ma60, 'close': close_today, 'dist': dist, 'vol_ratio': vol_ratio}

# ============================================================
# 5. Layer 4: 卖出规则
# ============================================================
def check_exit(date, pos, info):
    df = info['df']
    if date not in df.index:
        return pos.get('_exit', None), pos

    try:
        idx = df.index.get_loc(date)
    except:
        return None, pos

    closes = df['close']
    close_today = closes.iloc[idx]
    holding = pos.get('holding_days', 0) + 1
    pnl = (close_today - pos['cost_basis']) / pos['cost_basis'] * 100

    # 时间止损
    if holding >= 10:
        gain = (close_today - pos['entry_price']) / pos['entry_price'] * 100
        if gain < 5:
            return 'time_stop', pos

    # 硬止损 (MA10)
    ma10 = closes.iloc[max(0,idx-10):idx+1].mean()
    if close_today < ma10:
        return 'hard_stop_ma10', pos

    # 保本
    if pnl > 10:
        pos['stop_loss'] = pos['cost_basis']
    if pos.get('stop_loss') and close_today < pos['stop_loss']:
        return 'breakeven', pos

    # 移动止盈
    if pnl > 30:
        ma10 = closes.iloc[max(0,idx-10):idx+1].mean()
        if close_today < ma10:
            return 'trailing_ma10', pos
    elif pnl > 20:
        ma5 = closes.iloc[max(0,idx-5):idx+1].mean()
        if close_today < ma5:
            return 'trailing_ma5', pos

    pos['holding_days'] = holding
    return None, pos

# ============================================================
# 6. 回测引擎
# ============================================================
class BacktestEngine:
    def __init__(self, index_df, universe):
        self.index_df = index_df
        self.universe = universe
        self.capital = CONFIG['initial_capital']
        self.positions = []
        self.closed_trades = []
        self.daily_equity = []
        self.rps_threshold = 85
        self.calibration_week = None

    def run(self):
        dates = self.index_df.index.tolist()
        start_i = 120
        prev_state = None
        consecutive = 0

        for i, date in enumerate(dates[start_i:], start=start_i):
            if i % 50 == 0:
                total_val = self._total_value(date)
                print(f"  [{date.strftime('%Y-%m-%d')}] 净值:{total_val:.0f} 持仓:{len(self.positions)} 主线:{len(self._core) if hasattr(self,'_core') else 0}个")

            # Layer 1
            m_state, ratio, consecutive = market_state_detector(date, self.index_df, prev_state, consecutive)
            prev_state = m_state
            self._last_market_state = m_state

            # 周度校准
            if date.weekday() == 0:
                cal_week = date.isocalendar()[1]
                if cal_week != self.calibration_week:
                    self.calibration_week = cal_week
                    core, _, _ = get_core_sectors(date, self.universe, self.rps_threshold)
                    self.rps_threshold = calibrate_rps_threshold(core, self.rps_threshold)

            # Layer 2
            core, qualified, nh5 = get_core_sectors(date, self.universe, self.rps_threshold)
            self._core = core

            # Layer 4: 卖
            new_pos = []
            for pos in self.positions:
                code = pos['code']
                info = self.universe.get(code)
                if info is None:
                    self._close(pos, 'data_loss', date, 0)
                    continue
                action, updated = check_exit(date, pos, info)
                if action:
                    self._close(updated, action, date, close_today=info['df'].loc[date,'close'])
                else:
                    new_pos.append(updated)
            self.positions = new_pos

            # Layer 3: 买
            buy_limit = int(CONFIG['max_daily_buy'] * ratio / 0.7) + 1 if ratio > 0 else 0
            if ratio > 0 and len(self.positions) < buy_limit:
                candidates = []
                for code, info in self.universe.items():
                    ok, detail = stock_filter(date, code, info, core)
                    if ok and not any(p['code'] == code for p in self.positions):
                        candidates.append((code, info, detail))
                candidates.sort(key=lambda x: x[2]['vol_ratio'], reverse=True)

                for code, info, detail in candidates[:5]:
                    if len(self.positions) >= buy_limit:
                        break
                    self._buy(date, code, info, detail)

            # 记录
            self.daily_equity.append({
                'date': date, 'equity': self._total_value(date), 'state': m_state
            })

        # 清仓
        last_date = dates[-1]
        for pos in list(self.positions):
            info = self.universe.get(pos['code'])
            close = info['df'].loc[last_date, 'close'] if info and last_date in info['df'].index else pos['entry_price']
            self._close(pos, 'end', last_date, close)

    def _total_value(self, date):
        val = self.capital
        for pos in self.positions:
            info = self.universe.get(pos['code'])
            if info and date in info['df'].index:
                val += pos['shares'] * info['df'].loc[date, 'close']
            else:
                val += pos['shares'] * pos['entry_price']
        return val

    def _buy(self, date, code, info, detail):
        close = detail['close']
        pos_val = self.capital * CONFIG['single_position']
        shares = int(pos_val / (close * (1 + CONFIG['slippage']))) // 100 * 100
        if shares < 100:
            return
        cost = shares * close * (1 + CONFIG['slippage']) * (1 + CONFIG['commission_rate'])
        if cost > self.capital * 0.25:
            return
        self.capital -= cost
        self.positions.append({
            'code': code, 'entry_date': date, 'entry_price': close,
            'cost_basis': close * (1 + CONFIG['slippage']),
            'shares': shares, 'holding_days': 0, 'stop_loss': None,
            'market_state': self._last_market_state,
            'sector': info['sector'],
        })

    def _close(self, pos, reason, date, close_today=None):
        info = self.universe.get(pos['code'])
        if close_today is None and info and date in info['df'].index:
            close_today = info['df'].loc[date, 'close']
        elif close_today is None:
            close_today = pos['entry_price']

        proceeds = pos['shares'] * close_today * (1 - CONFIG['slippage']) * (1 - CONFIG['commission_rate'])
        self.capital += proceeds
        pnl = proceeds - pos['shares'] * pos['cost_basis']
        pnl_pct = pnl / (pos['shares'] * pos['cost_basis']) * 100

        self.closed_trades.append({
            'code': pos['code'], 'sector': pos.get('sector',''),
            'entry_date': pos['entry_date'], 'exit_date': date,
            'entry_price': pos['entry_price'], 'exit_price': close_today,
            'exit_reason': reason, 'pnl': pnl, 'pnl_pct': pnl_pct,
            'holding_days': pos.get('holding_days', 0),
            'market_state': pos.get('market_state', ''),
        })

    def report(self):
        eq = pd.DataFrame(self.daily_equity)
        eq['date'] = pd.to_datetime(eq['date'])
        eq = eq.set_index('date')
        equity = eq['equity']

        total_ret = (equity.iloc[-1] / CONFIG['initial_capital'] - 1) * 100
        days = (equity.index[-1] - equity.index[0]).days
        ann_ret = ((1 + total_ret/100) ** (365/days) - 1) * 100

        peak = equity.expanding().max()
        dd = (equity - peak) / peak * 100
        max_dd = dd.min()

        daily_r = equity.pct_change().dropna()
        sharpe = (daily_r.mean() / daily_r.std()) * np.sqrt(252) if daily_r.std() > 0 else 0

        trades = self.closed_trades
        n = len(trades)
        wins = [t for t in trades if t['pnl'] > 0]
        wr = len(wins)/n*100 if n else 0
        avg_w = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
        avg_l = np.mean([t['pnl_pct'] for t in trades if t['pnl'] <= 0]) if n > len(wins) else 0
        pf = abs(avg_w/avg_l) if avg_l and avg_w else 0

        mcl = 0; cur = 0
        for t in trades:
            cur = cur + 1 if t['pnl'] < 0 else 0
            mcl = max(mcl, cur)

        # 分状态
        state_stats = {}
        for st in ['上涨','震荡','下跌']:
            st_t = [t for t in trades if t['market_state'] == st]
            if st_t:
                state_stats[st] = {
                    'n': len(st_t),
                    'wr': len([t for t in st_t if t['pnl']>0])/len(st_t)*100,
                    'avg': np.mean([t['pnl_pct'] for t in st_t])
                }

        # 分行业TOP
        sector_pnl = defaultdict(list)
        for t in trades:
            sector_pnl[t['sector']].append(t['pnl_pct'])
        top_sectors = sorted(sector_pnl.items(), key=lambda x: np.mean(x[1]), reverse=True)[:5]
        worst_sectors = sorted(sector_pnl.items(), key=lambda x: np.mean(x[1]))[:5]

        rpt = f"""
{'='*60}
            量化回测报告 v5.1 (Layer 2 修复)
{'='*60}

回测区间: {equity.index[0].strftime('%Y-%m-%d')} ~ {equity.index[-1].strftime('%Y-%m-%d')}
初始资金: {CONFIG['initial_capital']:,} 元
最终资金: {equity.iloc[-1]:,.0f} 元
RPS阈值: {self.rps_threshold}

--- 核心指标 ---
总收益率:     {total_ret:+.2f}%
年化收益率:   {ann_ret:+.2f}%
最大回撤:     {max_dd:+.2f}%
夏普比率:     {sharpe:.2f}
交易次数:     {n}
胜率:         {wr:.1f}%
盈亏比:       {pf:.2f}
最大连续亏损: {mcl} 次

--- 分市场状态 ---"""
        for st in ['上涨','震荡','下跌']:
            if st in state_stats:
                s = state_stats[st]
                rpt += f"\n  {st}市: 交易{s['n']}次  胜率{s['wr']:.1f}%  均收益{s['avg']:+.2f}%"
            else:
                rpt += f"\n  {st}市: 无交易"

        rpt += f"\n\n--- 最佳5行业 ---"
        for sec, pnls in top_sectors:
            rpt += f"\n  {sec}: {len(pnls)}笔  均{np.mean(pnls):+.2f}%  胜率{len([p for p in pnls if p>0])/len(pnls)*100:.0f}%"

        rpt += f"\n\n--- 最差5行业 ---"
        for sec, pnls in worst_sectors:
            rpt += f"\n  {sec}: {len(pnls)}笔  均{np.mean(pnls):+.2f}%"

        rpt += f"\n\n--- 全部交易明细 (按收益排序) ---"
        for i, t in enumerate(sorted(trades, key=lambda x: x['pnl_pct'], reverse=True)):
            rpt += f"\n  {i+1:2d}. {t['code']:10s} {t['sector']:8s} {t['pnl_pct']:+7.2f}% {t['holding_days']:2d}天 {t['entry_date'].strftime('%m-%d')}→{t['exit_date'].strftime('%m-%d')} {t['exit_reason']:14s}"

        # 盈亏分布
        pnl_all = [t['pnl_pct'] for t in trades]
        seps = [-20, -10, -5, 0, 5, 10, 20, 50]
        rpt += f"\n\n--- 盈亏分布 ---\n  盈利: {len([p for p in pnl_all if p>0])}笔  亏损: {len([p for p in pnl_all if p<=0])}笔  均收益: {np.mean(pnl_all):+.2f}%"
        for i in range(len(seps)-1):
            cnt = len([p for p in pnl_all if seps[i] <= p < seps[i+1]])
            rpt += f"\n  {seps[i]:+3d}%~{seps[i+1]:+3d}%: {cnt}笔 {'#'*cnt}"

        # 持仓天数
        hd = [t['holding_days'] for t in trades]
        rpt += f"\n\n--- 持仓天数 ---\n  均值:{np.mean(hd):.1f}天 中位数:{np.median(hd):.0f}天 最长:{max(hd)}天 最短:{min(hd)}天"

        # 出场原因
        from collections import Counter
        reasons = Counter(t['exit_reason'] for t in trades)
        rpt += f"\n\n--- 出场原因 ---"
        for r, c in reasons.most_common():
            rpt += f"\n  {r}: {c}笔 ({c/len(trades)*100:.0f}%)"

        rpt += f"\n{'='*60}\n"
        return rpt

# ============================================================
# 7. Main
# ============================================================
def main():
    print('='*50)
    print('  量化回测 v5.1 (Layer 2 RPS修复)')
    print('='*50)

    print('\n[1/4] 加载数据...')
    index_df = load_index_data()
    print(f'  上证: {len(index_df)} 天')

    stock_data = load_all_stock_data()
    print(f'  个股缓存: {len(stock_data)} 只')

    sector_map = load_sector_map()
    print(f'  行业映射: {len(sector_map)} 只')

    print('\n[2/4] 对齐数据...')
    universe = prepare_universe(stock_data, index_df, sector_map)
    sectors = set(i['sector'] for i in universe.values())
    print(f'  有效个股: {len(universe)} 只, {len(sectors)} 个行业')

    print(f'\n[3/4] 跑回测...')
    engine = BacktestEngine(index_df, universe)
    engine.run()

    print(f'\n[4/4] 报告...')
    report = engine.report()
    print(report)

    path = os.path.join(CONFIG['output_dir'], '回测报告_v51.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'保存: {path}')

if __name__ == '__main__':
    main()
