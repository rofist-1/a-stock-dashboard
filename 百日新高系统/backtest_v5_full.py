# -*- coding: utf-8 -*-
"""
量化回测脚本 v1.0
================================
四层筛选体系：
  Layer1: 大盘状态 & 仓位管理（三锚表决+情绪过滤器）
  Layer2: 板块RPS筛选 & 核心主线
  Layer3: 个股筛选 & 五步买入确认
  Layer4: 卖出规则

数据源: AKShare + 本地kline_cache
回测区间: 2024-06-01 至 2026-07-03
"""

import os, sys, pickle, glob, warnings, time, json
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ============================================================
# 0. 配置参数
# ============================================================
CONFIG = {
    'start_date': '2024-06-01',
    'end_date':   '2026-07-03',
    'initial_capital': 1_000_000,
    'commission_rate': 0.00025,   # 万2.5
    'slippage': 0.001,            # 0.1%
    'max_daily_buy': 2,
    'single_position': 0.15,
    'output_dir': r'百日新高系统',
}

CACHE_DIR = os.path.join(CONFIG['output_dir'], 'kline_cache')
SECTOR_MAP_FILE = os.path.join(CONFIG['output_dir'], 'sector_map.json')

# ============================================================
# 1. 数据加载模块
# ============================================================

def load_index_data():
    """加载上证指数日线数据（使用AKShare）"""
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol='sh000001')
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df = df[(df['date'] >= CONFIG['start_date']) & (df['date'] <= CONFIG['end_date'])]
    return df.set_index('date')

def load_market_breadth():
    """
    加载市场涨跌家数（使用AKShare）
    若AKShare失败则用涨跌比估算
    """
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        # spot数据是实时快照，需要daily数据。
        # 尝试获取历史的涨跌家数
        df_breadth = ak.stock_market_fund_flow()
        return df_breadth
    except:
        pass

    # 降级方案: 用本地缓存算
    return None

def load_stock_list():
    """加载股票列表（从本地缓存或AKShare）"""
    files = glob.glob(os.path.join(CACHE_DIR, '*.pkl'))
    stocks = {}
    for f in files:
        try:
            code = os.path.basename(f).replace('.pkl', '')
            with open(f, 'rb') as fh:
                data = pickle.load(fh)
            df = data.get('df', data) if isinstance(data, dict) else data
            if hasattr(df, 'iloc') and len(df) > 0:
                stocks[code] = df
        except:
            pass
    return stocks

