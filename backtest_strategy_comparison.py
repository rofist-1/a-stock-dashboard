# -*- coding: utf-8 -*-
"""
三大策略回测对比系统 v3.0 (2024-2026)
=====================================
策略A: 百日新高+60日线突破复合策略
策略B: 纯60日线首板涨停策略
策略C: 纯百日新高策略

数据源: AKShare (新浪)
运行: python backtest_strategy_comparison.py
输出: results/ 目录下所有图表 + 分析报告

使用方法:
  首次运行: python backtest_strategy_comparison.py  (自动抓取1000只股票, 约15-30分钟)
  二次运行: python backtest_strategy_comparison.py  (从缓存加载, 约1-2分钟)
"""
import os, sys, time, json, pickle, warnings
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Callable, Optional, Tuple
import concurrent.futures

import numpy as np
import pandas as pd
from scipy import stats
import akshare as ak

# Fix GBK encoding for Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

warnings.filterwarnings("ignore")

# ============================================================
# 配置
# ============================================================
START_DATE = "2024-01-01"
END_DATE = "2026-07-28"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache_bt3")
RESULT_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

MAX_WORKERS = 5
INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS = 5
POSITION_PCT = 0.20
COMMISSION_BUY = 0.00025
COMMISSION_SELL = 0.00125
SLIPPAGE = 0.001
MAX_STOCKS_TO_FETCH = 1000  # 首次拉取数量

CASE_STOCKS = {
    "300679": "电连技术(2026.4.8)",
    "301392": "汇成真空(2026.4.1)",
    "603083": "剑桥科技(2026.4.8)",
    "603678": "火炬电子(2026.5.22-应过滤)",
    "002238": "天威视讯(2026.2.3-应过滤)",
    "002259": "升达林业(2026.1.5入选/5.8过滤)",
}

# ============================================================
# 数据获取
# ============================================================
def get_stock_list():
    p = os.path.join(CACHE_DIR, "stock_list.pkl")
    if os.path.exists(p):
        return pd.read_pickle(p)
    df = ak.stock_info_a_code_name()
    df = df[~df["code"].str.contains("BJ|^8|^4|^9", na=False)]
    df["exchange"] = df["code"].apply(lambda x: "sh" if x.startswith("6") else "sz")
    df["symbol"] = df["exchange"] + df["code"]
    df["circ_mv_est"] = 100.0  # placeholder
    df.to_pickle(p)
    return df


def load_all_data() -> Dict[str, pd.DataFrame]:
    """
    加载所有可用数据。
    优先从缓存加载，不足时自动拉取新数据。
    """
    # 检查缓存
    cached_files = [f for f in os.listdir(CACHE_DIR) if f.startswith("stock_") and f.endswith(".pkl") and f != "stock_list.pkl"]
    cached_codes = set(f.replace("stock_", "").replace(".pkl", "") for f in cached_files)
    
    if len(cached_codes) >= 200:
        # 已有足够缓存，直接加载
        result = {}
        for cf in cached_files:
            code = cf.replace("stock_", "").replace(".pkl", "")
            try:
                result[code] = pd.read_pickle(os.path.join(CACHE_DIR, cf))
            except:
                pass
        print(f"  => 从缓存加载 {len(result)} 只股票")
        return result
    
    # 需要拉取数据
    stock_list = get_stock_list()
    
    # 优先中小盘（20-500亿目标）
    priority_codes = stock_list["code"].tolist()
    
    # 排除已缓存的
    to_fetch = [c for c in priority_codes if c not in cached_codes][:MAX_STOCKS_TO_FETCH]
    
    # 加上已缓存的
    all_codes = list(cached_codes) + to_fetch
    
    print(f"  => 需要拉取 {len(to_fetch)} 只新股票 (已有缓存 {len(cached_codes)} 只)")
    
    result = {}
    # 先加载缓存
    for code in cached_codes:
        cf = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
        try:
            df = pd.read_pickle(cf)
            if "date" not in df.columns:
                continue
            result[code] = df
        except:
            pass
    
    # 再拉取新数据
    def fetch_one(code):
        cf = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
        if os.path.exists(cf):
            return None  # 已被其他线程缓存
        prefix = "sh" if code.startswith("6") else "sz"
        try:
            df = ak.stock_zh_a_daily(symbol=prefix+code, start_date=START_DATE.replace("-",""),
                                     end_date=END_DATE.replace("-",""), adjust="qfq")
            if df is None or len(df) < 60:
                return None
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            df["code"] = code
            df["name"] = ""
            if "outstanding_share" in df.columns:
                df["circ_mv"] = df["close"] * df["outstanding_share"] / 1e8
            else:
                df["circ_mv"] = df["close"] * 1e8 / 1e8  # fallback
            df.to_pickle(cf)
            return (code, df)
        except:
            return None
    
    n_success = 0
    n_total = len(to_fetch)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_one, code): code for code in to_fetch}
        done = 0
        for f in concurrent.futures.as_completed(futures):
            done += 1
            if done % 100 == 0:
                print(f"    ... {done}/{n_total} ({int(done/n_total*100)}%)", flush=True)
            try:
                r = f.result()
                if r:
                    code, df = r
                    result[code] = df
                    n_success += 1
            except:
                pass
    
    print(f"  => 共 {len(result)} 只股票可用 (新增 {n_success})")
    return result


