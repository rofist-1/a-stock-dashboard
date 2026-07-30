# -*- coding: utf-8 -*-
"""
简化版回测：仅 站上60日线 + 量比≥1.5 + 近20日涨幅≤25% + 流通市值20~500亿
（无百日新高、无POS分类、无MA60方向要求）
卖出：跌破5日线次日开盘
"""
import os, sys, pickle, json, time
import numpy as np
import pandas as pd
from collections import namedtuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache_bt3")
RESULT_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULT_DIR, exist_ok=True)

# ---------- 交易记录 ----------
Trade = namedtuple("Trade", ["code", "name", "signal_date", "buy_date", "sell_date",
                              "buy_price", "sell_price", "pnl_pct", "hold_days", "exit_reason"])

def load_stocks():
    files = sorted([f for f in os.listdir(CACHE_DIR) if f.startswith("stock_") and f.endswith(".pkl") and f != "stock_list.pkl"])
    stocks = []
    for f in files:
        code = f.replace("stock_", "").replace(".pkl", "")
        name = f.split("_", 1)[1].replace(".pkl", "") if "_" in f else code
        stocks.append((code, name, os.path.join(CACHE_DIR, f)))
    return stocks

def run_simple_backtest(stock_list, initial_capital=1000000, max_positions=5):
    """简化版回测：站上60日线 + 量比 + 涨幅 + 市值"""
    
    # 加载上证指数
    sh_code = "000001"
    sh_f = os.path.join(CACHE_DIR, f"index_{sh_code}.pkl")
    sh_data = None
    if os.path.exists(sh_f):
        sh_data = pd.read_pickle(sh_f)
    # 如果没有缓存上证指数，尝试从akshare获取
    if sh_data is None:
        try:
            import akshare as ak
            sh = ak.stock_zh_index_daily(symbol="sh000001")
            sh["date"] = pd.to_datetime(sh["date"])
            sh_data = sh
            os.makedirs(CACHE_DIR, exist_ok=True)
            sh.to_pickle(sh_f)
        except:
            pass
    
    # 为上证指数计算MA60
    sh_ma60_map = {}
    if sh_data is not None:
        sh_c = sh_data["close"].values
        sh_dates = sh_data["date"].values
        for idx in range(59, len(sh_c)):
            d = pd.Timestamp(sh_dates[idx]).strftime("%Y-%m-%d")
            sh_ma60_map[d] = np.mean(sh_c[idx-59:idx+1])
    
    total = len(stock_list)
    trades = []
    signals_found = 0
    
    for idx, (code, name, fpath) in enumerate(stock_list):
        if (idx+1) % 200 == 0:
            print(f"    [{idx+1}/{total}] signals so far: {signals_found}")
        try:
            df = pd.read_pickle(fpath)
        except:
            continue
        if len(df) < 80:
            continue
        
        c_arr = df["close"].values
        v_arr = df["volume"].values
        cm_arr = df["circ_mv"].values
        dates = df["date"].values
        
        n = len(c_arr)
        for i in range(70, n):
            ma60 = np.mean(c_arr[i-59:i+1])
            cp = c_arr[i]
            
            # 条件1: 站上60日线 (CROSS)
            if not (c_arr[i-1] < np.mean(c_arr[i-60:i]) and cp >= ma60):
                continue
            
            # 条件2: 量比≥1.5
            vol_ma60 = np.mean(v_arr[i-59:i+1])
            if vol_ma60 <= 0 or v_arr[i] / vol_ma60 < 1.5:
                continue
            
            # 条件3: 近20日涨幅≤25%
            if i >= 20:
                chg20 = (cp / c_arr[i-20] - 1) * 100
                if chg20 > 25:
                    continue
            
            # 条件4: 流通市值20~500亿
            cm = cm_arr[i]
            if cm < 20 or cm > 500:
                continue
            
            # 大盘过滤：上证指数站上MA60
            d = pd.Timestamp(dates[i]).strftime("%Y-%m-%d")
            if d in sh_ma60_map and sh_ma60_map[d] is not None:
                sh_close = None
                if sh_data is not None:
                    sh_mask = sh_data["date"] == dates[i]
                    if sh_mask.any():
                        sh_close = sh_data.loc[sh_mask, "close"].values[0]
                if sh_close is not None:
                    sh_ma60_val = sh_ma60_map[d]
                    if sh_close < sh_ma60_val:
                        continue
            
            signals_found += 1
            signal_date = d
            
            # 买入：次日开盘
            if i + 1 >= n:
                continue
            buy_price = c_arr[i+1]  # 次日开盘（这里简化，实际应取open）
            # 更精确的：取次日开盘价
            buy_price = df["open"].iloc[i+1]
            buy_cost = buy_price * 1.001 * 1.00025  # 滑点0.1% + 佣金0.025%
            buy_date = pd.Timestamp(dates[i+1]).strftime("%Y-%m-%d")
            
            # 卖出：跌破5日线次日开盘
            sell_price = None
            sell_date = None
            exit_reason = "unknown"
            
            for j in range(i+2, n):
                ma5 = np.mean(c_arr[j-4:j+1])
                if c_arr[j] < ma5:
                    # 跌破5日线，次日开盘卖出
                    if j + 1 < n:
                        sell_price = df["open"].iloc[j+1]
                        sell_cost = sell_price * 0.999 * 0.99875  # 滑点0.1% + 佣金+印花税0.125%
                        sell_date = pd.Timestamp(dates[j+1]).strftime("%Y-%m-%d")
                        exit_reason = "break_ma5"
                    else:
                        sell_price = c_arr[j]
                        sell_cost = sell_price * 0.999 * 0.99875
                        sell_date = pd.Timestamp(dates[j]).strftime("%Y-%m-%d")
                        exit_reason = "break_ma5_end"
                    break
            
            if sell_price is None:
                # 持有到结束，按最后一天收盘卖
                sell_price = c_arr[-1]
                sell_cost = sell_price * 0.999 * 0.99875
                sell_date = pd.Timestamp(dates[-1]).strftime("%Y-%m-%d")
                exit_reason = "end_of_data"
            
            pnl = (sell_cost - buy_cost) / buy_cost * 100
            hold_days = (pd.Timestamp(sell_date) - pd.Timestamp(buy_date)).days
            
            trades.append(Trade(code, name, signal_date, buy_date, sell_date,
                               buy_cost, sell_cost, pnl, hold_days, exit_reason))
    
    return trades, signals_found

