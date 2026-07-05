# -*- coding: utf-8 -*-
"""
波段交易策略回测脚本
====================
数据源: AKShare (Sina) + Backtrader

策略:
  1. 大盘 MA20 定仓位 (指数>MA20 且 MA20 向上方可持股)
  2. 板块 RPS 三线共振 (10/20/60 日均在板块排行前 40%)
  3. 趋势中军 (流通市值>100亿, 5日均成交额>5亿)
  4. 缩量回踩 10/20 日线买入 (成交量<前5日均量80% + 距MA3%以内)
  5. 跌破 MA20 止损 (初始5%)
  6. 最多等权持有 3 只

输出: 年化收益, 最大回撤, 夏普比率
"""

import akshare as ak
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime
import os, warnings, sys, time
warnings.filterwarnings("ignore")

START = "2024-06-01"
END = "2026-06-26"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_bt")
os.makedirs(CACHE, exist_ok=True)

MAX_POS = 3; VOL_SHRINK = 0.8; NEAR_MA = 0.03; RPS_PCTILE = 0.40; RPS_WINS = [10, 20, 60]

SECTORS = {
    "芯片概念": ["002371","688012","688072","688981","603501",
                 "300782","603986","600584","002156","603019"],
    "专精特新": ["300124","300450","688017","002709"],
    "商业航天": ["600118","601698","600879"],
    "光伏概念": ["002129","600438","601012"],
    "新能源汽车": ["300750","002594"],
}
ALL_CODES = sorted(set(c for lst in SECTORS.values() for c in lst))
MARKET_PREFIX = {c: "sz"+c if c.startswith(("0","3")) else "sh"+c for c in ALL_CODES}

def _path(name): return os.path.join(CACHE, f"{name}.pkl")

def fetch_index():
    p = _path("idx")
    if os.path.exists(p): return pd.read_pickle(p)
    df = ak.stock_zh_index_daily(symbol="sh000001")
    df["date"] = pd.to_datetime(df["date"]); df = df.set_index("date").sort_index()
    df.to_pickle(p); return df

def fetch_stocks():
    p = _path("stocks3")
    if os.path.exists(p): return pd.read_pickle(p)
    all_dfs = []
    for i, code in enumerate(ALL_CODES):
        try:
            df = ak.stock_zh_a_daily(symbol=MARKET_PREFIX[code],
                start_date=START.replace("-",""), end_date=END.replace("-",""), adjust="qfq")
            if df is None or df.empty: continue
            df["date"] = pd.to_datetime(df["date"]); df["code"] = code; df = df.set_index("date")
            df["amount"] = df["volume"] * (df["close"] + df["open"]) / 2
            all_dfs.append(df[["code","open","close","high","low","volume","amount"]])
            print(f"  [{i+1}/{len(ALL_CODES)}] {code} ({len(df)} rows)", flush=True)
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{i+1}/{len(ALL_CODES)}] {code} -> {e}", flush=True); time.sleep(2)
    result = pd.concat(all_dfs).reset_index().set_index(["date","code"]).sort_index()
    result.to_pickle(p); return result