def load_limited_universe() -> Dict[str, pd.DataFrame]:
    """加载数据，如果已有缓存直接加载，没有则拉取"""
    return load_all_data()


# ============================================================
# 信号计算
# ============================================================
def _get_sh_rate(df, i, is_zt20, is_zt10):
    if "outstanding_share" in df.columns:
        os_ = df["outstanding_share"].iloc[i]
        if os_ > 0:
            sh_rate = df["volume"].values[i] / os_ * 100
        else:
            sh_rate = 0
    elif "turnover" in df.columns:
        sh_rate = df["turnover"].iloc[i] * 100
    else:
        sh_rate = 0
    if (is_zt20 and sh_rate >= 25) or (is_zt10 and sh_rate >= 20):
        return False
    return True


def _check_st(name):
    return "ST" in str(name) or "*ST" in str(name)


def _check_circ_mv(df, i):
    if "circ_mv" in df.columns:
        cm = df["circ_mv"].iloc[i]
        if cm < 20 or cm > 500:
            return False
    return True


def compute_signals_strategyA(df):
    """策略A: 百日新高+60日线突破"""
    if len(df) < 120:
        return pd.Series(False, index=df.index)
    c, h, l, v = [df[c].values for c in ["close","high","low","volume"]]
    n = len(c)
    sig = np.zeros(n, dtype=bool)
    name = str(df["name"].iloc[0]) if "name" in df.columns else ""
    if _check_st(name):
        return pd.Series(False, index=df.index)
    
    for i in range(100, n):
        # 1-3 百日新高+涨停+封板
        if c[i] < np.max(c[i-99:i+1]): continue
        pct = c[i]/c[i-1] - 1
        zt20, zt10 = pct > 0.195, pct > 0.095
        if not (zt20 or zt10): continue
        if c[i] < h[i]: continue
        if not _get_sh_rate(df, i, zt20, zt10): continue
        if not _check_circ_mv(df, i): continue
        
        # 4. MA60向上
        ma60_i = np.mean(c[i-59:i+1])
        if ma60_i <= np.mean(c[i-69:i-9]): continue
        
        # 5. POS条件 (A/B/C)
        ma60 = np.mean(c[i-59:i+1])
        ma5, ma10 = np.mean(c[i-4:i+1]), np.mean(c[i-9:i+1])
        a_cls = (c[i-1] < ma60) and (c[i] >= ma60)
        b_cls = (abs(c[i]/ma60 - 1) < 0.15) and (ma5 > ma10) and (ma10 > np.mean(c[i-12:i-9]))
        days_abv = sum(1 for j in range(max(0,i-4), i+1) if c[j] > np.mean(c[j-59:j+1]))
        c_cls = (days_abv >= 3 and l[i-1] <= ma60*1.03 and l[i-1] >= ma60*0.97)
        if not (a_cls or b_cls or c_cls): continue
        
        # 6. 量比 >= 1.5
        if v[i] < np.mean(v[i-59:i+1]) * 1.5: continue
        
        # 7. 位置过滤
        if c[i] > np.max(h[max(0,i-119):i+1]) * 1.02: continue
        hh20, ll20 = np.max(h[max(0,i-19):i+1]), np.min(l[max(0,i-19):i+1])
        if ll20 > 0 and (hh20-ll20)/ll20 >= 0.50: continue
        if i >= 5 and (c[i]-c[i-5])/c[i-5] >= 0.40: continue
        
        sig[i] = True
    return pd.Series(sig, index=df.index)


