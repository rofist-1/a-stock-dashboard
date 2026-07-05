# -*- coding: utf-8 -*-
"""
波段交易模型 - 参数优化 + 场景分析
===================================
1. 止损参数: 固定5%/8%/10%, ATR动态(2倍)
2. 仓位管理: 持股上限3/5, 单日买入上限0/2
3. 周期敏感性: 上涨/震荡/下跌市分别分析
"""

import akshare as ak
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os, warnings, sys, time, itertools
warnings.filterwarnings("ignore")

START = "2024-06-01"; END = "2026-06-26"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_bt")
os.makedirs(CACHE, exist_ok=True)

SECTORS = {
    "芯片概念": ["002371","688012","688072","688981","603501",
                 "300782","603986","600584","002156","603019"],
    "专精特新": ["300124","300450","688017","002709"],
    "商业航天": ["600118","601698","600879"],
    "光伏概念": ["002129","600438","601012"],
    "新能源汽车": ["300750","002594"],
}
ALL_CODES = sorted(set(c for lst in SECTORS.values() for c in lst))
PREFIX = {c: "sz"+c if c.startswith(("0","3")) else "sh"+c for c in ALL_CODES}
VOL_SHRINK = 0.8; NEAR_MA = 0.03; RPS_PCTILE = 0.40; RPS_WINS = [10, 20, 60]

def _p(name): return os.path.join(CACHE, f"{name}.pkl")

def fetch_index():
    p = _p("idx"); t0 = time.time()
    if os.path.exists(p):
        df = pd.read_pickle(p)
        print(f"    缓存 idx ({len(df)} 行) {time.time()-t0:.0f}s"); return df
    df = ak.stock_zh_index_daily(symbol="sh000001")
    df["date"] = pd.to_datetime(df["date"]); df = df.set_index("date").sort_index()
    df.to_pickle(p); return df

def fetch_stocks():
    p = _p("stk_opt"); t0 = time.time()
    if os.path.exists(p):
        df = pd.read_pickle(p)
        print(f"    缓存 stk ({df.index.get_level_values('code').nunique()} 只) {time.time()-t0:.0f}s"); return df
    all_dfs = []
    for i, code in enumerate(ALL_CODES):
        try:
            df = ak.stock_zh_a_daily(symbol=PREFIX[code],
                start_date=START.replace("-",""), end_date=END.replace("-",""), adjust="qfq")
            if df is None or df.empty: continue
            df["date"] = pd.to_datetime(df["date"]); df["code"] = code
            df = df.set_index("date")
            df["amount"] = df["volume"] * (df["close"] + df["open"]) / 2
            all_dfs.append(df[["code","open","close","high","low","volume","amount"]])
            time.sleep(0.3)
        except Exception as e:
            print(f"    [{i+1}/{len(ALL_CODES)}] {code} FAIL {e}", flush=True); time.sleep(2)
        if (i+1) % 5 == 0: print(f"    [{i+1}/{len(ALL_CODES)}]...", flush=True)
    result = pd.concat(all_dfs).reset_index().set_index(["date","code"]).sort_index()
    result.to_pickle(p); return result

