# -*- coding: utf-8 -*-
"""
策略B原版 + 大盘MA60过滤 + 集合竞价止损模拟
"""
import os, sys, time, json, pickle, warnings
import numpy as np
import pandas as pd
import akshare as ak
from collections import defaultdict, namedtuple

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache_bt3")
RESULT_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULT_DIR, exist_ok=True)

START, END = "2024-01-01", "2026-07-28"
INIT_CAP, MAX_POS, POS_PCT = 1_000_000, 5, 0.20
SLIP, CB, CS = 0.001, 0.00025, 0.00125

Trade = namedtuple("Trade", [
    "code","name","buy_date","sell_date","buy_price","sell_price",
    "pnl_pct","pnl_amount","hold_days","exit_reason"
])

# ===== 1. 加载上证指数 =====
def load_index_data():
    """返回三个dict: close_price, ma60, ma60_slope_up(date->bool)"""
    cache_f = os.path.join(CACHE_DIR, "index_000001.pkl")
    if not os.path.exists(cache_f):
        print("  下载上证指数数据...")
        idx = ak.stock_zh_index_daily(symbol="sh000001")
        idx.to_pickle(cache_f)
    else:
        idx = pd.read_pickle(cache_f)
    
    c = idx["close"].values
    d = idx["date"].values
    close_price, ma60_val, ma60_slope_up = {}, {}, {}
    for i in range(len(c)):
        d_str = pd.Timestamp(d[i]).strftime("%Y-%m-%d")
        close_price[d_str] = c[i]
        if i >= 59:
            m = np.mean(c[i-59:i+1])
            ma60_val[d_str] = m
            if i >= 64:
                m_prev = np.mean(c[i-64:i-4])
                ma60_slope_up[d_str] = m > m_prev  # 5日斜率
            else:
                ma60_slope_up[d_str] = True
    return close_price, ma60_val, ma60_slope_up

def market_ok(today, idx_close, idx_ma60, idx_slope, margin=0.0, slope_days=0):
    """
    判断大盘环境是否OK
    margin: 站上MA60的额外比例，0=仅站上，0.02=站上2%
    slope_days: 斜率天数，0=不检查
    """
    if today not in idx_close or today not in idx_ma60:
        return False
    c, m = idx_close[today], idx_ma60[today]
    if c <= m:
        return False
    if margin > 0 and c < m * (1 + margin):
        return False
    if slope_days > 0 and idx_slope.get(today, False) == False:
        return False
    return True

# ===== 2. 策略B信号 + 大盘过滤 =====
def compute_signals(df):
    """原版策略B + 大盘MA60向上过滤"""
    if len(df) < 120:
        return pd.Series(False, index=df.index), {}
    c,h,l,v = [df[c].values for c in ["close","high","low","volume"]]
    o = df["open"].values
    n = len(c)
    sig = np.zeros(n, dtype=bool)
    name = str(df["name"].iloc[0]) if "name" in df.columns else ""
    if "ST" in name or "*ST" in name or "退" in name:
        return pd.Series(False, index=df.index), {}
    
    # 预计算信号日的信息
    signal_info = {}
    
    for i in range(60, n):
        pct = c[i]/c[i-1] - 1
        zt20, zt10 = pct > 0.195, pct > 0.095
        if not (zt20 or zt10): continue
        if c[i] < h[i]: continue
        os_ = df["outstanding_share"].iloc[i] if "outstanding_share" in df.columns else 0
        sh = (v[i]/os_*100) if os_ > 0 else (df["turnover"].iloc[i]*100 if "turnover" in df.columns else 0)
        if (zt20 and sh >= 25) or (zt10 and sh >= 20): continue
        cm = df["circ_mv"].iloc[i] if "circ_mv" in df.columns else 0
        if cm < 20 or cm > 500: continue
        
        ma60 = np.mean(c[i-59:i+1])
        if ma60 <= np.mean(c[i-69:i-9]): continue
        ma5, ma10 = np.mean(c[i-4:i+1]), np.mean(c[i-9:i+1])
        a_cls = (c[i-1] < ma60) and (c[i] >= ma60)
        b_cls = (abs(c[i]/ma60 - 1) < 0.15) and (ma5 > ma10) and (ma10 > np.mean(c[i-12:i-9]))
        days_abv = sum(1 for j in range(max(0,i-4), i+1) if c[j] > np.mean(c[j-59:j+1]))
        c_cls = (days_abv >= 3 and l[i-1] <= ma60*1.03 and l[i-1] >= ma60*0.97)
        if not (a_cls or b_cls or c_cls): continue
        if v[i] < np.mean(v[i-59:i+1]) * 1.5: continue
        
        # 120日高点过滤（只要不是在120日最高点附近，排除追高）
        if c[i] > np.max(h[max(0,i-119):i+1]) * 1.02: continue
        # 20日振幅 < 50%
        hh20, ll20 = np.max(h[max(0,i-19):i+1]), np.min(l[max(0,i-19):i+1])
        if ll20 > 0 and (hh20-ll20)/ll20 >= 0.50: continue
        if i >= 5 and (c[i]-c[i-5])/c[i-5] >= 0.40: continue
        
        sig[i] = True
        d_str = pd.Timestamp(df["date"].iloc[i]).strftime("%Y-%m-%d")
        signal_info[d_str] = {"close": c[i], "open": o[i], "low": l[i], "date": df["date"].iloc[i], "circ_mv": cm}
    
    return pd.Series(sig, index=df.index), signal_info