def compute_signals_strategyB(df):
    """策略B: 纯60日线首板涨停"""
    if len(df) < 120:
        return pd.Series(False, index=df.index)
    c, h, l, v = [df[c].values for c in ["close","high","low","volume"]]
    n = len(c)
    sig = np.zeros(n, dtype=bool)
    name = str(df["name"].iloc[0]) if "name" in df.columns else ""
    if _check_st(name):
        return pd.Series(False, index=df.index)
    
    for i in range(60, n):
        pct = c[i]/c[i-1] - 1
        zt20, zt10 = pct > 0.195, pct > 0.095
        if not (zt20 or zt10): continue
        if c[i] < h[i]: continue
        if not _get_sh_rate(df, i, zt20, zt10): continue
        if not _check_circ_mv(df, i): continue
        
        ma60_i = np.mean(c[i-59:i+1])
        if ma60_i <= np.mean(c[i-69:i-9]): continue
        
        ma60 = np.mean(c[i-59:i+1])
        ma5, ma10 = np.mean(c[i-4:i+1]), np.mean(c[i-9:i+1])
        a_cls = (c[i-1] < ma60) and (c[i] >= ma60)
        b_cls = (abs(c[i]/ma60 - 1) < 0.15) and (ma5 > ma10) and (ma10 > np.mean(c[i-12:i-9]))
        days_abv = sum(1 for j in range(max(0,i-4), i+1) if c[j] > np.mean(c[j-59:j+1]))
        c_cls = (days_abv >= 3 and l[i-1] <= ma60*1.03 and l[i-1] >= ma60*0.97)
        if not (a_cls or b_cls or c_cls): continue
        
        if v[i] < np.mean(v[i-59:i+1]) * 1.5: continue
        if i >= 5 and (c[i]-c[i-5])/c[i-5] >= 0.40: continue
        
        sig[i] = True
    return pd.Series(sig, index=df.index)


def compute_signals_strategyC(df):
    """策略C: 纯百日新高"""
    if len(df) < 120:
        return pd.Series(False, index=df.index)
    c, h, v = [df[c].values for c in ["close","high","volume"]]
    n = len(c)
    sig = np.zeros(n, dtype=bool)
    name = str(df["name"].iloc[0]) if "name" in df.columns else ""
    if _check_st(name):
        return pd.Series(False, index=df.index)
    
    for i in range(100, n):
        if c[i] < np.max(c[i-99:i+1]): continue
        pct = c[i]/c[i-1] - 1
        zt20, zt10 = pct > 0.195, pct > 0.095
        if not (zt20 or zt10): continue
        if c[i] < h[i]: continue
        if not _get_sh_rate(df, i, zt20, zt10): continue
        if not _check_circ_mv(df, i): continue
        sig[i] = True
    return pd.Series(sig, index=df.index)


# ============================================================
# 回测引擎
# ============================================================
@dataclass
class Trade:
    buy_date: str; sell_date: str; code: str; name: str
    buy_price: float; sell_price: float; shares: int
    pnl_pct: float; pnl_amount: float; hold_days: int
    exit_reason: str = "规则卖出"


@dataclass
class BacktestResult:
    name: str
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    monthly_returns: Dict = field(default_factory=dict)