def compute_signals(idx_raw, stock_raw):
    idx = idx_raw.copy()
    idx["ma20"] = idx["close"].rolling(20).mean()
    idx["ma20_slope"] = idx["ma20"].pct_change(5)
    above = idx["close"] > idx["ma20"]; up = idx["ma20_slope"] > 0.005; down = idx["ma20_slope"] < -0.005
    idx["regime"] = "震荡"
    idx.loc[above & up, "regime"] = "上涨"; idx.loc[~above & down, "regime"] = "下跌"
    idx["regime"] = idx["regime"].fillna("震荡")
    idx["market_ok"] = (above & (idx["ma20_slope"] > 0)).astype(int)

    # 板块RPS三线共振
    ret_data = {}
    for sector, codes in SECTORS.items():
        valid = [c for c in codes if c in stock_raw.index.get_level_values("code").unique()]
        pieces = [stock_raw.xs(c, level="code")["close"].pct_change().rename(c) for c in valid if len(stock_raw.xs(c, level="code")) >= 20]
        if pieces: ret_data[sector] = pd.concat(pieces, axis=1).mean(axis=1)
    sector_rets = pd.DataFrame(ret_data).dropna()
    resonance = pd.DataFrame(0, index=sector_rets.index, columns=sector_rets.columns)
    for sector in sector_rets.columns:
        ok = pd.Series(True, index=sector_rets.index)
        for N in RPS_WINS:
            rank = sector_rets.rolling(N).sum().rank(axis=1, pct=True)
            ok = ok & (rank[sector] > RPS_PCTILE)
        resonance[sector] = ok.astype(int)

    # 个股信号
    sig = stock_raw.copy()
    sig = sig.join(idx[["market_ok","regime"]], how="left")
    sig[["market_ok","regime"]] = sig[["market_ok","regime"]].fillna(method="ffill").fillna(0)
    sig["ma10"] = sig.groupby(level="code")["close"].transform(lambda x: x.rolling(10, min_periods=5).mean())
    sig["ma20"] = sig.groupby(level="code")["close"].transform(lambda x: x.rolling(20, min_periods=10).mean())
    sig["ma20_slope"] = sig.groupby(level="code")["ma20"].transform(lambda x: x.pct_change(5))
    sig["ma20_ok"] = ((sig["close"] > sig["ma20"]) & (sig["ma20_slope"] > 0)).astype(int)
    vol5d = sig.groupby(level="code")["volume"].transform(lambda x: x.rolling(5, min_periods=3).mean())
    sig["vol_shrink"] = (sig["volume"] < vol5d * VOL_SHRINK).astype(int)
    sig["pullback"] = ((sig["vol_shrink"]) & (
        (sig["close"]/sig["ma10"]-1).abs() < NEAR_MA) | ((sig["close"]/sig["ma20"]-1).abs() < NEAR_MA)).astype(int)
    amt5d = sig.groupby(level="code")["amount"].transform(lambda x: x.rolling(5, min_periods=3).mean()) / 1e8
    sig["amount_ok"] = (amt5d > 5).astype(int)
    # ATR
    def _tr(g):
        hml = (g["high"]-g["low"]).abs(); hmc = (g["high"]-g["close"].shift(1)).abs(); lmc = (g["low"]-g["close"].shift(1)).abs()
        return pd.concat([hml, hmc, lmc], axis=1).max(axis=1)
    sig["tr"] = sig.groupby(level="code", group_keys=False).apply(_tr)
    sig["atr14"] = sig.groupby(level="code")["tr"].transform(lambda x: x.rolling(14, min_periods=7).mean())
    sig["resonance"] = 0
    for sector in resonance.columns:
        for c in SECTORS.get(sector, []):
            mask = sig.index.get_level_values("code") == c
            sig.loc[mask, "resonance"] = sig.loc[mask].index.get_level_values("date").map(resonance[sector]).fillna(0).astype(int)
    return sig, idx[["regime"]]

# ======================== BACKTRADER ========================
class SigData(bt.feeds.PandasData):
    lines = ("market_ok","resonance","ma20_ok","pullback","amount_ok","ma20","atr14")
    params = (("market_ok","market_ok"),("resonance","resonance"),("ma20_ok","ma20_ok"),
              ("pullback","pullback"),("amount_ok","amount_ok"),("ma20","ma20"),("atr14","atr14"))