def compute_metrics(trades, initial_capital=1000000):
    if not trades:
        return {"total_return": 0, "trades": 0}
    
    # 按时间排序
    sorted_trades = sorted(trades, key=lambda t: t.buy_date)
    
    # 模拟资金曲线
    equity = [initial_capital]
    dates_curve = ["2024-01-02"]
    capital = initial_capital
    position_value = 0
    active = []  # 当前持仓
    
    all_dates = sorted(set(t.buy_date for t in sorted_trades) | set(t.sell_date for t in sorted_trades))
    
    trade_idx = 0
    sell_idx = 0
    sorted_sells = sorted(trades, key=lambda t: t.sell_date)
    
    for d in sorted_dates(all_dates, initial_capital, sorted_trades):
        pass
    
    # 简化计算：直接累加交易收益
    total_pnl = sum(t.pnl_pct for t in sorted_trades)
    wins = [t for t in sorted_trades if t.pnl_pct > 0]
    losses = [t for t in sorted_trades if t.pnl_pct <= 0]
    win_rate = len(wins) / len(sorted_trades) * 100 if sorted_trades else 0
    avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0
    profit_factor = abs(sum(t.pnl_pct for t in wins) / sum(t.pnl_pct for t in losses)) if losses and sum(t.pnl_pct for t in losses) != 0 else float('inf')
    
    # 净值曲线（更精确）
    equity_curve = [initial_capital]
    curve_dates = ["2024-01-02"]
    cash = initial_capital
    positions = {}
    
    # 按日期排序所有事件
    events = []
    for t in sorted_trades:
        events.append((t.buy_date, "buy", t))
        events.append((t.sell_date, "sell", t))
    events.sort(key=lambda x: x[0])
    
    for dt, etype, t in events:
        if etype == "buy":
            if cash >= t.buy_price * (initial_capital * 0.2 / t.buy_price):
                shares = int((initial_capital * 0.2) / t.buy_price)
                cost = shares * t.buy_price
                if cost <= cash:
                    cash -= cost
                    positions[t.code] = {"shares": shares, "buy_cost": t.buy_price}
        elif etype == "sell":
            if t.code in positions:
                pos = positions.pop(t.code)
                proceeds = pos["shares"] * t.sell_price
                cash += proceeds
        
        total_value = cash + sum(p["shares"] * t.sell_price for p_code, p in positions.items())
        equity_curve.append(total_value)
        curve_dates.append(dt)
    
    total_ret = (equity_curve[-1] / initial_capital - 1) * 100
    max_dd = 0
    peak = equity_curve[0]
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    # 年化
    years = 2.5
    annual_ret = ((1 + total_ret/100) ** (1/years) - 1) * 100
    
    # 夏普
    daily_rets = []
    for k in range(1, len(equity_curve)):
        r = (equity_curve[k] - equity_curve[k-1]) / equity_curve[k-1]
        daily_rets.append(r)
    sharpe = np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252) if np.std(daily_rets) > 0 else 0
    
    win_hold = np.mean([t.hold_days for t in wins]) if wins else 0
    loss_hold = np.mean([t.hold_days for t in losses]) if losses else 0
    
    return {
        "total_trades": len(sorted_trades),
        "total_return_pct": round(total_ret, 2),
        "annual_return_pct": round(annual_ret, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 3),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "avg_hold_days": round(np.mean([t.hold_days for t in sorted_trades]), 1),
        "avg_hold_days_win": round(win_hold, 1),
        "avg_hold_days_loss": round(loss_hold, 1),
        "equity_curve": equity_curve,
        "curve_dates": curve_dates,
    }