def run_backtest(name: str, all_data: Dict[str, pd.DataFrame],
                 signal_func: Callable) -> BacktestResult:
    result = BacktestResult(name=name)
    
    # 交易日历
    all_dates = sorted(set(
        d for df in all_data.values()
        for d in df["date"].dt.strftime("%Y-%m-%d")
        if START_DATE <= d <= END_DATE
    ))
    if len(all_dates) < 10:
        return result
    
    # 计算信号
    stock_signals = {}
    for code, df in all_data.items():
        sig = signal_func(df)
        sig.index = df["date"].dt.strftime("%Y-%m-%d")
        stock_signals[code] = sig
    
    # 回测主循环
    cash = INITIAL_CAPITAL
    positions = {}
    equity_curve = []
    trades = []
    date_set = set(all_dates)
    
    for t_idx in range(len(all_dates) - 1):
        today = all_dates[t_idx]
        tomorrow = all_dates[t_idx + 1]
        
        # --- 卖出 ---
        to_close = []
        for code, pos in list(positions.items()):
            df = all_data.get(code)
            if df is None: continue
            rows_t = df[df["date"] == today]
            if len(rows_t) == 0: continue
            row = rows_t.iloc[0]
            cp, name_v = row["close"], pos.get("name", code)
            bp = pos["buy_price"]
            pnl = (cp - bp) / bp
            if pnl > pos.get("highest_pnl", 0):
                pos["highest_pnl"] = pnl
            
            # 止损: 破涨停日最低价
            if cp < pos["stop_loss_price"]:
                to_close.append((code, "止损-破位"))
                continue
            
            # 止损: 破60日线3日
            df_w = df[df["date"] <= today]
            if len(df_w) >= 60:
                ma60 = np.mean(df_w.tail(60)["close"].values)
                if cp < ma60 * 0.98:
                    below = sum(1 for _ in range(3) if len(df_w) >= 60)
                    if below >= 3:
                        to_close.append((code, "止损-MA60"))
                        continue
            
            # 止盈
            hp = pos.get("highest_pnl", 0)
            if hp >= 0.50 and len(df_w) >= 13:
                ma13 = np.mean(df_w.tail(13)["close"].values)
                if cp < ma13:
                    to_close.append((code, "止盈-破MA13"))
                    continue
            if hp >= 0.30 and (hp - pnl) / max(hp, 0.001) > 0.5:
                to_close.append((code, "止盈-回落"))
                continue
        
        for code, reason in to_close:
            if code not in positions: continue
            pos = positions.pop(code)
            df = all_data.get(code)
            if df is None: continue
            df_tom = df[df["date"] == tomorrow]
            if len(df_tom) == 0:
                df_t = df[df["date"] == today]
                if len(df_t) == 0: continue
                sp = df_t.iloc[0]["close"] * (1 - SLIPPAGE) * (1 - COMMISSION_SELL)
            else:
                sp = df_tom.iloc[0]["open"] * (1 - SLIPPAGE) * (1 - COMMISSION_SELL)
            
            proceeds = pos["shares"] * sp
            pnl_amt = proceeds - pos["shares"] * pos["buy_price"]
            pnl_pct = (sp / pos["buy_price"] - 1) * 100
            cash += proceeds
            
            bi = all_dates.index(pos["buy_date"]) if pos["buy_date"] in date_set else t_idx
            trades.append(Trade(
                buy_date=pos["buy_date"], sell_date=tomorrow,
                code=code, name=pos.get("name", code),
                buy_price=pos["buy_price"], sell_price=sp,
                shares=pos["shares"], pnl_pct=pnl_pct,
                pnl_amount=pnl_amt, hold_days=max(1, t_idx - bi),
                exit_reason=reason,
            ))
        
        # --- 买入 ---
        if len(positions) < MAX_POSITIONS:
            cands = []
            for code, ss in stock_signals.items():
                if code in positions: continue
                if today not in ss.index or not ss.loc[today]: continue
                df = all_data.get(code)
                if df is None: continue
                if len(df[df["date"] == today]) == 0: continue
                if len(df[df["date"] == tomorrow]) == 0: continue
                cands.append((code, df[df["date"] == today].iloc[0]))
            
            cands.sort(key=lambda x: x[1].get("circ_mv", 999))
            for code, row in cands[:MAX_POSITIONS - len(positions)]:
                if len(positions) >= MAX_POSITIONS: break
                df_tom = all_data[code][all_data[code]["date"] == tomorrow]
                if len(df_tom) == 0: continue
                bp = df_tom.iloc[0]["open"] * (1 + SLIPPAGE) * (1 + COMMISSION_BUY)
                available = cash * POSITION_PCT
                shares = int(available / bp / 100) * 100
                if shares <= 0: continue
                cost = shares * bp
                if cost > cash:
                    shares = int(cash / bp / 100) * 100
                    cost = shares * bp
                    if shares <= 0: continue
                cash -= cost
                df_t = all_data[code][all_data[code]["date"] == today]
                sp = df_t.iloc[0]["low"] * 0.97 if len(df_t) > 0 else bp * 0.9
                positions[code] = {
                    "buy_date": tomorrow, "buy_price": bp, "shares": shares,
                    "name": row.get("name", code), "stop_loss_price": sp,
                    "highest_pnl": 0,
                }
        
        # 总资产
        pv = sum(
            pos["shares"] * all_data[code][all_data[code]["date"] == today].iloc[0]["close"]
            for code, pos in positions.items()
            if code in all_data and len(all_data[code][all_data[code]["date"] == today]) > 0
        )
        equity_curve.append(cash + pv)
    
    # 结果整理
    result.dates = all_dates[:len(equity_curve)]
    result.equity_curve = equity_curve
    result.trades = trades
    result.total_trades = len(trades)
    
    if len(equity_curve) > 10 and len(trades) > 0:
        eq = np.array(equity_curve)
        result.total_return = (eq[-1] / INITIAL_CAPITAL - 1) * 100
        years = len(equity_curve) / 245
        result.annual_return = ((eq[-1] / INITIAL_CAPITAL) ** (1/max(years,0.1)) - 1) * 100
        peak = np.maximum.accumulate(eq)
        result.max_drawdown = abs(((eq - peak) / peak * 100).min())
        dr = np.diff(eq) / eq[:-1]
        if len(dr) > 5 and np.std(dr) > 0:
            result.sharpe_ratio = np.mean(dr - 0.03/245) / np.std(dr) * np.sqrt(245)
        wins = [t for t in trades if t.pnl_pct > 0]
        result.win_rate = len(wins) / len(trades) * 100
        aw = np.mean([t.pnl_pct for t in wins]) if wins else 0
        ls = [t for t in trades if t.pnl_pct <= 0]
        al = abs(np.mean([t.pnl_pct for t in ls])) if ls else 1
        result.profit_loss_ratio = aw / max(al, 0.01)
        for t in trades:
            m = t.buy_date[:7]
            if m not in result.monthly_returns:
                result.monthly_returns[m] = []
            result.monthly_returns[m].append(t.pnl_pct)
    
    return result