class OptStrategy(bt.Strategy):
    params = (("stop_type","fixed5"),("max_pos",3),("max_daily_buy",0))

    def __init__(self):
        self._stops = {}; self._daily_buys = 0; self._last_date = None
        self.trades_log = []  # [entry_date, exit_date, code, entry_px, regime]

    def log(self, txt): print(f"    {self.datas[0].datetime.date(0)} | {txt}", flush=True)

    def notify_order(self, order):
        if order.status != order.Completed: return
        nm = order.data._name; px = order.executed.price
        if order.isbuy():
            st = self.params.stop_type
            if st == "fixed5": sp = px * 0.95
            elif st == "fixed8": sp = px * 0.92
            elif st == "fixed10": sp = px * 0.90
            elif st == "atr2":
                atr = order.data.atr14[0]
                sp = px - 2 * (atr if atr and atr > 0 else px * 0.03)
            else: sp = px * 0.95
            self._stops[nm] = sp; self._daily_buys += 1
            self.trades_log.append([order.data.datetime.date(0), None, nm, px, None])
        elif order.issell():
            for t in self.trades_log:
                if t[0] is not None and t[1] is None and t[2] == nm:
                    t[1] = order.data.datetime.date(0); t[4] = px; break
            self._stops.pop(nm, None)

    def next(self):
        today = self.datas[0].datetime.date(0)
        if self._last_date != today:
            self._daily_buys = 0; self._last_date = today
        pos_count = sum(1 for d in self.datas[1:] if self.getposition(d).size > 0)
        for d in self.datas[1:]:
            nm = d._name; pos = self.getposition(d)
            if pos.size > 0:
                stop = self._stops.get(nm, d.close[0] * 0.95)
                if d.close[0] < stop: self.close(data=d)
                continue
            if self.params.max_daily_buy > 0 and self._daily_buys >= self.params.max_daily_buy: continue
            try: ok = d.market_ok[0] and d.resonance[0] and d.ma20_ok[0] and d.pullback[0]
            except: continue
            if not ok or pos_count >= self.params.max_pos: continue
            cash = self.broker.get_cash()
            slots = max(1, self.params.max_pos - pos_count)
            size = int(cash / slots * 0.98 / max(d.close[0], 0.01))
            if size >= 100: self.buy(data=d, size=size); pos_count += 1; self._daily_buys += 1

# ======================== RUNNER ========================
def build_cerebro(sig, stop_type, max_pos, max_daily_buy):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(OptStrategy, stop_type=stop_type, max_pos=max_pos, max_daily_buy=max_daily_buy)
    cerebro.broker.setcash(1_000_000); cerebro.broker.setcommission(commission=0.0003); n = 0
    for code in ALL_CODES:
        try: sub = sig.xs(code, level="code", drop_level=False)
        except: continue
        if sub.empty: continue
        sub = sub.reset_index(level="code", drop=True)
        out = pd.DataFrame(index=sub.index)
        for c in ["open","high","low","close","volume"]:
            out[c] = sub[c].fillna(0).astype(float) if c in sub.columns else 0
        out["openinterest"] = 0
        for ln in ["market_ok","resonance","ma20_ok","pullback","amount_ok","ma20","atr14"]:
            out[ln] = sub[ln].fillna(0).astype(float) if ln in sub.columns else 0
        data = SigData(dataname=out); data._name = code
        cerebro.adddata(data); n += 1
    return cerebro, n

def run_one(sig, stop_type, max_pos, max_daily_buy, quiet=False):
    cerebro, n = build_cerebro(sig, stop_type, max_pos, max_daily_buy)
    if n == 0: return {"error":"no data"}
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, riskfreerate=0.02, timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.DrawDown)
    cerebro.addanalyzer(bt.analyzers.Returns, tann=252)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer)
    results = cerebro.run(); strat = results[0]
    final = cerebro.broker.getvalue()
    tr = final / 1_000_000 - 1
    days = (datetime.strptime(END,"%Y-%m-%d") - datetime.strptime(START,"%Y-%m-%d")).days
    yr = max(days/365.25, 0.01); ar = (1+tr)**(1/yr)-1
    # Drawdown
    dd_a = strat.analyzers.drawdown.get_analysis()
    md = 0
    try:
        if hasattr(dd_a, 'max'): md = dd_a.max.drawdown
        elif isinstance(dd_a, dict):
            d = dd_a.get('drawdown', {})
            md = d.get('drawdown', 0) if isinstance(d, dict) else 0
    except: md = 0
    # Sharpe
    sa = strat.analyzers.sharperatio.get_analysis()
    sp = sa.get('sharperatio', None) if isinstance(sa, dict) else None
    # Trades
    ta = strat.analyzers.tradeanalyzer.get_analysis()
    tt=wn=ls=0
    try:
        if isinstance(ta, dict):
            tt = ta.get('total',{}).get('total',0)
            wn = ta.get('won',{}).get('total',0)
            ls = ta.get('lost',{}).get('total',0)
        else:
            tt = ta.total.total; wn = ta.won.total; ls = ta.lost.total
    except: pass
    r = {"stop_type":stop_type,"max_pos":max_pos,"daily_buy":max_daily_buy or 0,
         "total_ret_pct":round(tr*100,1),"ann_ret_pct":round(ar*100,1),
         "sharpe":round(sp,2) if sp is not None else None,
         "max_dd":round(md,1) if md else 0,
         "trades":tt,"win":wn,"loss":ls,"win_rate":round(wn/max(tt,1)*100,1),
         "final":round(final,0),"stocks":n}
    return r, strat