# ===== 3. 回测引擎 =====
def run_backtest(all_data, idx_close, idx_ma60, idx_slope, use_index_filter=True, use_auction_stop=True,
                 margin=0.0, slope_days=0, label="默认"):
    all_dates = sorted(set(
        d for df in all_data.values()
        for d in df["date"].dt.strftime("%Y-%m-%d")
        if START <= d <= END
    ))
    if len(all_dates) < 10: return None
    
    # 信号预计算
    stock_signals = {}
    stock_info = {}
    for code, df in all_data.items():
        ss, si = compute_signals(df)
        ss.index = df["date"].dt.strftime("%Y-%m-%d")
        stock_signals[code] = ss
        stock_info[code] = si
    
    cash = INIT_CAP; positions = {}; trades = []; equity_curve = []
    date_set = set(all_dates)
    
    # 统计
    skipped_by_index = 0
    
    for t_idx in range(len(all_dates) - 1):
        today = all_dates[t_idx]
        tomorrow = all_dates[t_idx + 1]
        
        # --- 卖出（集合竞价止损模拟）---
        to_close = []
        for code, pos in list(positions.items()):
            df = all_data.get(code)
            if df is None: continue
            rows_t = df[df["date"] == today]
            if len(rows_t) == 0: continue
            row = rows_t.iloc[0]
            cp, lp = row["close"], row["low"]
            bp = pos["buy_price"]
            pnl = (cp - bp) / bp
            if pnl > pos.get("highest_pnl", 0):
                pos["highest_pnl"] = pnl
            
            # 止损v1: 破涨停日最低价（原版标准）
            if cp < pos.get("stop_loss_signal", 0):
                to_close.append((code, "止损-破位"))
                continue
            # 止损v2: 基于买入价固定8%
            if cp < bp * 0.92:
                to_close.append((code, "止损-8%"))
                continue
            # 止损v3: 盘中最低价破-10%（防跳空）
            if lp < bp * 0.90:
                to_close.append((code, "止损-跳空"))
                continue
            # 止损v4: 破60日线
            df_w = df[df["date"] <= today]
            if len(df_w) >= 60:
                ma60_val = np.mean(df_w.tail(60)["close"].values)
                if cp < ma60_val * 0.98:
                    below = sum(1 for _ in range(3) if len(df_w) >= 60)
                    if below >= 3:
                        to_close.append((code, "止损-MA60"))
                        continue
            
            # 止盈（原版）
            hp = pos["highest_pnl"]
            if hp >= 0.50 and len(df[df["date"] <= today]) >= 13:
                ma13 = np.mean(df[df["date"] <= today].tail(13)["close"].values)
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
            
            if use_auction_stop and ("止损" in reason):
                # 集合竞价止损模拟：假设能在集合竞价以高于次日开盘价1.5%成交
                # 因为散户可以在9:15挂高价卖出，实际成交价为开盘价附近
                if len(df_tom) == 0:
                    sp = df[df["date"] == today].iloc[0]["close"] * 0.99 * (1 - SLIP) * (1 - CS)
                else:
                    # 保守估计：集合竞价止损价比次日开盘价高1.5%
                    auction_price = df_tom.iloc[0]["open"] * 1.015
                    sp = auction_price * (1 - SLIP) * (1 - CS)
            else:
                # 原版逻辑：收盘判断 → 次日开盘卖
                if len(df_tom) == 0:
                    sp = df[df["date"] == today].iloc[0]["close"] * (1 - SLIP) * (1 - CS)
                else:
                    sp = df_tom.iloc[0]["open"] * (1 - SLIP) * (1 - CS)
            
            proceeds = pos["shares"] * sp
            pnl_amt = proceeds - pos["shares"] * pos["buy_price"]
            pnl_pct = (sp / pos["buy_price"] - 1) * 100
            cash += proceeds
            bi = all_dates.index(pos["buy_date"]) if pos["buy_date"] in date_set else t_idx
            trades.append(Trade(
                buy_date=pos["buy_date"], sell_date=tomorrow,
                code=code, name=pos.get("name", code),
                buy_price=pos["buy_price"], sell_price=sp,
                pnl_pct=pnl_pct, pnl_amount=pnl_amt,
                hold_days=max(1, t_idx - bi), exit_reason=reason,
            ))
        
        # --- 买入 ---
        if len(positions) < MAX_POS:
            cands = []
            for code, ss in stock_signals.items():
                if code in positions: continue
                if today not in ss.index or not ss.loc[today]: continue
                df = all_data.get(code)
                if df is None: continue
                if len(df[df["date"] == today]) == 0: continue
                if len(df[df["date"] == tomorrow]) == 0: continue
                
                # 大盘过滤
                if use_index_filter:
                    if not market_ok(today, idx_close, idx_ma60, idx_slope, margin=margin, slope_days=slope_days):
                        skipped_by_index += 1
                        continue
                
                cands.append((code, df[df["date"] == today].iloc[0]))
            
            cands.sort(key=lambda x: x[1].get("circ_mv", 999))
            for code, row in cands[:MAX_POS - len(positions)]:
                if len(positions) >= MAX_POS: break
                df_tom = all_data[code][all_data[code]["date"] == tomorrow]
                if len(df_tom) == 0: continue
                bp = df_tom.iloc[0]["open"] * (1 + SLIP) * (1 + CB)
                available = cash * POS_PCT
                shares = int(available / bp / 100) * 100
                if shares <= 0: continue
                cost = shares * bp
                if cost > cash:
                    shares = int(cash / bp / 100) * 100; cost = shares * bp
                    if shares <= 0: continue
                cash -= cost
                # 从signal_info获取信号日最低价计算止损
                try:
                    today_sig = stock_info[code].get(today, {})
                    signal_low = today_sig.get("low", bp * 0.9)
                except:
                    signal_low = bp * 0.9
                positions[code] = {
                    "buy_date": tomorrow, "buy_price": bp, "shares": shares,
                    "name": row.get("name", code), "highest_pnl": 0,
                    "stop_loss_signal": signal_low * 0.97,
                }
        
        pv = sum(
            pos["shares"] * all_data[code][all_data[code]["date"] == today].iloc[0]["close"]
            for code, pos in positions.items()
            if code in all_data and len(all_data[code][all_data[code]["date"] == today]) > 0
        )
        equity_curve.append(cash + pv)
    
    # 结果计算
    class Result: pass
    res = Result()
    res.trades = trades
    res.equity_curve = equity_curve
    res.dates = all_dates[:len(equity_curve)]
    res.skipped = skipped_by_index
    
    if len(equity_curve) > 10 and len(trades) > 0:
        eq = np.array(equity_curve)
        res.total_return = (eq[-1] / INIT_CAP - 1) * 100
        years = len(equity_curve) / 245
        res.annual_return = ((eq[-1] / INIT_CAP) ** (1/max(years,0.1)) - 1) * 100
        peak = np.maximum.accumulate(eq)
        res.max_drawdown = abs(((eq - peak) / peak * 100).min())
        dr = np.diff(eq) / eq[:-1]
        res.sharpe = np.mean(dr - 0.03/245) / np.std(dr) * np.sqrt(245) if len(dr) > 5 and np.std(dr) > 0 else 0
        wins = [t for t in trades if t.pnl_pct > 0]
        losses = [t for t in trades if t.pnl_pct <= 0]
        res.win_rate = len(wins) / len(trades) * 100
        aw = np.mean([t.pnl_pct for t in wins]) if wins else 0
        al = abs(np.mean([t.pnl_pct for t in losses])) if losses else 1
        res.profit_loss_ratio = aw / max(al, 0.01)
        res.num_wins = len(wins)
        res.num_losses = len(losses)
        res.avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0
        res.below_8 = sum(1 for t in losses if t.pnl_pct < -8) if losses else 0
    else:
        for attr in ["total_return","annual_return","max_drawdown","sharpe",
                     "win_rate","profit_loss_ratio","num_wins","num_losses",
                     "avg_loss","below_8"]:
            setattr(res, attr, 0)
    
    return res