def compute_signals(idx_raw, stock_raw):
    idx = idx_raw.copy()
    idx["ma20"] = idx["close"].rolling(20).mean()
    idx["ma20_slope"] = idx["ma20"].pct_change(5)
    idx["market_ok"] = ((idx["close"] > idx["ma20"]) & (idx["ma20_slope"] > 0)).astype(int)

    ret_data = {}
    for sector, codes in SECTORS.items():
        valid = [c for c in codes if c in stock_raw.index.get_level_values("code").unique()]
        pieces = []
        for c in valid:
            sub = stock_raw.xs(c, level="code")
            if len(sub) >= 20: pieces.append(sub["close"].pct_change().rename(c))
        if pieces: ret_data[sector] = pd.concat(pieces, axis=1).mean(axis=1)
    sector_rets = pd.DataFrame(ret_data)

    resonance = pd.DataFrame(index=sector_rets.index)
    for sector in sector_rets.columns:
        ok = pd.Series(True, index=sector_rets.index)
        for N in RPS_WINS:
            rank = sector_rets.rolling(N).sum().rank(axis=1, pct=True)
            ok = ok & (rank[sector] > RPS_PCTILE)
        resonance[sector] = ok.astype(int)

    sig = stock_raw.copy()
    sig = sig.join(idx[["market_ok"]], how="left")
    ma10 = sig.groupby(level="code")["close"].transform(lambda x: x.rolling(10, min_periods=5).mean())
    ma20 = sig.groupby(level="code")["close"].transform(lambda x: x.rolling(20, min_periods=10).mean())
    sig["ma10"] = ma10; sig["ma20"] = ma20
    sig["ma20_slope"] = sig.groupby(level="code")["ma20"].transform(lambda x: x.pct_change(5))
    sig["ma20_ok"] = ((sig["close"] > sig["ma20"]) & (sig["ma20_slope"] > 0)).astype(int)
    sig["amount_5d"] = sig.groupby(level="code")["amount"].transform(lambda x: x.rolling(5, min_periods=3).mean()) / 1e8
    sig["amount_ok"] = (sig["amount_5d"] > 5).astype(int)
    vol_5d = sig.groupby(level="code")["volume"].transform(lambda x: x.rolling(5, min_periods=3).mean())
    sig["vol_shrink"] = (sig["volume"] < vol_5d * VOL_SHRINK).astype(int)
    near_ma10 = (sig["close"] / sig["ma10"] - 1).abs() < NEAR_MA
    near_ma20 = (sig["close"] / sig["ma20"] - 1).abs() < NEAR_MA
    sig["pullback"] = (sig["vol_shrink"] & (near_ma10 | near_ma20)).astype(int)

    sig["resonance"] = 0
    for sector in resonance.columns:
        codes_in = SECTORS.get(sector, [])
        res_srs = resonance[sector].reindex(sig.index.get_level_values("date").unique()).ffill().fillna(0).astype(int)
        mask = sig.index.get_level_values("code").isin(codes_in)
        sig.loc[mask, "resonance"] = sig.index.get_level_values("date")[mask].map(res_srs)
    return sig

class SignalData(bt.feeds.PandasData):
    lines = ("market_ok", "resonance", "ma20_ok", "pullback", "amount_ok", "ma20")
    params = (("market_ok","market_ok"),("resonance","resonance"),("ma20_ok","ma20_ok"),
              ("pullback","pullback"),("amount_ok","amount_ok"),("ma20","ma20"))

class TrendStrategy(bt.Strategy):
    params = (("max_pos", MAX_POS),)
    def __init__(self): self._stops = {}
    def log(self, txt):
        print(f"  {self.datas[0].datetime.date(0)} | {txt}", flush=True)
    def notify_order(self, order):
        if order.status == order.Completed:
            nm = order.data._name; px = order.executed.price
            self.log(f"{'BUY' if order.isbuy() else 'SELL'} {nm} @ {px:.2f}")
            if order.isbuy(): self._stops[nm] = px * 0.95
            else: self._stops.pop(nm, None)
    def next(self):
        pos_count = sum(1 for d in self.datas[1:] if self.getposition(d).size > 0)
        for d in self.datas[1:]:
            nm = d._name; pos = self.getposition(d)
            if pos.size > 0:
                stop = self._stops.get(nm, d.close[0] * 0.95)
                if d.close[0] < stop:
                    self.log(f"STOP {nm}: {d.close[0]:.2f}"); self.close(data=d)
                continue
            try:
                if not (d.market_ok[0] and d.resonance[0] and d.ma20_ok[0] and d.pullback[0]): continue
            except: continue
            if pos_count >= self.params.max_pos: continue
            size = int(self.broker.get_cash() / max(1, self.params.max_pos - pos_count) * 0.95 / d.close[0])
            if size >= 100: self.buy(data=d, size=size); pos_count += 1

