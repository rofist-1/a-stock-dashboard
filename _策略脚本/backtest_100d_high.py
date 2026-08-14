# -*- coding: utf-8 -*-
"""
百日新高 + 回踩5日线 回测策略
================================
大盘条件 : 全市场百日新高股票数量 > 百日新低股票数量
选股     : 当日首次创百日新高（收盘价 >= 前100交易日最高价，且为首次突破）
买入     : 入选后第2个交易日，收盘价在5日均线 ±1% 范围内
卖出     : 持有3个交易日后卖出，或跌破5日均线止损（先到先出）
回测区间 : 2020-01-01 ~ 2025-12-31

数据源   : akshare (新浪 前复权日线) — 迪雅API Token已过期(401)
费用     : 买入 *(1.001)*(1.00025)，卖出 *(0.999)*(0.99875)（与 audit_backtest 口径一致）
输出     : 胜率 / 平均收益率 / 最大回撤 / 交易次数

用法:
  python backtest_100d_high.py --fetch [--limit N]   # 先下载全市场日线缓存
  python backtest_100d_high.py                        # 运行回测
"""
import os, sys, time, pickle
import numpy as np
import pandas as pd
import akshare as ak
import requests
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache_bt4")
OUT_DIR = os.path.join(os.path.dirname(BASE_DIR), "results")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------- 数据 ----------------
FETCH_START = "20190601"          # 回测从2020起，需要2019中的100日缓冲
FETCH_END   = "20251231"
FETCH_WORKERS = 24

# ---------------- 策略参数 ----------------
LOOKBACK      = 100     # 百日新高
MA_N          = 5       # 5日均线
PULLBACK_TOL  = 0.01    # 回踩 ±1%
BUY_DELAY     = 2       # 入选后第2个交易日买入
HOLD_DAYS     = 3       # 持有3个交易日
BT_START      = "2020-01-01"
BT_END        = "2025-12-31"

# ---------------- 组合与费用 ----------------
INIT_CAPITAL = 1_000_000
MAX_POS      = 10                    # 同时最多持10只
SLIP = 0.001; COMM = 0.00025; SELL_FEE = 0.00125
BUY_MULT   = (1 + SLIP) * (1 + COMM)
SELL_MULT  = (1 - SLIP) * (1 - SELL_FEE)


# ═══════════════════════════════════════════
#  数据下载
# ═══════════════════════════════════════════
#  说明: 迪雅API Token已过期(401); 东财/新浪被风控; 改用腾讯日线(qfq),
#        3 次分页(每页640根)可覆盖 2019-06~2025-12, 纯requests线程安全。
TX_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"

def _path(code):
    return os.path.join(CACHE_DIR, f"stock_{code}.pkl")

def get_universe():
    info = ak.stock_info_a_code_name()
    codes = info["code"].astype(str).str.zfill(6)
    return sorted(c for c in codes if c[0] in ("6", "0", "3"))

def fetch_one(code):
    """腾讯日线 qfq: 倒序分页直到覆盖 2019-06-01"""
    from akshare.utils import demjson
    symbol = ("sh" if code.startswith("6") else "sz") + code
    for attempt in range(3):
        try:
            rows = []
            end = FETCH_END
            for _ in range(8):
                d_end = f"{end[:4]}-{end[4:6]}-{end[6:]}"
                params = {"_var": "kline_dayqfq",
                          "param": f"{symbol},day,1990-01-01,{d_end},640,qfq"}
                r = requests.get(TX_URL, params=params, timeout=15)
                t = r.text
                j = demjson.decode(t[t.find("={") + 1:])["data"][symbol]
                key = "day" if "day" in j else ("qfqday" if "qfqday" in j else "hfqday")
                chunk = j.get(key) or []
                if not chunk:
                    break
                rows.extend(chunk)
                first = chunk[0][0]
                if int(first.replace("-", "")) <= int(FETCH_START):
                    break
                end = (pd.Timestamp(first) - pd.Timedelta(days=1)).strftime("%Y%m%d")
            if not rows:
                return code, 0
            df = pd.DataFrame([r[:5] for r in rows],
                              columns=["date", "open", "close", "high", "low"])
            df["date"] = pd.to_datetime(df["date"])
            for c in ["open", "close", "high", "low"]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
            df = df[df["date"] >= pd.Timestamp(pd.to_datetime(FETCH_START))]
            df.to_pickle(_path(code))
            return code, len(df)
        except Exception:
            if attempt == 2:
                return code, -1
            time.sleep(1 + attempt)
    return code, -1