def sorted_dates(dates, initial_cap, trades):
    return sorted(set(dates))

# ==========================================
# 验证案例股票
# ==========================================
def check_case(code, name, date_str):
    fpath = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
    if not os.path.exists(fpath):
        return "NO_DATA"
    df = pd.read_pickle(fpath)
    c_arr = df["close"].values; v_arr = df["volume"].values; cm_arr = df["circ_mv"].values
    dates_str = [str(d)[:10] for d in df["date"].values]
    
    try:
        i = dates_str.index(date_str)
    except ValueError:
        return "DATE_NOT_FOUND"
    
    cp = c_arr[i]
    ma60 = np.mean(c_arr[i-59:i+1]) if i >= 60 else 0
    cross = (c_arr[i-1] < np.mean(c_arr[i-60:i]) and cp >= ma60) if i >= 60 else False
    vol_ma60 = np.mean(v_arr[i-59:i+1]); vr = v_arr[i]/vol_ma60 if vol_ma60 > 0 else 0
    chg20 = (cp/c_arr[i-20]-1)*100 if i >= 20 else 0
    cm = cm_arr[i]
    
    passed = cross and vr >= 1.5 and chg20 <= 25 and 20 <= cm <= 500
    return {
        "code": code, "name": name, "date": date_str,
        "close": round(cp, 2), "ma60": round(ma60, 2),
        "cross_ma60": cross, "vol_ratio": round(vr, 1),
        "chg20_pct": round(chg20, 1), "circ_mv": round(cm, 0),
        "selected": passed
    }

# ==========================================
# 主程序
# ==========================================
print("=" * 80)
print("简化版回测：站上60日线 + 量比≥1.5 + 20日涨≤25% + 市值20~500亿")
print("=" * 80)

stocks = load_stocks()
print(f"加载 {len(stocks)} 只股票")

t0 = time.time()
trades, signal_count = run_simple_backtest(stocks)
elapsed = time.time() - t0
print(f"回测完成: {elapsed:.0f}s, 信号数: {signal_count}, 交易数: {len(trades)}")

metrics = compute_metrics(trades)