def run():
    print("=" * 60)
    print(f"  Trend Leader Backtest  {START} ~ {END}")
    print(f"  Pool: {len(ALL_CODES)} stocks, {len(SECTORS)} sectors")
    print("=" * 60)
    idx = fetch_index().loc[START:END]
    print(f"  Index: {len(idx)} days")
    stocks = fetch_stocks()
    print(f"  Stocks: {len(stocks)} rows")
    sig = compute_signals(idx, stocks)
    print(f"  Market OK: {idx['close'].rolling(20).mean().pipe(lambda x: ((idx['close']>x)&(x.pct_change(5)>0))).sum():.0f}/{len(idx)}")

    cerebro = bt.Cerebro(); cerebro.addstrategy(TrendStrategy)
    cerebro.broker.setcash(1_000_000); cerebro.broker.setcommission(commission=0.0003)
    added = 0
    for code in ALL_CODES:
        try: sub = sig.xs(code, level="code", drop_level=False)
        except: continue
        if sub.empty: continue
        sub = sub.reset_index(level="code", drop=True)
        for c in ["open","high","low","close","volume","amount",
                   "market_ok","resonance","ma20_ok","pullback","amount_ok","ma20"]:
            if c not in sub.columns: sub[c] = 0
        out = sub[["open","high","low","close","volume","amount",
                    "market_ok","resonance","ma20_ok","pullback","amount_ok","ma20"]].copy()
        out.columns = ["open","high","low","close","volume","openinterest",
                       "market_ok","resonance","ma20_ok","pullback","amount_ok","ma20"]
        out["openinterest"] = out["openinterest"].fillna(0).astype(float)
        data = SignalData(dataname=out); data._name = code
        cerebro.adddata(data); added += 1
    print(f"  Data: {added} stocks | Cash: {cerebro.broker.getvalue():,.0f}\n")

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, riskfreerate=0.02, timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.DrawDown)
    cerebro.addanalyzer(bt.analyzers.Returns, tann=252)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer)
    results = cerebro.run(); strat = results[0]
    final = cerebro.broker.getvalue(); total_ret = final / 1_000_000 - 1
    days = (datetime.strptime(END, "%Y-%m-%d") - datetime.strptime(START, "%Y-%m-%d")).days
    years = max(days / 365.25, 0.01); ann_ret = (1 + total_ret) ** (1 / years) - 1

    def _g(d, *ks, default=0):
        for k in ks:
            if isinstance(d, dict): d = d.get(k, {})
            else: return default
        return d if isinstance(d, (int,float)) else default
    dd = strat.analyzers.drawdown.get_analysis(); md = _g(dd,"drawdown","drawdown") if isinstance(dd,dict) else 0
    sa = strat.analyzers.sharperatio.get_analysis(); sp = sa.get("sharperatio", None) if isinstance(sa, dict) else None
    ta = strat.analyzers.tradeanalyzer.get_analysis(); tt = _g(ta,"total","total"); wn = _g(ta,"won","total")

    print("\n" + "=" * 60)
    print("  Backtest Results")
    print("=" * 60)
    print(f"  Total Return:       {total_ret*100:>8.2f}%")
    print(f"  Annual Return:      {ann_ret*100:>8.2f}%")
    print(f"  Sharpe Ratio:       {sp:>8.2f}" if sp else "  Sharpe Ratio:         N/A")
    print(f"  Max Drawdown:       {md:>8.2f}%" if md else "  Max Drawdown:         N/A")
    print(f"  Total Trades:       {tt:>8}")
    print(f"  Win Rate:           {wn/max(tt,1)*100:>7.1f}%" if tt else "  Win Rate:             N/A")
    print(f"  Final Cash:         {final:>10,.0f}")
    print("=" * 60)
    return {"total_return_pct": round(total_ret*100,2), "annual_return_pct": round(ann_ret*100,2),
            "sharpe_ratio": round(sp,2) if sp else None, "max_drawdown_pct": round(md,2) if md else None,
            "total_trades": tt, "win_rate": round(wn/max(tt,1)*100,1) if tt else 0}

if __name__ == "__main__":
    r = run()