def fetch_all(limit=None, workers=FETCH_WORKERS):
    codes = get_universe()
    if limit:
        codes = codes[:limit]
    todo = [c for c in codes if not os.path.exists(_path(c))]
    print(f"  股票池 {len(codes)} 只, 待下载 {len(todo)} 只", flush=True)
    if not todo:
        return
    t0 = time.time(); ok = err = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (code, n) in enumerate(ex.map(fetch_one, todo), 1):
            if n > 0:
                ok += 1
            else:
                err += 1
            if i % 200 == 0 or i == len(todo):
                el = time.time() - t0
                rate = i / el
                print(f"  [{i}/{len(todo)}] ok={ok} err={err} {el:.0f}s "
                      f"({rate:.1f}只/s 预计剩余{(len(todo)-i)/max(rate,0.01)/60:.0f}min)",
                      flush=True)
    print(f"  完成: 成功{ok} 失败{err} 用时{(time.time()-t0)/60:.1f}min")

def load_all():
    codes = sorted(f.replace("stock_", "").replace(".pkl", "")
                   for f in os.listdir(CACHE_DIR) if f.startswith("stock_"))
    print(f"  加载缓存 {len(codes)} 只股票 ...", flush=True)
    data = {}
    for i, c in enumerate(codes, 1):
        try:
            df = pd.read_pickle(_path(c))
        except Exception:
            continue
        if len(df) >= LOOKBACK + MA_N:
            data[c] = df
        if i % 1000 == 0:
            print(f"    {i}/{len(codes)}", flush=True)
    return data


# ═══════════════════════════════════════════
#  信号计算
# ═══════════════════════════════════════════
def _signals(df):
    """返回 per-stock 的布尔列: is_high / is_low / breakout"""
    h = df["high"].rolling(LOOKBACK, min_periods=LOOKBACK).max().shift(1)
    l = df["low"].rolling(LOOKBACK, min_periods=LOOKBACK).min().shift(1)
    is_high = (df["close"] >= h).fillna(False)
    is_low = (df["close"] <= l).fillna(False)
    breakout = is_high & (~is_high.shift(1).fillna(False))
    return is_high, is_low, breakout

def compute_breadth(data, bt_start, bt_end):
    """全市场每日 百日新高/新低 数量 → market_ok: 新高数 > 新低数"""
    high_cnt = Counter(); low_cnt = Counter()
    all_dates = set()
    start = pd.Timestamp(bt_start); end = pd.Timestamp(bt_end)
    for c, df in data.items():
        is_high, is_low, _ = _signals(df)
        d = df["date"]
        mh = (d >= start) & (d <= end) & is_high
        ml = (d >= start) & (d <= end) & is_low
        if mh.any():
            vals, cnts = np.unique(d.to_numpy()[mh.to_numpy()].astype("datetime64[D]"), return_counts=True)
            for v, k in zip(vals, cnts):
                high_cnt[pd.Timestamp(v)] += int(k)
        if ml.any():
            vals, cnts = np.unique(d.to_numpy()[ml.to_numpy()].astype("datetime64[D]"), return_counts=True)
            for v, k in zip(vals, cnts):
                low_cnt[pd.Timestamp(v)] += int(k)
        all_dates.update(pd.DatetimeIndex(d[(d >= start) & (d <= end)].values).normalize())
    days = sorted(all_dates)
    market_ok = {d: high_cnt.get(d, 0) > low_cnt.get(d, 0) for d in days}
    return market_ok, high_cnt, low_cnt, all_dates


def generate_trades(data, market_ok, bt_start, bt_end):
    """生成交易记录 + 需要 mark-to-market 的收盘价序列"""
    trades = []
    closes = {}
    start = pd.Timestamp(bt_start); end = pd.Timestamp(bt_end)
    for c, df in data.items():
        is_high, _, breakout = _signals(df)
        d = df["date"].values
        close = df["close"].values
        ma5 = df["close"].rolling(MA_N, min_periods=MA_N).mean().values
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = close / ma5
            pull = (np.abs(ratio - 1.0) <= PULLBACK_TOL) & np.isfinite(ratio)

        for i in np.where(breakout.values)[0]:
            sig_date = pd.Timestamp(d[i])
            if sig_date < start or sig_date > end:
                continue
            if not market_ok.get(sig_date, False):
                continue
            j = i + BUY_DELAY                        # 入选后第2个交易日
            if j >= len(df):
                continue
            if not pull[j] or np.isnan(ma5[j]):
                continue
            entry_date = pd.Timestamp(d[j])
            entry_fill = close[j] * BUY_MULT

            # 卖出: 先看止损(跌破5日线), 再看持有3日
            exit_idx = None; exit_reason = ""
            for k in range(j + 1, j + HOLD_DAYS + 1):
                if k >= len(df):
                    k = len(df) - 1                  # 停牌/到期, 用最后一根
                    exit_reason = "到期(无数据)"
                    exit_idx = k
                    break
                if close[k] < ma5[k]:
                    exit_idx = k; exit_reason = "跌破5日线止损"
                    break
                if k == j + HOLD_DAYS:
                    exit_idx = k; exit_reason = "持有3日卖出"
            exit_date = pd.Timestamp(d[exit_idx])
            exit_fill = close[exit_idx] * SELL_MULT
            ret = (exit_fill - entry_fill) / entry_fill * 100
            trades.append({
                "code": c, "signal_date": sig_date, "entry_date": entry_date,
                "entry_price": round(entry_fill, 3), "exit_date": exit_date,
                "exit_price": round(exit_fill, 3), "ret_pct": round(ret, 3),
                "hold_days": exit_idx - j, "exit_reason": exit_reason,
            })
        if closes.get(c) is None:
            closes[c] = pd.Series(close, index=pd.DatetimeIndex(df["date"]))
    trades.sort(key=lambda t: (t["entry_date"], t["code"]))
    return trades, closes