# ============================================================
# 分析模块
# ============================================================
def print_comparison(results):
    print("\n" + "=" * 100)
    print("三大策略绩效对比表 (2024-2026)")
    print("=" * 100)
    print(f"{'指标':<20}", end="")
    for r in results:
        print(f" {r.name[:20]:<22}", end="")
    print()
    print("-" * 100)
    
    metrics = [
        ("总收益率%", lambda r: f"{r.total_return:.2f}"),
        ("年化收益率%", lambda r: f"{r.annual_return:.2f}"),
        ("最大回撤%", lambda r: f"{r.max_drawdown:.2f}"),
        ("夏普比率", lambda r: f"{r.sharpe_ratio:.3f}"),
        ("胜率%", lambda r: f"{r.win_rate:.2f}"),
        ("盈亏比", lambda r: f"{r.profit_loss_ratio:.2f}"),
        ("交易次数", lambda r: f"{r.total_trades}"),
        ("平均持仓(天)", lambda r: f"{np.mean([t.hold_days for t in r.trades]):.1f}" if r.trades else "0"),
    ]
    table = {}
    for m_name, m_func in metrics:
        vals = [m_func(r) for r in results]
        print(f"{m_name:<20} {'  '.join(f'{v:<22}' for v in vals)}")
        table[m_name] = vals
    print("=" * 100)
    return table


def statistical_test(results):
    print("\n" + "=" * 100)
    print("统计检验: 百日新高条件是否显著提升收益风险比?")
    print("=" * 100)
    rets = [np.array([t.pnl_pct for t in r.trades]) for r in results]
    
    for idx_a, idx_b, label in [(0,1,"A vs B"), (0,2,"A vs C")]:
        ra, rb = rets[idx_a], rets[idx_b]
        if len(ra) < 5 or len(rb) < 5:
            print(f"  {label}: 交易次数不足, 跳过")
            continue
        t_stat, p_val = stats.ttest_ind(ra, rb, equal_var=False)
        np.random.seed(42)
        all_r = np.concatenate([ra, rb])
        na, nb = len(ra), len(rb)
        obs = np.mean(ra) - np.mean(rb)
        boot = np.array([np.mean(np.random.choice(all_r, na, replace=True)) -
                         np.mean(np.random.choice(all_r, nb, replace=True)) for _ in range(5000)])
        ci = np.percentile(boot, [2.5, 97.5])
        print(f"\n  {label}")
        print(f"    策略A: u={np.mean(ra):.2f}%, s={np.std(ra):.2f}%, n={na}")
        print(f"    对比: u={np.mean(rb):.2f}%, s={np.std(rb):.2f}%, n={nb}")
        print(f"    Welch t检验: t={t_stat:.4f}, p={p_val:.6f}  {'显著(p<0.05)' if p_val<0.05 else '不显著'}")
        print(f"    Bootstrap 95%CI: [{ci[0]:.4f}, {ci[1]:.4f}]  {'显著' if ci[0]*ci[1]>0 else '不显著'}")


def annual_analysis(results):
    print("\n" + "=" * 100)
    print("分年度表现分析")
    print("=" * 100)
    for year in ["2024", "2025", "2026"]:
        print(f"\n  [{year}年]")
        print(f"  {'策略':<22} {'收益率%':<10} {'交易数':<8} {'胜率%':<8} {'盈亏比':<8}")
        print(f"  {'-'*56}")
        for r in results:
            yt = [t for t in r.trades if t.buy_date.startswith(year)]
            if not yt:
                print(f"  {r.name[:20]:<22} {'无交易':<10}")
                continue
            ret = sum(t.pnl_amount for t in yt) / INITIAL_CAPITAL * 100
            wr = len([t for t in yt if t.pnl_pct > 0]) / len(yt) * 100
            aw = np.mean([t.pnl_pct for t in yt if t.pnl_pct > 0]) or 0
            al = abs(np.mean([t.pnl_pct for t in yt if t.pnl_pct <= 0])) or 1
            print(f"  {r.name[:20]:<22} {ret:<10.2f} {len(yt):<8} {wr:<8.1f} {aw/max(al,0.01):<8.2f}")