# ==========================================
# 打印结果
# ==========================================
print("\n" + "=" * 80)
print("绩效指标")
print("=" * 80)
print(f"{'指标':<25} {'值':>15}")
print("-" * 42)
print(f"{'总交易次数':<25} {metrics['total_trades']:>15}")
print(f"{'总收益率%':<25} {metrics['total_return_pct']:>15.2f}")
print(f"{'年化收益率%':<25} {metrics['annual_return_pct']:>15.2f}")
print(f"{'最大回撤%':<25} {metrics['max_drawdown_pct']:>15.2f}")
print(f"{'夏普比率':<25} {metrics['sharpe']:>15.3f}")
print(f"{'胜率%':<25} {metrics['win_rate_pct']:>15.1f}")
print(f"{'盈亏比':<25} {metrics['profit_factor']:>15.2f}")
print(f"{'平均盈利%':<25} {metrics['avg_win_pct']:>15.2f}")
print(f"{'平均亏损%':<25} {metrics['avg_loss_pct']:>15.2f}")
print(f"{'平均持仓(天)':<25} {metrics['avg_hold_days']:>15.1f}")
print(f"{'盈利交易均持仓':<25} {metrics['avg_hold_days_win']:>15.1f}")
print(f"{'亏损交易均持仓':<25} {metrics['avg_hold_days_loss']:>15.1f}")

print("\n" + "=" * 80)
print("前20笔交易记录")
print("=" * 80)
sorted_trades = sorted(trades, key=lambda t: t.buy_date)
print(f"{'代码':<8} {'名称':<10} {'买入日':<12} {'卖出日':<12} {'买价':<8} {'卖价':<8} {'收益%':<8} {'持有':<5} {'退出原因':<12}")
print("-" * 85)
for t in sorted_trades[:20]:
    name_short = t.name[:8] if len(t.name) > 8 else t.name
    print(f"{t.code:<8} {name_short:<10} {t.buy_date:<12} {t.sell_date:<12} {t.buy_price:<8.2f} {t.sell_price:<8.2f} {t.pnl_pct:<+8.2f} {t.hold_days:<5} {t.exit_reason:<12}")

# ==========================================
# 胜率分布
# ==========================================
print("\n" + "=" * 80)
print("胜率分布分析")
print("=" * 80)
wins = [t for t in sorted_trades if t.pnl_pct > 0]
losses = [t for t in sorted_trades if t.pnl_pct <= 0]
print(f"  盈利交易: {len(wins)}笔, 均持有 {metrics['avg_hold_days_win']:.1f}天")
print(f"  亏损交易: {len(losses)}笔, 均持有 {metrics['avg_hold_days_loss']:.1f}天")
print(f"  → {'亏损持有更久' if metrics['avg_hold_days_loss'] > metrics['avg_hold_days_win'] else '盈利持有更久'}")

# 分年份统计
yearly = {}
for t in sorted_trades:
    y = t.buy_date[:4]
    if y not in yearly:
        yearly[y] = []
    yearly[y].append(t)
print(f"\n  分年度:")
for y in sorted(yearly.keys()):
    ts = yearly[y]
    w = [t for t in ts if t.pnl_pct > 0]
    l = [t for t in ts if t.pnl_pct <= 0]
    ret = sum(t.pnl_pct for t in ts)
    print(f"  {y}: {len(ts)}笔, 胜率{len(w)/len(ts)*100:.0f}%, 合计{ret:+.1f}%")

# ==========================================
# 案例股票验证
# ==========================================
print("\n" + "=" * 80)
print("5只案例股票验证")
print("=" * 80)
cases = [
    ("300679", "电连技术", "2026-04-08"),
    ("301392", "汇成真空", "2026-04-01"),
    ("603083", "剑桥科技", "2026-04-08"),
    ("002259", "升达林业", "2026-01-05"),
    ("002238", "天威视讯", "2026-02-03"),
]
for code, name, dt in cases:
    r = check_case(code, name, dt)
    if isinstance(r, dict):
        sel = "入选" if r["selected"] else "过滤"
        print(f"  {name}({code}) @ {dt}: {sel}  收盘{r['close']:.2f} MA60:{r['ma60']:.2f}  "
              f"交叉{r['cross_ma60']} 量比{r['vol_ratio']:.1f}x 涨20日{r['chg20_pct']:.1f}% 市值{r['circ_mv']:.0f}亿")

# ==========================================
# 保存结果
# ==========================================
result = {
    "version": "simplified",
    "signal_count": signal_count,
    "trade_count": len(trades),
    "metrics": metrics,
    "trades": [t._asdict() for t in sorted_trades],
}
with open(os.path.join(RESULT_DIR, "result_simplified.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print(f"\n结果已保存到 {os.path.join(RESULT_DIR, 'result_simplified.json')}")
print("=" * 80)
print("DONE")