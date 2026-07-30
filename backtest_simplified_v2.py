# -*- coding: utf-8 -*-
"""
简化版回测 v2 — 事件驱动引擎
选股: 站上60日线(CROSS) + 量比≥1.5 + 近20日涨幅≤25% + 市值20~500亿
卖出: 跌破5日线次日开盘
"""
import os, sys, json, time
import numpy as np
import pandas as pd
from collections import namedtuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache_bt3")
RESULT_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULT_DIR, exist_ok=True)

Trade = namedtuple("Trade", ["code", "name", "signal_date", "buy_date", "sell_date",
                              "buy_price", "sell_price", "pnl_pct", "hold_days", "exit_reason"])

# ====== 加载上证指数 ======
def load_sh_index():
    sh_f = os.path.join(CACHE_DIR, "index_000001.pkl")
    if os.path.exists(sh_f):
        return pd.read_pickle(sh_f)
    try:
        import akshare as ak
        sh = ak.stock_zh_index_daily(symbol="sh000001")
        sh["date"] = pd.to_datetime(sh["date"])
        sh.to_pickle(sh_f)
        return sh
    except:
        return None

# ====== 获取股票名称（从文件名解析） ======
def get_stock_name(code):
    """从缓存文件名获取股票名称"""
    fname = f"stock_{code}.pkl"
    fpath = os.path.join(CACHE_DIR, fname)
    if os.path.exists(fpath):
        try:
            df = pd.read_pickle(fpath)
            if "name" in df.columns and len(df) > 0:
                return df["name"].iloc[0]
        except:
            pass
    return code

