# -*- coding: utf-8 -*-
"""
策略B改进版: 加净利润过滤 + 修复止损
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

START = "2024-01-01"
END = "2026-07-28"
INIT_CAP = 1_000_000
MAX_POS = 5
POS_PCT = 0.20
SLIPPAGE = 0.001
COMM_B = 0.00025
COMM_S = 0.00125

Trade = namedtuple("Trade", [
    "code", "name", "buy_date", "sell_date",
    "buy_price", "sell_price", "pnl_pct", "pnl_amount",
    "hold_days", "exit_reason"
])

# ===== 1. 净利润数据 =====
def load_net_profits():
    """下载所有A股最新净利润数据"""
    cache_f = os.path.join(CACHE_DIR, "net_profit_cache.json")
    if os.path.exists(cache_f):
        with open(cache_f, "r", encoding="utf-8") as f:
            return json.load(f)
    
    print("  下载净利润数据...")
    np_map = {}
    try:
        # 2025年报
        print("    尝试2025年报...")
        df = ak.stock_yjbb_em(date="20251231")
        # 查找净利润列名：不同版本的akshare可能不同
        profit_cols = [c for c in df.columns if "净利润" in str(c)]
        code_col = "股票代码"
        print(f"    净利润列: {profit_cols[:3]}")
        if profit_cols:
            pc = profit_cols[0]
            for _, row in df.iterrows():
                try:
                    code = str(row[code_col]).zfill(6)
                    val = float(row[pc])
                    if not np.isnan(val) and val != 0:
                        np_map[code] = val
                except: pass
        if np_map:
            print(f"    2025年报成功: {len(np_map)}只")
        else:
            # 尝试无分隔符的列名
            for col in df.columns:
                for _, row in df.iterrows():
                    try:
                        code = str(row[code_col]).zfill(6)
                        val = float(row[col])
                        if abs(val) > 10000 and "688" not in code:  # 净利润至少万级
                            np_map[code] = val
                    except: pass
    except Exception as e:
        print(f"  2025年报失败: {e}")
    
    with open(cache_f, "w", encoding="utf-8") as f:
        json.dump(np_map, f, ensure_ascii=False)
    print(f"  净利润数据: {len(np_map)}只股票")
    return np_map

# ===== 2. 改进版策略B信号 =====
def compute_strategyB_improved(df, np_map):
    """策略B + 净利润过滤 + 止损修复"""
    if len(df) < 120:
        return pd.Series(False, index=df.index)
    
    code = str(df["code"].iloc[0]).zfill(6) if "code" in df.columns else ""
    name = str(df["name"].iloc[0]) if "name" in df.columns else ""
    
    # ST过滤
    if "ST" in name or "*ST" in name or "退" in name:
        return pd.Series(False, index=df.index)
    
    # 净利润过滤
    if code and code in np_map and np_map[code] <= 0:
        # 亏损股跳过
        pass  # 后面在信号循环里加
    
    c = df["close"].values; h = df["high"].values; l = df["low"].values
    v = df["volume"].values; o = df["open"].values; cm = df["circ_mv"].values
    n = len(c)
    sig = np.zeros(n, dtype=bool)
    
    # 净利润检查map
    has_profit = not code or code not in np_map or np_map.get(code, 1) > 0
    
    for i in range(60, n):
        pct = c[i]/c[i-1] - 1
        zt20, zt10 = pct > 0.195, pct > 0.095
        if not (zt20 or zt10): continue
        if c[i] < h[i]: continue  # 封板
        
        # 换手率
        os_ = df["outstanding_share"].iloc[i] if "outstanding_share" in df.columns else 0
        sh = (v[i] / os_ * 100) if os_ > 0 else df["turnover"].iloc[i] * 100
        if (zt20 and sh >= 25) or (zt10 and sh >= 20): continue
        
        # 市值
        cmv = cm[i]
        if cmv < 20 or cmv > 500: continue
        
        # MA60方向
        ma60 = np.mean(c[i-59:i+1])
        if ma60 <= np.mean(c[i-69:i-9]): continue  # MA60需向上
        
        # POS: A/B/C
        ma5, ma10 = np.mean(c[i-4:i+1]), np.mean(c[i-9:i+1])
        a_cls = (c[i-1] < ma60) and (c[i] >= ma60)
        b_cls = (abs(c[i]/ma60 - 1) < 0.15) and (ma5 > ma10) and (ma10 > np.mean(c[i-12:i-9]))
        days_abv = sum(1 for j in range(max(0,i-4), i+1) if c[j] > np.mean(c[j-59:j+1]))
        c_cls = (days_abv >= 3 and l[i-1] <= ma60*1.03 and l[i-1] >= ma60*0.97)
        if not (a_cls or b_cls or c_cls): continue
        
        # 量比
        if v[i] < np.mean(v[i-59:i+1]) * 1.5: continue
        
        # 涨幅限制
        if i >= 5 and (c[i]-c[i-5])/c[i-5] >= 0.40: continue
        
        # 净利润过滤
        if not has_profit: continue
        
        sig[i] = True
    return pd.Series(sig, index=df.index)

# ===== 3. 回测引擎（优化版止损）=====
def run_backtest_B_improved(all_data, np_map):
    """改进版回测：止损基于买入价的固定比例"""
    print("  运行改进版策略B回测...")
    
    all_dates = sorted(set(
        d for df in all_data.values()
        for d in df["date"].dt.strftime("%Y-%m-%d")
        if START <= d <= END
    ))
    if len(all_dates) < 10:
        return None
    
    # 计算信号
    stock_signals = {}
    for code, df in all_data.items():
        ss = compute_strategyB_improved(df, np_map)
        ss.index = df["date"].dt.strftime("%Y-%m-%d")
        stock_signals[code] = ss
    
    # 主循环
    cash = INIT_CAP
    positions = {}
    trades = []
    equity_curve = []
    date_set = set(all_dates)
    
    for t_idx in range(len(all_dates) - 1):
        today = all_dates[t_idx]
        tomorrow = all_dates[t_idx + 1]
        
        # --- 卖出（改进止损）---
        to_close = []
        for code, pos in list(positions.items()):
            df = all_data.get(code)
            if df is None: continue
            rows_t = df[df["date"] == today]
            if len(rows_t) == 0: continue
            row = rows_t.iloc[0]
            cp = row["close"]
            lp = row["low"]
            
            # 止损v2: 基于买入价固定比例
            bp = pos["buy_price"]
            max_loss_pct = 0.08  # 8%固定止损
            
            # 条件1: 收盘价跌破止损线
            if cp < bp * (1 - max_loss_pct):
                to_close.append((code, "止损-8%"))
                continue
            
            # 条件2: 盘中最低价跌破-10%（防跳空低开）
            if lp < bp * (1 - 0.10):
                to_close.append((code, "止损-跳空"))
                continue
            
            # 止盈（沿用原版）
            hp = pos.get("highest_pnl", 0)
            pnl = (cp - bp) / bp
            if pnl > hp:
                pos["highest_pnl"] = pnl
            
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
            if len(df_tom) == 0:
                df_t = df[df["date"] == today]
                if len(df_t) == 0: continue
                sp = df_t.iloc[0]["close"] * (1 - SLIPPAGE) * (1 - COMM_S)
            else:
                sp = df_tom.iloc[0]["open"] * (1 - SLIPPAGE) * (1 - COMM_S)
            
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
                hold_days=max(1, t_idx - bi),
                exit_reason=reason,
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
                cands.append((code, df[df["date"] == today].iloc[0]))
            
            cands.sort(key=lambda x: x[1].get("circ_mv", 999))
            for code, row in cands[:MAX_POS - len(positions)]:
                if len(positions) >= MAX_POS: break
                df_tom = all_data[code][all_data[code]["date"] == tomorrow]
                if len(df_tom) == 0: continue
                bp = df_tom.iloc[0]["open"] * (1 + SLIPPAGE) * (1 + COMM_B)
                available = cash * POS_PCT
                shares = int(available / bp / 100) * 100
                if shares <= 0: continue
                cost = shares * bp
                if cost > cash:
                    shares = int(cash / bp / 100) * 100
                    cost = shares * bp
                    if shares <= 0: continue
                cash -= cost
                positions[code] = {
                    "buy_date": tomorrow, "buy_price": bp, "shares": shares,
                    "name": row.get("name", code),
                    "highest_pnl": 0,
                }
        
        # 总资产
        pv = sum(
            pos["shares"] * all_data[code][all_data[code]["date"] == today].iloc[0]["close"]
            for code, pos in positions.items()
            if code in all_data and len(all_data[code][all_data[code]["date"] == today]) > 0
        )
        equity_curve.append(cash + pv)
    
    # 结果
    class Result:
        pass
    res = Result()
    res.trades = trades
    res.equity_curve = equity_curve
    res.dates = all_dates[:len(equity_curve)]
    
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
        res.win_rate = len(wins) / len(trades) * 100
        aw = np.mean([t.pnl_pct for t in wins]) if wins else 0
        ls = [t for t in trades if t.pnl_pct <= 0]
        al = abs(np.mean([t.pnl_pct for t in ls])) if ls else 1
        res.profit_loss_ratio = aw / max(al, 0.01)
    else:
        res.total_return = 0; res.annual_return = 0; res.max_drawdown = 0
        res.sharpe = 0; res.win_rate = 0; res.profit_loss_ratio = 0
    
    return res

# ===== 主程序 =====
print("=" * 80)
print("策略B改进版: +净利润过滤 + 止损修复")
print("=" * 80)

# 下载净利润
np_map = load_net_profits()
print(f"净利润数据: {len(np_map)}只股票, "
      f"其中盈利{sum(1 for v in np_map.values() if v > 0)}只, "
      f"亏损{sum(1 for v in np_map.values() if v <= 0)}只")

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

# 跑回测
t0 = time.time()
result = run_backtest_B_improved(all_data, np_map)
elapsed = time.time() - t0

# 输出
trades = result.trades
st = sorted(trades, key=lambda t: t.buy_date)
wins = [t for t in st if t.pnl_pct > 0]
losses = [t for t in st if t.pnl_pct <= 0]

print(f"\n{'='*60}")
print(f"结果 (耗时{elapsed:.0f}s)")
print(f"{'='*60}")
print(f"{'指标':<25} {'原版策略B':<18} {'改进版':<18}")
print(f"{'-'*60}")
print(f"{'交易次数':<25} {111:<18} {len(trades):<18}")
print(f"{'总收益率%':<25} {-4.75:<18} {result.total_return:<18.2f}")
print(f"{'年化%':<25} {-1.91:<18} {result.annual_return:<18.2f}")
print(f"{'最大回撤%':<25} {26.42:<18} {result.max_drawdown:<18.2f}")
print(f"{'夏普':<25} {-0.072:<18} {result.sharpe:<18.3f}")
print(f"{'胜率%':<25} {33.3:<18} {result.win_rate:<18.1f}")
print(f"{'盈亏比':<25} {2.17:<18} {result.profit_loss_ratio:<18.2f}")
print(f"{'平均盈利%':<25} -         {np.mean([t.pnl_pct for t in wins]):<18.2f}" if wins else "")
print(f"{'平均亏损%':<25} -         {np.mean([t.pnl_pct for t in losses]):<18.2f}" if losses else "")

# 亏损分析
print(f"\n{'='*60}")
print("亏损分析:")
print(f"{'='*60}")
print(f"亏损交易: {len(losses)}笔")
print(f"<-8%的: {sum(1 for t in losses if t.pnl_pct < -8)}笔")
print(f"平均亏损: {np.mean([t.pnl_pct for t in losses]):.2f}%")
print(f"最大亏损: {min(t.pnl_pct for t in losses):.2f}%")

# 前5笔亏损
loss_s = sorted(losses, key=lambda t: t.pnl_pct)
print(f"\n前5大亏损:")
for t in loss_s[:5]:
    print(f"  {t.code} {t.name[:8]:<8} {t.buy_date}->{t.sell_date} {t.pnl_pct:+.2f}% {t.exit_reason}")

# 分年度
print(f"\n{'='*60}")
print("分年度:")
for year in ["2024", "2025", "2026"]:
    yt = [t for t in st if t.buy_date.startswith(year)]
    if not yt: continue
    yw = [t for t in yt if t.pnl_pct > 0]
    ret = sum(t.pnl_pct for t in yt)
    print(f"  {year}: {len(yt)}笔, 胜率{len(yw)/len(yt)*100:.0f}%, 合计{ret:+.1f}%")

# 案例
print(f"\n{'='*60}")
print("案例验证:")
for code, name, dt in [("300679","电连技术","2026-04-08"),("301392","汇成真空","2026-04-01"),
                         ("603083","剑桥科技","2026-04-08"),("002259","升达林业","2026-01-05"),
                         ("002259","升达林业","2026-05-08"),("002238","天威视讯","2026-02-03")]:
    if code not in all_data: continue
    df = all_data[code]
    match = df[df["date"] == dt]
    if len(match) == 0:
        print(f"  {name}({code}) {dt}: 无数据"); continue
    i = match.index[0]
    c_arr = df["close"].values
    pct = (c_arr[i]/c_arr[i-1]-1)*100
    profit_ok = code in np_map and np_map[code] > 0
    print(f"  {name}({code}) {dt}: 涨停{pct:+.1f}% 净利润{'盈利' if profit_ok else '亏损/未获取'}")

# 保存
with open(os.path.join(RESULT_DIR, "result_B_improved.json"), "w", encoding="utf-8") as f:
    json.dump({
        "total_trades": len(trades),
        "total_return": result.total_return,
        "annual_return": result.annual_return,
        "max_drawdown": result.max_drawdown,
        "sharpe": result.sharpe,
        "win_rate": result.win_rate,
        "profit_loss_ratio": result.profit_loss_ratio,
        "num_profitable": len(np_map),
    }, f, ensure_ascii=False, indent=2)
print(f"\n结果保存至: results/result_B_improved.json")