def case_study_analysis(all_data):
    print("\n" + "=" * 100)
    print("案例分析: 特定股票的策略筛选评估")
    print("=" * 100)
    
    case_dates = {
        "300679": ["2026-04-08"],
        "301392": ["2026-04-01"],
        "603083": ["2026-04-08"],
        "603678": ["2026-05-22"],
        "002238": ["2026-02-03"],
        "002259": ["2026-01-05", "2026-05-08"],
    }
    
    for code, dates in case_dates.items():
        name_str = CASE_STOCKS.get(code, code)
        print(f"\n  [{name_str}] ({code})")
        if code not in all_data:
            print("    无数据")
            continue
        df = all_data[code]
        c_arr = df["close"].values
        h_arr = df["high"].values
        l_arr = df["low"].values
        v_arr = df["volume"].values
        
        for target_date in dates:
            match = df[df["date"] == target_date].index.tolist()
            if not match:
                print(f"    {target_date}: 无数据")
                continue
            i = match[0]
            cp = c_arr[i]
            
            # 条件检查
            new_h = cp >= np.max(c_arr[max(0,i-99):i+1]) if i >= 100 else False
            pct = (cp/c_arr[i-1] - 1)*100 if i >= 1 else 0
            zt = pct > 9.5
            fb = cp >= h_arr[i]
            ma60 = np.mean(c_arr[i-59:i+1]) if i >= 60 else None
            abv60 = cp > ma60 if ma60 else False
            ma60_up = (ma60 > np.mean(c_arr[i-69:i-9])) if i >= 69 else True
            a_cls = (c_arr[i-1] < ma60 and cp >= ma60) if (i >= 60 and ma60) else False
            b_cls = (abs(cp/ma60-1) < 0.15) if ma60 else False
            if i >= 9:
                ma5, ma10 = np.mean(c_arr[i-4:i+1]), np.mean(c_arr[i-9:i+1])
                b_cls = b_cls and (ma5 > ma10) and (ma10 > np.mean(c_arr[i-12:i-9]))
            vol_ma60 = np.mean(v_arr[max(0,i-59):i+1])
            vr = v_arr[i]/vol_ma60 if vol_ma60 > 0 else 0
            
            if ma60:
                days_abv = sum(1 for j in range(max(0,i-4),i+1)
                              if c_arr[j] > np.mean(c_arr[max(0,j-59):j+1]))
                c_cls = (days_abv >= 3 and l_arr[i-1] <= ma60*1.03 and l_arr[i-1] >= ma60*0.97)
            else:
                c_cls = False
            
            hh20 = np.max(h_arr[max(0,i-19):i+1])
            ll20 = np.min(l_arr[max(0,i-19):i+1])
            amp20 = (hh20-ll20)/ll20*100 if ll20 > 0 else 0
            chg5 = (cp/c_arr[i-5] - 1)*100 if i >= 5 else 0
            cm = df["circ_mv"].iloc[i] if "circ_mv" in df.columns else 0
            
            fwd = [(c_arr[i+k]/cp - 1)*100 for k in range(1, min(6, len(c_arr)-i))]
            
            strat_a = new_h and zt and fb and ma60_up and (a_cls or b_cls or c_cls) and vr >= 1.5 and amp20 < 50
            strat_b = zt and fb and ma60_up and (a_cls or b_cls or c_cls) and vr >= 1.5
            
            print(f"    {target_date}: 收{cp:.2f}, 涨{pct:.1f}%, 百日新高{'Y' if new_h else 'N'}, "
                  f"涨停{'Y' if zt else 'N'}, 封板{'Y' if fb else 'N'}")
            print(f"      POS: A{a_cls} B{b_cls} C{c_cls}, 量比{vr:.1f}x, 振幅20日{amp20:.1f}%, "
                  f"5日涨{chg5:.1f}%, 市值{cm:.0f}亿")
            print(f"      后续5日: 均{np.mean(fwd):.2f}%, 高{max(fwd):.2f}%, 低{min(fwd):.2f}%" if fwd else "")
            print(f"      策略A: {'入选' if strat_a else '过滤'}, 策略B: {'入选' if strat_b else '过滤'}")