# ====== 预计算全市场信号日 + 模拟交易 ======
def run_backtest(initial_capital=1000000, max_positions=5, position_pct=0.20):
    sh_data = load_sh_index()
    
    # 预计算上证MA60
    sh_ma60 = {}
    if sh_data is not None:
        sc = sh_data["close"].values
        sd = sh_data["date"].values
        for i in range(59, len(sc)):
            d = pd.Timestamp(sd[i]).strftime("%Y-%m-%d")
            sh_ma60[d] = np.mean(sc[i-59:i+1])

    # 扫描所有股票，收集信号
    files = sorted([f for f in os.listdir(CACHE_DIR) if f.startswith("stock_") and f.endswith(".pkl") and f != "stock_list.pkl"])
    
    all_signals = []  # [(date, code, name, buy_open, ...)]
    signal_count = 0
    
    for idx, fname in enumerate(files):
        code = fname.replace("stock_", "").replace(".pkl", "")
        fpath = os.path.join(CACHE_DIR, fname)
        
        try:
            df = pd.read_pickle(fpath)
        except:
            continue
        
        if len(df) < 80:
            continue
        
        name = df["name"].iloc[0] if "name" in df.columns else code
        
        c_arr = df["close"].values.astype(float)
        o_arr = df["open"].values.astype(float) if "open" in df.columns else c_arr
        v_arr = df["volume"].values.astype(float)
        cm_arr = df["circ_mv"].values.astype(float) if "circ_mv" in df.columns else np.zeros(len(df))
        dates = df["date"].values
        n = len(dates)
        
        for i in range(70, n):
            ma60 = np.mean(c_arr[i-59:i+1])
            ma60_prev = np.mean(c_arr[i-60:i])
            cp = c_arr[i]
            
            # 站上60日线 (CROSS): 前日<MA60 且 今日>=MA60
            if not (c_arr[i-1] < ma60_prev and cp >= ma60):
                continue
            
            # 量比>=1.5
            vol_ma60 = np.mean(v_arr[i-59:i+1])
            if vol_ma60 <= 0 or v_arr[i] / vol_ma60 < 1.5:
                continue
            
            # 近20日涨幅<=25%
            if i >= 20:
                chg20 = (cp / c_arr[i-20] - 1) * 100
                if chg20 > 25:
                    continue
            
            # 市值20~500亿
            cm = cm_arr[i]
            if cm < 20 or cm > 500:
                continue
            
            # 大盘过滤: 上证站上MA60
            d = pd.Timestamp(dates[i]).strftime("%Y-%m-%d")
            if d in sh_ma60:
                sh_idx = np.where(sh_data["date"].values == dates[i])[0]
                if len(sh_idx) > 0:
                    sh_c = sh_data["close"].values[sh_idx[0]]
                    sh_m60 = sh_ma60[d]
                    if sh_c < sh_m60:
                        continue
            
            # 次日开盘买入价
            if i + 1 >= n:
                continue
            buy_open = o_arr[i+1]
            buy_price = buy_open * 1.001 * 1.00025  # +滑点 +佣金
            buy_date = pd.Timestamp(dates[i+1]).strftime("%Y-%m-%d")
            
            # 查找卖出日：收盘跌破5日线 → 次日开盘卖出
            sell_price = None
            sell_date = None
            exit_reason = "end"
            
            for j in range(i+2, n):
                if j >= 4:
                    ma5 = np.mean(c_arr[j-4:j+1])
                    if c_arr[j] < ma5:
                        if j + 1 < n:
                            sell_open = o_arr[j+1]
                            sell_price = sell_open * 0.999 * (1 - 0.001 - 0.0005)
                            sell_date = pd.Timestamp(dates[j+1]).strftime("%Y-%m-%d")
                            exit_reason = "break_ma5"
                        else:
                            sell_price = c_arr[j] * 0.999 * (1 - 0.001 - 0.0005)
                            sell_date = pd.Timestamp(dates[j]).strftime("%Y-%m-%d")
                            exit_reason = "end"
                        break
            
            if sell_price is None:
                sell_price = c_arr[-1] * 0.999 * (1 - 0.001 - 0.0005)
                sell_date = pd.Timestamp(dates[-1]).strftime("%Y-%m-%d")
                exit_reason = "end"
            
            all_signals.append({
                "code": code, "name": name,
                "signal_date": d, "buy_date": buy_date,
                "buy_open": float(buy_open), "buy_price": float(buy_price),
                "sell_date": sell_date, "sell_price": float(sell_price),
                "exit_reason": exit_reason,
            })
            signal_count += 1
        
        if (idx + 1) % 200 == 0:
            print(f"  scan {idx+1}/{len(files)}, signals={signal_count}")
    
    print(f"  扫描完成: {signal_count}个信号")
    
    # ====== 事件驱动模拟交易 ======
    signals_sorted = sorted(all_signals, key=lambda s: s["buy_date"])
    
    cash = float(initial_capital)
    positions = {}  # code -> {shares, buy_price, buy_date, name}
    trades = []
    equity_curve = [initial_capital]
    curve_dates = ["2024-01-02"]
    position_value_per = initial_capital * position_pct
    
    for sig in signals_sorted:
        buy_dt = sig["buy_date"]
        code = sig["code"]
        
        # 更新净值（用之前的持仓到当前日期的市值变化，简化处理）
        
        # 如果已有持仓，跳过
        if code in positions:
            continue
        
        # 计算可买股数
        max_cost = min(position_value_per, cash)
        shares = int(max_cost / sig["buy_price"])
        cost = shares * sig["buy_price"]
        if shares <= 0 or cost <= 0 or len(positions) >= max_positions:
            continue
        
        # 买入
        cash -= cost
        positions[code] = {
            "shares": shares, "buy_cost": sig["buy_price"],
            "buy_date": buy_dt, "name": sig["name"],
            "signal_date": sig["signal_date"],
        }
    
    # 按卖出日期处理平仓
    sell_events = sorted(all_signals, key=lambda s: s["sell_date"])
    for sig in sell_events:
        code = sig["code"]
        if code not in positions:
            continue
        pos = positions.pop(code)
        proceeds = pos["shares"] * sig["sell_price"]
        pnl = (sig["sell_price"] - pos["buy_cost"]) / pos["buy_cost"] * 100
        hold = (pd.Timestamp(sig["sell_date"]) - pd.Timestamp(pos["buy_date"])).days
        
        trades.append(Trade(
            code, pos["name"], pos["signal_date"],
            pos["buy_date"], sig["sell_date"],
            round(pos["buy_cost"], 4), round(sig["sell_price"], 4),
            round(pnl, 2), hold, sig["exit_reason"]
        ))
        cash += proceeds
        
        # 记录净值
        total = cash + sum(p["shares"] * sig["sell_price"] for _, p in positions.items()
                          if p["buy_date"] <= sig["sell_date"])
        equity_curve.append(total)
        curve_dates.append(sig["sell_date"])
    
    # 最终平仓（到数据结束） — 实际上已经被上面处理完了
    
    return trades, equity_curve, curve_dates, signal_count

# ====== 计算指标 ======
def compute_metrics(trades, equity_curve, initial_capital=1000000):
    if not trades:
        return {}
    
    total_ret = (equity_curve[-1] / initial_capital - 1) * 100
    years = 2.5
    annual_ret = ((1 + total_ret/100) ** (1/years) - 1) * 100
    
    # 最大回撤
    max_dd = 0
    peak = equity_curve[0]
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd
    
    # 夏普
    daily_rets = []
    for k in range(1, len(equity_curve)):
        r = (equity_curve[k] - equity_curve[k-1]) / equity_curve[k-1] if equity_curve[k-1] > 0 else 0
        daily_rets.append(r)
    sharpe = np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252) if np.std(daily_rets) > 0 else 0
    
    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    wr = len(wins) / len(trades) * 100
    avg_w = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_l = np.mean([t.pnl_pct for t in losses]) if losses else 0
    
    total_w = sum(t.pnl_pct for t in wins) if wins else 1
    total_l = sum(t.pnl_pct for t in losses) if losses else 1
    pf = abs(total_w / total_l) if total_l != 0 else float('inf')
    
    wh = np.mean([t.hold_days for t in wins]) if wins else 0
    lh = np.mean([t.hold_days for t in losses]) if losses else 0
    
    return {
        "total_trades": len(trades),
        "total_return_pct": round(total_ret, 2),
        "annual_return_pct": round(annual_ret, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 3),
        "win_rate_pct": round(wr, 1),
        "profit_factor": round(pf, 2),
        "avg_win_pct": round(avg_w, 2),
        "avg_loss_pct": round(avg_l, 2),
        "avg_hold_days": round(np.mean([t.hold_days for t in trades]), 1),
        "avg_hold_win_days": round(wh, 1),
        "avg_hold_loss_days": round(lh, 1),
    }