# ═══════════════════════════════════════════
#  组合模拟 (现金制, 盯市) → 最大回撤
# ═══════════════════════════════════════════
def simulate_equity(trades, closes, all_dates, bt_start, bt_end):
    calendar = sorted(d for d in all_dates
                      if pd.Timestamp(bt_start) <= d <= pd.Timestamp(bt_end))
    if not calendar:
        return [], 0
    by_entry = {}
    for t in trades:
        by_entry.setdefault(t["entry_date"], []).append(t)
    by_exit = {}
    for t in trades:
        by_exit.setdefault(t["exit_date"], []).append(t)

    cash = float(INIT_CAPITAL)
    pos = []                      # code, entry_fill, shares, exit_date, last_close
    curve = []
    executed = 0
    for day in calendar:
        # 先处理当日卖出
        for t in by_exit.get(day, []):
            for p in pos:
                if p["code"] == t["code"] and p["entry_date"] == t["entry_date"]:
                    cash += p["shares"] * t["exit_price"]
                    p["closed"] = True
                    break
        pos = [p for p in pos if not p.get("closed")]
        # 再处理当日买入 (仓位 = 当前净值/MAX_POS, 不足则跳过)
        for t in by_entry.get(day, []):
            if len(pos) >= MAX_POS:
                break
            equity_now = cash + sum(p["shares"] * p["last_close"] for p in pos)
            notional = equity_now / MAX_POS
            if notional <= 0 or cash <= 0:
                break
            shares = int(notional / t["entry_price"] / 100) * 100   # 整手100股
            if shares <= 0:
                shares = notional / t["entry_price"]                 # 高价股放宽为碎股
            cost = shares * t["entry_price"]
            if cost > cash:
                shares = int(cash / t["entry_price"] / 100) * 100
                cost = shares * t["entry_price"]
                if shares <= 0:
                    break
            cash -= cost
            executed += 1
            pos.append({"code": t["code"], "entry_date": t["entry_date"],
                        "entry_fill": t["entry_price"], "shares": shares,
                        "exit_date": t["exit_date"], "last_close": t["entry_price"]})
        # 按收盘价盯市
        for p in pos:
            v = closes[p["code"]].get(day)
            if v is not None and not np.isnan(v):
                p["last_close"] = float(v)
        value = cash + sum(p["shares"] * p["last_close"] for p in pos)
        curve.append((day, value))
    return curve, executed

def max_drawdown(curve):
    peak = -np.inf; mdd = 0.0; peak_d = lo_d = hi_d = None
    for d, v in curve:
        if v > peak:
            peak = v; peak_d = d
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > mdd:
            mdd = dd; hi_d = peak_d; lo_d = d
    return mdd, hi_d, lo_d