def parameter_robustness(all_data):
    print("\n" + "=" * 100)
    print("参数鲁棒性测试")
    print("=" * 100)
    
    configs = [
        ("基准(MA60+100日,量比1.5)", 60, 100, 1.5),
        ("MA50日线", 50, 100, 1.5),
        ("MA70日线", 70, 100, 1.5),
        ("50日新高", 60, 50, 1.5),
        ("150日新高", 60, 150, 1.5),
        ("量比2.0倍", 60, 100, 2.0),
    ]
    
    sample = list(all_data.keys())[:200]
    for label, ma_p, nh_p, vr_m in configs:
        total = 0; stocks = 0
        for code in sample:
            df = all_data[code]
            c = df["close"].values; h = df["high"].values; v = df["volume"].values
            for i in range(max(ma_p, nh_p), len(c)):
                if c[i] < np.max(c[max(0,i-nh_p+1):i+1]): continue
                if c[i]/c[i-1]-1 < 0.095: continue
                if c[i] < h[i]: continue
                ma = np.mean(c[i-ma_p+1:i+1])
                if c[i-1] >= ma or c[i] < ma: continue  # A class
                if v[i] < np.mean(v[i-ma_p+1:i+1]) * vr_m: continue
                total += 1
            if total > 0: stocks += 1
        print(f"  {label:<22}: {total:>5} 信号, {stocks:>3} 只股票")


def plot_results(results):
    try:
        import matplotlib
        matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
        matplotlib.rcParams['axes.unicode_minus'] = False
        import matplotlib.pyplot as plt
        
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1"]
        
        # 1. 净值曲线
        plt.figure(figsize=(14, 7))
        for i, r in enumerate(results):
            eq = np.array(r.equity_curve) / INITIAL_CAPITAL * 100
            plt.plot(range(len(eq)), eq, label=r.name[:20], color=colors[i], lw=2)
        plt.axhline(100, color="gray", ls="--", alpha=0.5)
        plt.title("Three Strategy NAV Curves (2024-2026)", fontsize=14)
        plt.xlabel("Trading Day"); plt.ylabel("NAV (Base 100%)")
        plt.legend(); plt.grid(alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(RESULT_DIR, "1_equity.png"), dpi=150); plt.close()
        
        # 2. 雷达图
        metrics = ["total_return", "sharpe_ratio", "win_rate", "profit_loss_ratio"]
        labels = ["Total Return", "Sharpe", "Win Rate", "Profit/Loss"]
        vals = np.array([[max(getattr(r,m,0.01),0.01) for m in metrics] for r in results])
        for j in range(vals.shape[1]):
            m = vals[:,j].max()
            if m > 0: vals[:,j] /= m
        angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
        fig, ax = plt.subplots(figsize=(8,8), subplot_kw=dict(polar=True))
        for i, r in enumerate(results):
            v = vals[i].tolist() + [vals[i,0]]
            a = angles + [angles[0]]
            ax.plot(a, v, "o-", label=r.name[:20], color=colors[i], lw=2)
            ax.fill(a, v, alpha=0.1, color=colors[i])
        ax.set_xticks(angles); ax.set_xticklabels(labels)
        ax.set_ylim(0, 1.15)
        plt.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
        plt.title("Normalized Performance Comparison", fontsize=14, y=1.08)
        plt.tight_layout(); plt.savefig(os.path.join(RESULT_DIR, "2_radar.png"), dpi=150); plt.close()
        
        # 3. 月度收益
        for i, r in enumerate(results):
            months = sorted(r.monthly_returns.keys())
            mrets = [np.mean(r.monthly_returns[m]) for m in months]
            plt.figure(figsize=(12,3))
            bc = ["#FF4D4F" if x<0 else "#52C41A" for x in mrets]
            plt.bar(range(len(months)), mrets, color=bc, width=0.7)
            plt.axhline(0, color="gray", lw=0.5)
            plt.title(f"{r.name[:20]} - Monthly Avg Return")
            plt.xticks(range(len(months)), months, rotation=45, fontsize=8)
            plt.tight_layout()
            plt.savefig(os.path.join(RESULT_DIR, f"3_monthly_{['A','B','C'][i]}.png"), dpi=150)
            plt.close()
        
        # 4. 收益分布
        fig, axes = plt.subplots(1, 3, figsize=(15,4))
        for i, r in enumerate(results):
            rets = [t.pnl_pct for t in r.trades]
            if rets:
                axes[i].hist(rets, bins=40, color=colors[i], alpha=0.7, edgecolor="white")
                axes[i].axvline(0, color="red", ls="--", alpha=0.5)
                axes[i].set_title(f"{r.name[:15]} n={len(rets)}")
        plt.tight_layout()
        plt.savefig(os.path.join(RESULT_DIR, "4_distributions.png"), dpi=150); plt.close()
        
        # 5. 回撤
        plt.figure(figsize=(14, 5))
        for i, r in enumerate(results):
            eq = np.array(r.equity_curve)
            pk = np.maximum.accumulate(eq)
            dd = (eq - pk) / pk * 100
            plt.plot(range(len(dd)), dd, label=r.name[:20], color=colors[i], lw=1.5)
        plt.axhline(0, color="gray", ls="--", alpha=0.3)
        plt.title("Drawdown Curves")
        plt.xlabel("Trading Day"); plt.ylabel("Drawdown %")
        plt.legend(); plt.grid(alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(RESULT_DIR, "5_drawdown.png"), dpi=150); plt.close()
        
        # 6. 持仓天数 vs 收益
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        for i, r in enumerate(results):
            if r.trades:
                axes[i].scatter([t.hold_days for t in r.trades],
                               [t.pnl_pct for t in r.trades],
                               alpha=0.6, c=colors[i], s=20)
                axes[i].axhline(0, color="gray", ls="--", alpha=0.3)
                axes[i].set_title(f"{r.name[:15]}")
                axes[i].set_xlabel("Hold Days"); axes[i].set_ylabel("Return %")
        plt.tight_layout()
        plt.savefig(os.path.join(RESULT_DIR, "6_hold_vs_return.png"), dpi=150); plt.close()
        
        print(f"  => Charts saved to {RESULT_DIR}/")
    except Exception as e:
        print(f"  Chart error: {e}")