# ====== 验证案例 ======
def check_case(code, date_str):
    fpath = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
    if not os.path.exists(fpath):
        return None
    df = pd.read_pickle(fpath)
    c_arr = df["close"].values.astype(float)
    v_arr = df["volume"].values.astype(float)
    cm_arr = df["circ_mv"].values.astype(float)
    name = df["name"].iloc[0] if "name" in df.columns else code
    
    mask = df["date"] == date_str
    if not mask.any():
        return None
    i = mask.idxmax()
    
    cp = c_arr[i]; ma60 = np.mean(c_arr[i-59:i+1]); ma60_prev = np.mean(c_arr[i-60:i])
    cross = bool(c_arr[i-1] < ma60_prev and cp >= ma60)
    vol_ma60 = np.mean(v_arr[i-59:i+1]); vr = float(v_arr[i]/vol_ma60) if vol_ma60 > 0 else 0
    chg20 = float((cp/c_arr[i-20]-1)*100) if i >= 20 else 0
    cm = float(cm_arr[i])
    
    return {
        "name": name, "code": code, "date": str(date_str)[:10],
        "close": round(float(cp), 2), "ma60": round(float(ma60), 2),
        "cross_ma60": cross, "vol_ratio": round(vr, 1),
        "chg20_pct": round(chg20, 1), "circ_mv": round(cm, 1),
        "selected": bool(cross and vr >= 1.5 and chg20 <= 25 and 20 <= cm <= 500)
    }

# ====== 主程序 ======
print("=" * 80)
print("简化版回测 v2 — 事件驱动")
print("选股: CROSS(MA60) + 量比>=1.5 + 20日涨<=25% + 市值20~500亿")
print("卖出: 跌破MA5次日开盘")
print("=" * 80)

t0 = time.time()
trades, equity, dates, sig_count = run_backtest()
metrics = compute_metrics(trades, equity, 1000000)
elapsed = time.time() - t0

print(f"\n回测完成: {elapsed:.0f}s, 信号数: {sig_count}, 实际交易: {metrics['total_trades']}")

print("\n" + "=" * 80)
print("绩效指标")
print("=" * 80)
for k, v in metrics.items():
    print(f"  {k:<25} {v:>15}")

# 前20笔
print("\n" + "=" * 80)
print("前20笔交易")
print("=" * 80)
st = sorted(trades, key=lambda t: t.buy_date)
print(f"{'代码':<8} {'名称':<10} {'买入':<12} {'卖出':<12} {'收益%':<8} {'持有':<5} {'退出原因':<15}")
print("-" * 70)
for t in st[:20]:
    print(f"{t.code:<8} {t.name[:8]:<10} {t.buy_date:<12} {t.sell_date:<12} {t.pnl_pct:<+8.2f} {t.hold_days:<5} {t.exit_reason:<15}")

# 分年度
print("\n" + "=" * 80)
print("分年度表现")
print("=" * 80)
yearly = {}
for t in st:
    y = t.buy_date[:4]
    yearly.setdefault(y, []).append(t)
for y in sorted(yearly):
    ts = yearly[y]
    w = [t for t in ts if t.pnl_pct > 0]
    ret = sum(t.pnl_pct for t in ts)
    print(f"  {y}: {len(ts)}笔, 胜率{len(w)/len(ts)*100:.0f}%, 合计{ret:+.1f}%")

# 案例验证
print("\n" + "=" * 80)
print("案例股票验证")
print("=" * 80)
cases = [("300679","2026-04-08"), ("301392","2026-04-01"), ("603083","2026-04-08"),
         ("002259","2026-01-05"), ("002238","2026-02-03")]
for code, dt in cases:
    r = check_case(code, dt)
    if r:
        s = "入选" if r["selected"] else "过滤"
        print(f"  {r['name']}({code}) @ {dt}: {s}  收盘{r['close']:.2f} MA60:{r['ma60']:.2f}  "
              f"交叉{r['cross_ma60']} 量比{r['vol_ratio']:.1f}x 20日涨{r['chg20_pct']:.1f}%")

# 保存
result = {
    "version": "simplified_v2",
    "metrics": metrics,
    "trades": [t._asdict() for t in st],
    "equity": [float(v) for v in equity],
    "dates": dates,
}
with open(os.path.join(RESULT_DIR, "result_simplified.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print(f"\n结果保存至: {os.path.join(RESULT_DIR, 'result_simplified.json')}")
print("DONE")