def print_result(label, res):
    if res is None:
        print(f"  {label}: 无数据")
        return
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"  {'指标':<25} {'值':>15}")
    print(f"  {'-'*40}")
    print(f"  {'交易次数':<25} {len(res.trades):>15}")
    print(f"  {'总收益率%':<25} {res.total_return:>15.2f}")
    print(f"  {'年化%':<25} {res.annual_return:>15.2f}")
    print(f"  {'最大回撤%':<25} {res.max_drawdown:>15.2f}")
    print(f"  {'夏普':<25} {res.sharpe:>15.3f}")
    print(f"  {'胜率%':<25} {res.win_rate:>15.1f}")
    print(f"  {'盈亏比':<25} {res.profit_loss_ratio:>15.2f}")
    print(f"  {'盈利':<25} {res.num_wins:>15}")
    print(f"  {'亏损':<25} {res.num_losses:>15}")
    print(f"  {'平均亏损%':<25} {res.avg_loss:>15.2f}")
    print(f"  {'亏损<-8%笔数':<25} {res.below_8:>15}")
    
    # 分年度
    st = sorted(res.trades, key=lambda t: t.buy_date)
    for year in ["2024","2025","2026"]:
        yt = [t for t in st if t.buy_date.startswith(year)]
        if not yt: continue
        ret = sum(t.pnl_pct for t in yt)
        wr = len([t for t in yt if t.pnl_pct > 0]) / len(yt) * 100
        print(f"  {year}: {len(yt)}笔, 胜率{wr:.0f}%, 合计{ret:+.1f}%")