# ═══════════════════════════════════════════
#  报告
# ═══════════════════════════════════════════
def print_report(trades, curve, market_ok, executed):
    if not trades:
        print("  无交易!"); return
    rets = np.array([t["ret_pct"] for t in trades])
    wins = rets > 0
    n = len(trades)
    win_rate = wins.sum() / n * 100
    avg_ret = rets.mean()
    med_ret = np.median(rets)
    cum = curve[-1][1] if curve else INIT_CAPITAL
    total_ret = (cum / INIT_CAPITAL - 1) * 100
    mdd, hi_d, lo_d = max_drawdown(curve)

    if curve:
        span_y = (curve[-1][0] - curve[0][0]).days / 365.25
        ann = (cum / INIT_CAPITAL) ** (1 / max(span_y, 0.1)) - 1
    else:
        span_y = 0; ann = 0

    t0, t1 = pd.Timestamp(BT_START), pd.Timestamp(BT_END)
    ok_days = sum(1 for d, v in market_ok.items() if v and t0 <= d <= t1)
    all_days = sum(1 for d in market_ok if t0 <= d <= t1)

    print(f"""
{'='*68}
  百日新高 + 回踩5日线 策略回测
  回测区间: {BT_START} ~ {BT_END}
{'='*68}

【数据】
  沪深股票: {len(closes) if hasattr(closes,'__len__') else '?'} 只 (前复权日线)
  大盘过滤: 百日新高数 > 百日新低数 满足 {ok_days}/{all_days} 个交易日

【策略输出 · 全部信号】
  交易次数:    {n}
  胜率:        {win_rate:.2f}%
  平均收益率:  {avg_ret:+.2f}%   (中位数 {med_ret:+.2f}%)
  盈亏比(均值):  {rets[rets>0].mean():+.2f}% / {rets[rets<=0].mean():+.2f}%  (盈利/亏损)

【组合净值 (100万本金, 最多同时10只, 单笔仓位=当前净值/10)】
  实际成交:    {executed} 笔
  期末净值:    {cum:,.0f}
  累计收益:    {total_ret:+.2f}%
  年化收益:    {ann*100:+.2f}%
  最大回撤:    {mdd:.2f}%   ({hi_d} ~ {lo_d})
""")

    # 年度分布
    yearly = {}
    for t in trades:
        yearly.setdefault(t["entry_date"].year, []).append(t["ret_pct"])
    print("【年度表现】")
    print(f"  {'年份':<6}{'交易数':<7}{'胜率':<8}{'平均收益':<10}{'累计(等权复利)'}")
    eq = 1.0
    for y in sorted(yearly):
        rs = np.array(yearly[y]); wr = (rs > 0).mean() * 100
        eq *= (1 + rs.mean() / 100)
        print(f"  {y:<6}{len(rs):<7}{wr:<8.1f}{rs.mean():>+7.2f}%  {eq*100:>8.1f}")

    # 退出原因分布
    print("\n【退出原因】")
    reasons = Counter(t["exit_reason"] for t in trades)
    for r, k in reasons.most_common():
        rs = np.array([t["ret_pct"] for t in trades if t["exit_reason"] == r])
        print(f"  {r:<12} {k:>6} 笔  均收益 {rs.mean():+.2f}%  胜率 {(rs>0).mean()*100:.1f}%")

    return {
        "trades": n, "win_rate": round(win_rate, 2), "avg_ret": round(float(avg_ret), 2),
        "max_drawdown": round(mdd, 2), "total_return": round(total_ret, 2),
    }


def export(trades, curve):
    tf = os.path.join(OUT_DIR, "bt_100d_high_trades.csv")
    pd.DataFrame(trades).to_csv(tf, index=False, encoding="utf-8-sig")
    ef = os.path.join(OUT_DIR, "bt_100d_high_equity.csv")
    pd.DataFrame(curve, columns=["date", "equity"]).to_csv(ef, index=False, encoding="utf-8-sig")
    print(f"  交易明细: {tf}")
    print(f"  净值曲线: {ef}")


# ═══════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════
if __name__ == "__main__":
    args = sys.argv[1:]
    if "--fetch" in args:
        limit = None
        for a in args:
            if a.startswith("--limit="):
                limit = int(a.split("=")[1])
        print("=" * 68)
        print("  下载全市场前复权日线 (腾讯)")
        print("=" * 68)
        fetch_all(limit=limit)
        if limit:
            sys.exit(0)

    print("=" * 68)
    print("  加载数据 ...")
    print("=" * 68)
    data = load_all()
    if not data:
        print("  没有缓存, 请先运行: python backtest_100d_high.py --fetch")
        sys.exit(1)

    print("  计算全市场百日新高/新低宽度 ...", flush=True)
    market_ok, high_cnt, low_cnt, all_dates = compute_breadth(data, BT_START, BT_END)
    print(f"  覆盖交易日 {len(market_ok)} 天, 其中新高>新低 {sum(1 for v in market_ok.values() if v)} 天")

    print("  生成交易信号 ...", flush=True)
    trades, closes = generate_trades(data, market_ok, BT_START, BT_END)
    print(f"  有效信号 {len(trades)} 笔 (入选信号已按大盘过滤 + 回踩确认)")

    print("  组合净值模拟 ...", flush=True)
    curve, executed = simulate_equity(trades, closes, all_dates, BT_START, BT_END)

    metrics = print_report(trades, curve, market_ok, executed)
    export(trades, curve)