def load_sector_map():
    """加载申万行业映射"""
    if os.path.exists(SECTOR_MAP_FILE):
        with open(SECTOR_MAP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def prepare_stock_universe(stock_data, index_df):
    """
    将本地缓存的个股数据对齐到回测日期范围。
    返回: {code: DataFrame indexed by date}
    """
    universe = {}
    trade_dates = index_df.index.tolist()

    for code, df in stock_data.items():
        try:
            # 标准化列名
            cols = {c.lower(): c for c in df.columns}
            date_col = cols.get('date', None)
            if date_col is None:
                continue

            df = df.copy()
            df['date'] = pd.to_datetime(df[date_col])
            df = df.sort_values('date').drop_duplicates('date').set_index('date')

            # 对齐到回测区间
            df = df.reindex(trade_dates)
            df = df.ffill()  # 前向填充停牌日

            # 标准化OHLC
            for std, orig in [('open','open'), ('high','high'), ('low','low'),
                             ('close','close'), ('volume','volume'), ('amount','amount')]:
                for c in df.columns:
                    if c.lower() == orig:
                        df[std] = pd.to_numeric(df[c], errors='coerce')
                        break

            if all(c in df.columns for c in ['open','high','low','close','volume']):
                df = df.dropna(subset=['close'])
                if len(df) > 60:
                    universe[code] = df
        except:
            continue

    return universe

# ============================================================
# 2. Layer1: 大盘状态 & 仓位管理
# ============================================================

def calc_ma(series, window):
    return series.rolling(window).mean()

def market_state_detector(date, index_df, breadth_series, prev_state, state_days):
    """
    三锚表决系统:
      锚1: 上证收盘 > MA20 且 MA20连续3日走高
      锚2: 全A等权 > MA20 且 MA20连续3日走高
      锚3: 涨跌比 > 1.2
    表决: >=2锚满足=上涨市, >=2锚不满足=下跌市, 其余=震荡市
    状态切换需连续2日满足
    """
    idx = index_df.index.get_loc(date)
    if idx < 60:
        return '震荡', 0.3, state_days

    # 锚1: 上证指数
    sh_close = index_df['close']
    sh_ma20 = calc_ma(sh_close, 20)
    anchor1 = (sh_close.iloc[idx] > sh_ma20.iloc[idx]) and \
              (sh_ma20.iloc[idx] > sh_ma20.iloc[idx-3])

    # 锚2: 全A等权（用收盘价近似，无等权指数时分两种情况）
    # 降级方案：同上证
    anchor2 = anchor1  # FIXME: 需要全A等权指数数据

    # 锚3: 市场广度（涨跌家数比）
    if breadth_series is not None and len(breadth_series) > idx:
        br = breadth_series.iloc[idx]
        anchor3 = br > 1.2 if pd.notna(br) else True
    else:
        anchor3 = True  # 无数据时默认真

    # 表决
    votes_true = sum([anchor1, anchor2, anchor3])
    if votes_true >= 2:
        target_state = '上涨'
        target_position = 0.7
    elif votes_true <= 0:
        target_state = '下跌'
        target_position = 0.0
    else:
        target_state = '震荡'
        target_position = 0.3

    # 状态切换需连续2日满足新条件
    if target_state == prev_state:
        state_days[target_state] = state_days.get(target_state, 0) + 1
    else:
        state_days = {target_state: 1}  # 新状态，重置计数

    if state_days.get(target_state, 0) >= 2:
        current_state = target_state
        position_ratio = target_position
    else:
        current_state = prev_state if prev_state else target_state
        position_ratio = 0.3  # 未确认前默认震荡仓

    return current_state, position_ratio, state_days

def sentiment_filter(date, new_high_low_diff_series, idx, position_ratio):
    """
    情绪过滤器: 百日新高-百日新低差值
    差值<0: 仓位降一级
    连续3日为负: 强制空仓
    """
    if new_high_low_diff_series is None or idx < 3:
        return position_ratio

    diff_today = new_high_low_diff_series.iloc[idx] if idx < len(new_high_low_diff_series) else 0

    # 连续3日为负检查
    neg_streak = 0
    for i in range(idx, max(idx-3, -1), -1):
        if i < len(new_high_low_diff_series) and new_high_low_diff_series.iloc[i] < 0:
            neg_streak += 1
        else:
            break

    if neg_streak >= 3:
        return 0.0  # 强制空仓

    if diff_today < 0:
        # 降一级: 0.7->0.3, 0.3->0
        return max(0, position_ratio - 0.4)

    return position_ratio

# ============================================================
# 3. Layer2: 板块RPS筛选
# ============================================================

def calc_rps(price_series, window):
    """计算相对价格强度 RPS = 当前价格在过去N日中的分位数"""
    if len(price_series) < window:
        return 50
    current = price_series.iloc[-1]
    past = price_series.iloc[-window]
    chg = (current - past) / abs(past) * 100 if past != 0 else 0
    return chg

def sector_rps_filter(date, sector_prices, universe):
    """
    计算申万二级板块的RPS(10/20/60)
    筛选三项全部>=85的板块
    """
    # 按行业分组计算板块平均涨幅
    sector_map = load_sector_map()
    if not sector_map:
        return []

    # 计算每个板块的成分股平均收益
    sector_gains = defaultdict(list)
    for code, df in universe.items():
        sec = sector_map.get(code, sector_map.get(code[-6:], None))
        if sec is None:
            continue
        try:
            idx = df.index.get_loc(date)
            for w in [10, 20, 60]:
                if idx >= w:
                    chg = (df['close'].iloc[idx] - df['close'].iloc[idx-w]) / df['close'].iloc[idx-w] * 100
                    sector_gains[(sec, w)].append(chg)
        except:
            continue

    # 计算每个板块各窗口RPS
    sector_rps = {}
    for (sec, w), gains in sector_gains.items():
        avg_gain = np.mean(gains) if gains else 0
        if sec not in sector_rps:
            sector_rps[sec] = {}
        sector_rps[sec][w] = avg_gain

    # 筛选 RPS(10/20/60) >= 85
    # 由于是绝对涨幅而非相对排名，阈值转换为涨幅阈值
    rps_threshold = 15  # 近60日涨15%
    qualified = []
    for sec, rps_vals in sector_rps.items():
        if all(rps_vals.get(w, 0) >= rps_threshold for w in [10, 20, 60]):
            qualified.append(sec)

    return qualified[:10]

def get_top_sectors_by_new_high(date, universe, top_n=5):
    """统计每个板块3日累计百日新高数量，取前5名"""
    # 从本地数据计算百日新高（收盘价=100日最高）
    sector_new_highs = defaultdict(int)
    sector_map = load_sector_map()

    for code, df in universe.items():
        sec = sector_map.get(code, sector_map.get(code[-6:], ''))
        if not sec:
            continue
        try:
            idx = df.index.get_loc(date)
            if idx >= 100:
                close_100d = df['close'].iloc[idx-100:idx+1]
                if df['close'].iloc[idx] >= close_100d.max():
                    sector_new_highs[sec] += 1
        except:
            continue

    sorted_sectors = sorted(sector_new_highs.items(), key=lambda x: x[1], reverse=True)
    return [s[0] for s in sorted_sectors[:top_n]]

# ============================================================
# 4. Layer3: 个股筛选 & 买入确认
# ============================================================

def stock_filter(date, code, df, sector_map, core_sectors):
    """
    个股筛选条件:
    - 收盘 > MA60 且 MA60连续3日走高
    - 量比 >= 1.5
    - 前20日涨幅 <= 30%
    - 距MA60在 0%~20%
    - 非ST
    """
    try:
        idx = df.index.get_loc(date)
        if idx < 60:
            return False, None
    except:
        return False, None

    closes = df['close']
    volumes = df['volume'] if 'volume' in df.columns else df.get('vol', None)

    # 行业检查 - 空主线时允许所有板块
    sec = sector_map.get(code, sector_map.get(code[-6:], ''))
    if core_sectors and core_sectors != [''] and sec not in core_sectors:
        return False, None

    # MA60
    ma60 = closes.iloc[idx-60:idx+1].mean()
    close_today = closes.iloc[idx]

    if close_today <= ma60:
        return False, None

    # MA60连续3日走高
    ma60_1 = closes.iloc[idx-1-60:idx].mean()
    ma60_2 = closes.iloc[idx-2-61:idx-1].mean()
    if not (ma60 > ma60_1 > ma60_2):
        return False, None

    # 量比 >= 1.5
    vol_ratio = 1.5  # 默认
    if volumes is not None and idx >= 5:
        avg_vol_5 = volumes.iloc[idx-5:idx].mean()
        if avg_vol_5 > 0:
            vol_ratio = volumes.iloc[idx] / avg_vol_5
            if vol_ratio < 1.5:
                return False, None

    # 前20日涨幅 <= 30%
    if idx >= 20:
        chg_20d = (closes.iloc[idx] - closes.iloc[idx-20]) / closes.iloc[idx-20] * 100
        if chg_20d > 30:
            return False, None

    # 距MA60在 0%~20%
    dist_pct = (close_today - ma60) / ma60 * 100
    if dist_pct < 0 or dist_pct > 20:
        return False, None

    return True, {'ma60': ma60, 'close': close_today, 'dist_pct': dist_pct, 'vol_ratio': vol_ratio if volumes is not None else 1.5}

def five_step_confirm(date, code, df, breakout_info):
    """
    五步买入确认:
    1. 突破后首次缩量回踩MA10(+-2%)或MA20
    2. 回调日成交额 < 突破日成交额 * 50%
    3. 出现止跌K线(下影线>实体2倍/阳线/不创新低)
    4. 确认后次日开盘买入
    """
    try:
        idx = df.index.get_loc(date)
    except:
        return False

    closes = df['close']
    opens = df['open']
    highs = df['high']
    lows = df['low']
    amounts = df.get('amount', None)

    close_today = closes.iloc[idx]

    # 计算MA10和MA20
    ma10 = closes.iloc[max(0,idx-10):idx+1].mean() if idx >= 10 else close_today
    ma20 = closes.iloc[max(0,idx-20):idx+1].mean() if idx >= 20 else close_today

    # 1. 回踩MA10(+-2%)或MA20
    at_ma10 = abs(close_today - ma10) / ma10 <= 0.02 if ma10 > 0 else False
    at_ma20 = abs(close_today - ma20) / ma20 <= 0.05 if ma20 > 0 else False
    if not (at_ma10 or at_ma20):
        return False

    # 2. 缩量 (成交额 < 前日50%)
    if amounts is not None and idx >= 1:
        if amounts.iloc[idx] > amounts.iloc[idx-1] * 0.5:
            return False

    # 3. 止跌K线
    body = abs(close_today - opens.iloc[idx])
    lower_shadow = min(opens.iloc[idx], close_today) - lows.iloc[idx]
    is_bullish = close_today > opens.iloc[idx]
    not_new_low = idx < 1 or lows.iloc[idx] >= lows.iloc[idx-1]

    stop_signal = (lower_shadow > body * 2) or is_bullish or not_new_low
    if not stop_signal:
        return False

    return True

# ============================================================
# 5. Layer4: 卖出规则
# ============================================================

def check_exit(date, position, df, core_sectors, sector_map):
    """
    卖出规则:
    - 时间止损: 入场第10日涨幅<5%
    - 硬止损: 收盘跌破MA20
    - 保本线: 浮盈>10%止损上移成本
    - 移动止盈: 浮盈>20%止盈线=MA5
    - 板块退潮: 只出不进
    """
    code = position['code']
    entry_date = position['entry_date']
    entry_price = position['entry_price']
    cost_basis = position['cost_basis']
    holding_days = position.get('holding_days', 0) + 1

    try:
        idx = df.index.get_loc(date)
    except:
        return None, position  # 无法判断，继续持有

    closes = df['close']
    close_today = closes.iloc[idx]
    pnl_pct = (close_today - cost_basis) / cost_basis * 100

    # 1. 板块退潮
    sec = sector_map.get(code, sector_map.get(code[-6:], ''))
    if sec and sec not in core_sectors and pnl_pct > 0:
        return 'sector_exit', position
    elif sec and sec not in core_sectors:
        return 'sector_exit', position  # 亏损也离场

    # 2. 时间止损: 第10日涨幅<5%
    if holding_days >= 10:
        gain_since_entry = (close_today - entry_price) / entry_price * 100
        if gain_since_entry < 5:
            return 'time_stop', position

    # 3. 硬止损: 收盘跌破MA20
    ma20 = closes.iloc[max(0,idx-20):idx+1].mean()
    if close_today < ma20:
        return 'hard_stop', position

    # 4. 保本线: 浮盈>10%止损上移成本
    if position.get('stop_loss') is None or pnl_pct > 10:
        position['stop_loss'] = position['cost_basis']

    # 5. 移动止盈
    if pnl_pct > 30:
        ma10 = closes.iloc[max(0,idx-10):idx+1].mean()
        if close_today < ma10:
            return 'trailing_stop_ma10', position
    elif pnl_pct > 20:
        ma5 = closes.iloc[max(0,idx-5):idx+1].mean()
        if close_today < ma5:
            return 'trailing_stop_ma5', position

    position['holding_days'] = holding_days
    return None, position

# ============================================================
# 6. 回测引擎
# ============================================================

class BacktestEngine:
    def __init__(self, index_df, universe, sector_map):
        self.index_df = index_df
        self.universe = universe
        self.sector_map = sector_map
        self.capital = CONFIG['initial_capital']
        self.positions = []       # 当前持仓
        self.closed_trades = []   # 已平仓
        self.daily_equity = []    # 每日净值
        self.market_states = []   # 每日市场状态

        self.rps_threshold = 85
        self.last_calibrate_date = None

    def run(self):
        trade_dates = self.index_df.index.tolist()
        prev_state = None
        state_days = {}

        # 先跳过前120日用于初始化MA计算
        start_idx = 120

        for i, date in enumerate(trade_dates[start_idx:], start=start_idx):
            if i % 50 == 0:
                print(f'  [{date.strftime("%Y-%m-%d")}] 净值: {self.capital:.0f} 持仓: {len(self.positions)}')

            # ---- Layer 1: 大盘状态 ----
            market_state, base_ratio, state_days = market_state_detector(
                date, self.index_df, None, prev_state, state_days
            )
            prev_state = market_state
            self._last_market_state = market_state  # 记录供买入时使用

            # 情绪过滤器 (简化: 无百日新高数据时跳过)
            actual_ratio = sentiment_filter(date, None, i, base_ratio)

            # ---- 周度校准 RPS阈值 ----
            if date.weekday() == 0 and date != self.last_calibrate_date:
                self._calibrate_rps(date)

            # ---- Layer 2: 核心主线 ----
            core_sectors = self._get_core_sectors(date)
            # 无主线时标记为 [''] 表示全市场筛选

            # ---- 卖出检查 ----
            new_positions = []
            for pos in self.positions:
                df = self.universe.get(pos['code'])
                if df is None:
                    self._close_position(pos, 'data_loss', date)
                    continue
                action, updated_pos = check_exit(date, pos, df, core_sectors, self.sector_map)
                if action:
                    self._close_position(updated_pos, action, date)
                else:
                    new_positions.append(updated_pos)
            self.positions = new_positions

            # ---- Layer 3: 买入 ----
            if actual_ratio > 0 and len(self.positions) < CONFIG['max_daily_buy']:
                candidates = self._scan_candidates(date, core_sectors)
                for code, info in candidates:
                    if len(self.positions) >= CONFIG['max_daily_buy']:
                        break
                    if any(p['code'] == code for p in self.positions):
                        continue
                    if self._confirm_and_buy(date, code, info):
                        pass

            # ---- 记录 ----
            total_value = self.capital
            for pos in self.positions:
                df = self.universe.get(pos['code'])
                if df is not None:
                    try:
                        idx = df.index.get_loc(date)
                        total_value += pos['shares'] * df['close'].iloc[idx]
                    except:
                        total_value += pos['shares'] * pos['entry_price']
                else:
                    total_value += pos['shares'] * pos['entry_price']

            self.daily_equity.append({'date': date, 'equity': total_value, 'state': market_state})
            self.market_states.append(market_state)

        # 清仓
        for pos in self.positions:
            self._close_position(pos, 'end_of_period', trade_dates[-1])

    def _calibrate_rps(self, date):
        """周度校准RPS阈值"""
        core = self._get_core_sectors(date)
        core_count = len(core)
        if core_count < 2:
            self.rps_threshold = 82
        elif core_count > 10:
            self.rps_threshold = 88
        else:
            self.rps_threshold = 85
        self.last_calibrate_date = date

    def _get_core_sectors(self, date):
        """获取核心主线板块"""
        rps_sectors = sector_rps_filter(date, None, self.universe)
        top5_sectors = get_top_sectors_by_new_high(date, self.universe, 5)
        core = [s for s in rps_sectors if s in top5_sectors]
        return core if core else []

    def _scan_candidates(self, date, core_sectors):
        """扫描符合条件的个股候选"""
        candidates = []
        for code, df in self.universe.items():
            ok, info = stock_filter(date, code, df, self.sector_map, core_sectors)
            if ok:
                candidates.append((code, info))
        # 按量比排序
        candidates.sort(key=lambda x: x[1].get('vol_ratio', 0), reverse=True)
        return candidates[:10]

    def _confirm_and_buy(self, date, code, info):
        """买入执行"""
        df = self.universe.get(code)
        if df is None:
            return False

        close_today = info['close']
        position_value = self.capital * CONFIG['single_position']
        shares = int(position_value / (close_today * (1 + CONFIG['slippage']))) // 100 * 100
        if shares < 100:
            return False

        cost = shares * close_today * (1 + CONFIG['slippage']) * (1 + CONFIG['commission_rate'])
        if cost > self.capital * 0.2:
            return False

        self.capital -= cost
        self.positions.append({
            'code': code,
            'entry_date': date,
            'entry_price': close_today,
            'cost_basis': close_today * (1 + CONFIG['slippage']),
            'shares': shares,
            'holding_days': 0,
            'stop_loss': None,
            'market_state': self._last_market_state,  # 记录入场的市场状态
        })
        return True

    def _close_position(self, pos, reason, date):
        """平仓"""
        df = self.universe.get(pos['code'])
        if df is not None:
            try:
                idx = df.index.get_loc(date)
                exit_price = df['close'].iloc[idx]
            except:
                exit_price = pos['entry_price']
        else:
            exit_price = pos['entry_price']

        exit_value = pos['shares'] * exit_price * (1 - CONFIG['slippage']) * (1 - CONFIG['commission_rate'])
        self.capital += exit_value

        pnl = exit_value - pos['shares'] * pos['cost_basis']
        pnl_pct = pnl / (pos['shares'] * pos['cost_basis']) * 100

        self.closed_trades.append({
            **pos,
            'exit_date': date,
            'exit_price': exit_price,
            'exit_reason': reason,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
        })

    def report(self):
        """生成回测报告"""
        equity_df = pd.DataFrame(self.daily_equity)
        equity_df['date'] = pd.to_datetime(equity_df['date'])
        equity_df = equity_df.set_index('date')

        total_return = (equity_df['equity'].iloc[-1] / CONFIG['initial_capital'] - 1) * 100

        # 年化收益
        days = (equity_df.index[-1] - equity_df.index[0]).days
        annual_return = ((1 + total_return/100) ** (365/days) - 1) * 100

        # 最大回撤
        equity_series = equity_df['equity']
        peak = equity_series.expanding().max()
        drawdown = (equity_series - peak) / peak * 100
        max_drawdown = drawdown.min()

        # 夏普比率
        daily_returns = equity_df['equity'].pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0

        # 交易统计
        trades = self.closed_trades
        n_trades = len(trades)
        wins = [t for t in trades if t['pnl'] > 0]
        win_rate = len(wins) / n_trades * 100 if n_trades > 0 else 0
        avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl_pct'] for t in trades if t['pnl'] <= 0]) if n_trades > len(wins) else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 and avg_win != 0 else 0

        # 最大连续亏损
        pnl_series = [t['pnl'] for t in trades]
        max_consec_loss = 0
        curr_streak = 0
        for pnl in pnl_series:
            if pnl < 0:
                curr_streak += 1
                max_consec_loss = max(max_consec_loss, curr_streak)
            else:
                curr_streak = 0

        # 分市场状态统计
        state_stats = {}
        for state in ['上涨', '震荡', '下跌']:
            state_trades = [t for t in trades if t.get('market_state', '') == state]
            if state_trades:
                state_win_rate = len([t for t in state_trades if t['pnl'] > 0]) / len(state_trades) * 100
                state_stats[state] = {
                    'trades': len(state_trades),
                    'win_rate': state_win_rate,
                    'avg_pnl': np.mean([t['pnl_pct'] for t in state_trades]),
                }

        report = f"""
{'='*60}
            量化回测报告
{'='*60}

回测区间: {equity_df.index[0].strftime('%Y-%m-%d')} ~ {equity_df.index[-1].strftime('%Y-%m-%d')}
初始资金: {CONFIG['initial_capital']:,.0f} 元
最终资金: {equity_df['equity'].iloc[-1]:,.0f} 元

--- 核心指标 ---
总收益率:     {total_return:+.2f}%
年化收益率:   {annual_return:+.2f}%
最大回撤:     {max_drawdown:+.2f}%
夏普比率:     {sharpe:.2f}
交易次数:     {n_trades}
胜率:         {win_rate:.1f}%
盈亏比:       {profit_factor:.2f}
最大连续亏损: {max_consec_loss} 次

--- 分市场状态表现 ---"""
        for state, stats in state_stats.items():
            report += f"""
  {state}市: 交易{stats['trades']}次  胜率{stats['win_rate']:.1f}%  均收益{stats['avg_pnl']:+.2f}%"""

        report += f"""
{'='*60}"""
        return report

# ============================================================
# 7. 主程序
# ============================================================

def main():
    print('=' * 50)
    print('  量化回测系统 v1.0')
    print('=' * 50)

    # 1. 加载上证指数
    print('\n[1/5] 加载上证指数数据...')
    index_df = load_index_data()
    print(f'  上证指数: {len(index_df)} 条日线 ({index_df.index[0].date()} ~ {index_df.index[-1].date()})')

    # 2. 加载股票列表
    print('\n[2/5] 加载个股数据...')
    stock_data = load_stock_list()
    print(f'  本地缓存: {len(stock_data)} 只个股')

    # 3. 加载行业映射
    print('\n[3/5] 加载行业映射...')
    sector_map = load_sector_map()
    print(f'  行业映射: {len(sector_map)} 只个股')
    if not sector_map:
        print('  ⚠️ 无行业映射文件，将跳过板块筛选')

    # 4. 准备个股数据
    print('\n[4/5] 对齐数据...')
    universe = prepare_stock_universe(stock_data, index_df)
    print(f'  可用个股: {len(universe)} 只 (回测区间: {index_df.index[0].date()} ~ {index_df.index[-1].date()})')

    # 5. 运行回测
    print(f'\n[5/5] 运行回测 ({CONFIG["start_date"]} ~ {CONFIG["end_date"]})...')
    engine = BacktestEngine(index_df, universe, sector_map)
    engine.run()

    # 6. 输出报告
    report = engine.report()
    print(report)

    # 保存报告
    report_path = os.path.join(CONFIG['output_dir'], '回测报告_20260704.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'\n报告已保存: {report_path}')

if __name__ == '__main__':
    main()