# ===== 主程序 =====
print("=" * 80)
print("策略B原版 + 大盘MA60过滤 + 集合竞价止损")
print("=" * 80)

# 下载沪深300
idx_close, idx_ma60, idx_slope = load_index_data()
# 统计不同条件
for mg in [0, 0.02, 0.03, 0.05]:
    ok_days = sum(1 for d in idx_close if d in idx_ma60 and market_ok(d, idx_close, idx_ma60, idx_slope, margin=mg))
    total = sum(1 for d in idx_close if d in idx_ma60)
    print(f"  站上MA60 (margin={mg*100:.0f}%): {ok_days}/{total}天 ({ok_days/total*100:.0f}%)")
slope_days = sum(1 for d in idx_slope if idx_slope[d])
print(f"  MA60斜率向上: {slope_days}天")

# 加载数据
files = sorted([f for f in os.listdir(CACHE_DIR) if f.startswith("stock_") and f.endswith(".pkl") and f != "stock_list.pkl"])
all_data = {}
for fname in files:
    code = fname.replace("stock_", "").replace(".pkl", "")
    try:
        df = pd.read_pickle(os.path.join(CACHE_DIR, fname))
        all_data[code] = df
    except: pass
print(f"加载 {len(all_data)} 只股票")

# ===== 版本一：原版B（基准）=====
t0 = time.time()
res_base = run_backtest(all_data, idx_close, idx_ma60, idx_slope, use_index_filter=False, use_auction_stop=False)
print_result("版本0: 原版B基准", res_base)
print(f"  耗时: {time.time()-t0:.0f}s")