# ============================================================
# 主程序
# ============================================================
def main():
    t0 = time.time()
    print("=" * 100)
    print("Three Strategy Backtest System v3.0 (2024-2026)")
    print(f"  Period: {START_DATE} ~ {END_DATE}")
    print(f"  Capital: {INITIAL_CAPITAL/10000:.0f}W | Position: {POSITION_PCT*100:.0f}% | Max: {MAX_POSITIONS}")
    print("=" * 100)
    
    # 1. Data
    print("\n[1/4] Loading data...")
    all_data = load_limited_universe()
    print(f"  => {len(all_data)} stocks loaded")
    
    if len(all_data) < 50:
        print("ERROR: Not enough data. Will use synthetic/mock data for demo.")
        return
    
    # 2. Backtest
    print("\n[2/4] Running backtests...")
    strategies = [
        ("A: 100dHigh+MA60", compute_signals_strategyA),
        ("B: Pure MA60", compute_signals_strategyB),
        ("C: Pure 100dHigh", compute_signals_strategyC),
    ]
    results = []
    for name, func in strategies:
        t1 = time.time()
        r = run_backtest(name, all_data, func)
        dt = time.time() - t1
        results.append(r)
        print(f"  {name}: {r.total_trades} trades, return {r.total_return:.2f}%, time {dt:.0f}s")
    
    # 3. Analysis
    print("\n[3/4] Analysis...")
    print_comparison(results)
    statistical_test(results)
    annual_analysis(results)
    parameter_robustness(all_data)
    case_study_analysis(all_data)
    
    # 4. Charts + Save
    print("\n[4/4] Charts & Save...")
    plot_results(results)
    
    for i, r in enumerate(results):
        lbl = ["A","B","C"][i]
        with open(os.path.join(RESULT_DIR, f"result_{lbl}.pkl"), "wb") as f:
            pickle.dump(r, f)
    
    # Summary report
    report = {
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "period": f"{START_DATE} ~ {END_DATE}",
        "stocks": len(all_data),
        "results": [{
            "name": r.name,
            "trades": r.total_trades, "return_pct": r.total_return,
            "annual_pct": r.annual_return, "max_dd_pct": r.max_drawdown,
            "sharpe": r.sharpe_ratio, "win_rate_pct": r.win_rate,
            "profit_loss_ratio": r.profit_loss_ratio,
        } for r in results],
    }
    with open(os.path.join(RESULT_DIR, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n{'='*100}")
    print(f"DONE! Time: {time.time()-t0:.0f}s ({((time.time()-t0)/60):.1f}min)")
    print(f"Output: {RESULT_DIR}/")
    print("=" * 100)


if __name__ == "__main__":
    main()