# ======================== PERIOD ANALYSIS ========================
def analyze_periods(sig, regime_df, stop_type, max_pos, max_daily_buy):
    r, strat = run_one(sig, stop_type, max_pos, max_daily_buy)
    if "error" in r: return r
    trades = strat.trades_log
    # Each trade: [entry_date, exit_date, code, entry_price, exit_price]
    completed = [t for t in trades if t[1] is not None and t[3] and t[4]]
    open_pos = [t for t in trades if t[1] is None]
    print(f"  已完成: {len(completed)} 笔, 持仓中: {len(open_pos)} 笔")

    # Classify each completed trade by its entry date's regime
    regime_map = {}
    for dt, row in regime_df.iterrows():
        regime_map[dt.date()] = row["regime"]
    by_regime = {"上涨":[], "震荡":[], "下跌":[], "未知":[]}
    for t in completed:
        reg = regime_map.get(t[0], "未知")
        if reg not in by_regime: reg = "未知"
        ret = (t[4]/t[3] - 1)*100
        by_regime[reg].append(ret)

    print(f"\n  周期细分 (参数: stop={stop_type} pos={max_pos} daily={max_daily_buy}):")
    print(f"  {'市场状态':<8} {'交易数':<6} {'平均收益':<10} {'正收益':<6} {'胜率':<8}")
    print(f"  {'-'*38}")
    for reg in ["上涨","震荡","下跌","未知"]:
        rets = by_regime[reg]
        if not rets:
            print(f"  {reg:<8} {'0':<6} {'--':<10} {'--':<6} {'--':<8}")
            continue
        avg = np.mean(rets); pos = sum(1 for r in rets if r > 0); wr = pos/len(rets)*100
        print(f"  {reg:<8} {len(rets):<6} {avg:>+6.2f}%{'':<4} {pos:<6} {wr:>5.1f}%")

    # Also analyze open positions by entry regime
    for t in open_pos:
        reg = regime_map.get(t[0], "未知")
        print(f"  持仓中: {t[0]} {t[2]} 买入{t[3]:.2f} 市场状态={reg}")

    print(f"\n  全区间表现: 收益率={r['total_ret_pct']}% 年化={r['ann_ret_pct']}% "
          f"夏普={r['sharpe']} 回撤={r['max_dd']}% 胜率={r['win_rate']}%")
    return r