# ===== 版本二：B + 大盘过滤（站上MA60）=====
t0 = time.time()
res_index = run_backtest(all_data, idx_close, idx_ma60, idx_slope, use_index_filter=True, use_auction_stop=False)
print_result("版本1: B + 站上MA60", res_index)
print(f"  耗时: {time.time()-t0:.0f}s")

# ===== 版本三：B + 大盘过滤 + 集合竞价止损 =====
t0 = time.time()
res_full = run_backtest(all_data, idx_close, idx_ma60, idx_slope, use_index_filter=True, use_auction_stop=True)
print_result("版本2: B + 站上MA60 + 竞价止损", res_full)
print(f"  耗时: {time.time()-t0:.0f}s")

# ===== 版本四~八：方案C组合过滤 =====
for mg, sd, lbl in [
    (0.00, 5, "slope5_only"),
    (0.02, 0, "margin2%"),
    (0.03, 0, "margin3%"),
    (0.05, 0, "margin5%"),
    (0.02, 5, "margin2%+slope5"),
    (0.03, 5, "margin3%+slope5"),
]:
    t0 = time.time()
    res = run_backtest(all_data, idx_close, idx_ma60, idx_slope, use_index_filter=True, use_auction_stop=True,
                       margin=mg, slope_days=sd, label=lbl)
    setattr(sys.modules[__name__], f"res_{lbl.replace('%','p').replace('+','_')}", res)
    print_result(f"版本: B + {lbl} + 竞价止损", res)
    print(f"  耗时: {time.time()-t0:.0f}s")

# ===== 对比表 =====
print(f"\n{'='*70}")
print(f"  最终对比")
print(f"{'='*70}")
print(f"  {'版本':<30} {'交易':<6} {'收益%':<10} {'胜率%':<8} {'盈亏比':<8} {'回撤%':<8} {'<-8%':<6}")
print(f"  {'-'*75}")
versions = [
    ("原版B", res_base),
    ("+站上MA60", res_index),
    ("+站上+竞价止损", res_full),
    ("+slope5_only", res_slope5_only),
    ("+margin2%", res_margin2p),
    ("+margin3%", res_margin3p),
    ("+margin5%", res_margin5p),
    ("+margin2%+slope5", res_margin2p_slope5),
    ("+margin3%+slope5", res_margin3p_slope5),
]
for label, r in versions:
    print(f"  {label:<30} {len(r.trades):<6} {r.total_return:<+10.2f} {r.win_rate:<8.1f} {r.profit_loss_ratio:<8.2f} {r.max_drawdown:<8.2f} {r.below_8:<6}")

# 保存
for label, r in [
    ("base", res_base), 
    ("index_filter", res_index), 
    ("full", res_full),
    ("slope5_only", res_slope5_only),
    ("margin2p", res_margin2p),
    ("margin3p", res_margin3p),
    ("margin5p", res_margin5p),
    ("margin2p_slope5", res_margin2p_slope5),
    ("margin3p_slope5", res_margin3p_slope5),
]:
    st = sorted(r.trades, key=lambda t: t.buy_date)
    with open(os.path.join(RESULT_DIR, f"result_B_{label}.json"), "w", encoding="utf-8") as f:
        json.dump({
            "version": label,
            "total_trades": len(r.trades),
            "total_return": r.total_return,
            "annual_return": r.annual_return,
            "max_drawdown": r.max_drawdown,
            "sharpe": r.sharpe,
            "win_rate": r.win_rate,
            "profit_loss_ratio": r.profit_loss_ratio,
            "num_wins": r.num_wins,
            "num_losses": r.num_losses,
            "avg_loss": r.avg_loss,
            "below_8": r.below_8,
            "trades": [t._asdict() for t in st],
        }, f, ensure_ascii=False, indent=2, default=str)
print(f"\n  结果保存至 results/result_B_*.json")