# ======================== MAIN ========================
def main():
    print("=" * 70)
    print("  波段交易模型 - 参数优化 + 场景分析")
    print(f"  期间: {START} ~ {END}")
    print("=" * 70)
    t0 = time.time()

    print("\n[1] 获取/加载数据...")
    idx = fetch_index().loc[START:END]
    stocks = fetch_stocks()
    sig, regime_df = compute_signals(idx, stocks)
    total_codes = sig.index.get_level_values("code").nunique()
    print(f"  信号矩阵: {len(sig)} 行, {total_codes} 只股票")

    # ---- 参数网格 ----
    print("\n[2] 参数网格扫描 (4止损 × 2仓位 × 2单日限制 = 16组)...\n")
    grid = list(itertools.product(["fixed5","fixed8","fixed10","atr2"], [3,5], [0,2]))
    results = []
    for sp, mp, db in grid:
        r, _ = run_one(sig, sp, mp, db)
        if "error" in r: continue
        results.append(r)
        inf = "\u221e"
        print(f"  stop={sp:>7} pos={mp} daily={db or inf:>2}  "
              f"ret={r['total_ret_pct']:>6.1f}%  ann={r['ann_ret_pct']:>5.1f}%  "
              f"sp={str(r['sharpe']):>5}  mdd={str(r['max_dd']):>5}%  "
              f"tr={r['trades']:>2}  wr={r['win_rate']:>4.1f}%")

    df = pd.DataFrame(results)

    # ---- 结论 ----
    print("\n" + "=" * 70)
    print("  [优化结论]")
    print("=" * 70)
    bsp = df.loc[df["sharpe"].fillna(0).idxmax()]; bret = df.loc[df["total_ret_pct"].idxmax()]; bwr = df.loc[df["win_rate"].idxmax()]
    print(f"  最高夏普  : stop={bsp['stop_type']:>7} pos={bsp['max_pos']} daily={bsp['daily_buy'] or inf:>2}  "
          f"ret={bsp['total_ret_pct']}%  ann={bsp['ann_ret_pct']}%  sp={bsp['sharpe']}  mdd={bsp['max_dd']}%")
    print(f"  最高收益  : stop={bret['stop_type']:>7} pos={bret['max_pos']} daily={bret['daily_buy'] or inf:>2}  "
          f"ret={bret['total_ret_pct']}%  ann={bret['ann_ret_pct']}%")
    print(f"  最高胜率  : stop={bwr['stop_type']:>7} pos={bwr['max_pos']} daily={bwr['daily_buy'] or inf:>2}  "
          f"wr={bwr['win_rate']}%")

    # Recommend: exclude fixed5/fixed10, prefer pos=5
    rec = df[(df["stop_type"].isin(["fixed8","atr2"])) & (df["max_pos"] == 5)]
    if rec.empty: rec = df[df["max_pos"] == 5]
    best = rec.loc[rec["sharpe"].fillna(0).idxmax()] if not rec.empty else bsp
    print(f"\n  推荐参数  : stop={best['stop_type']} pos={best['max_pos']} daily={best['daily_buy'] or inf}  "
          f"ret={best['total_ret_pct']}%  ann={best['ann_ret_pct']}%  sp={best['sharpe']}  wr={best['win_rate']}%")

    # ---- 周期分析 ----
    print("\n" + "=" * 70)
    print("  [周期敏感性分析]")
    print("=" * 70)
    reg_dist = regime_df["regime"].value_counts()
    for reg_name in ["上涨","震荡","下跌"]:
        print(f"  {reg_name}: {reg_dist.get(reg_name, 0)} 天")

    rec_stop = best["stop_type"]; rec_pos = int(best["max_pos"]); rec_db = int(best["daily_buy"])
    # Period analysis runs with fixed8 pos=5 daily=2 (more completed trades for meaningful breakdown)
    analyze_periods(sig, regime_df, "fixed8", 5, 2)

    # ---- 完整对比表 ----
    print("\n" + "=" * 70)
    print("  [完整参数对比表]")
    print("=" * 70)
    for _, r in df.iterrows():
        print(f"  {r['stop_type']:>7}  pos={r['max_pos']}  daily={r['daily_buy'] or inf:>2}  "
              f"收益={r['total_ret_pct']:>6.1f}%  年化={r['ann_ret_pct']:>5.1f}%  "
              f"夏普={str(r['sharpe']):>5}  回撤={str(r['max_dd']):>5}%  "
              f"交易={r['trades']:>2}  胜率={r['win_rate']:>4.1f}%")

    t1 = time.time()
    print(f"\n总耗时: {t1-t0:.0f}s")
    print("\n" + "=" * 70)
    print("  [策略建议]")
    print("=" * 70)
    print(f"  止损: {rec_stop} (综合回撤/胜率/收益率最优)")
    print(f"  仓位: {rec_pos}只 + 单日上限{rec_db}只")
    print(f"  震荡市: 如胜率骤降, 可加严缩量标准至0.6 或暂停交易")
    print("=" * 70)
    return df

if __name__ == "__main__":
    df = main()
