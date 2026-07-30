# -*- coding: utf-8 -*-
"""
简化版回测 v3 — 统一事件流引擎
选股: CROSS(MA60) + 量比>=1.5 + 20日涨<=25% + 市值20~500亿 + 上证站MA60
卖出: 跌破MA5次日开盘
"""
import os, sys, json, time, copy
import numpy as np
import pandas as pd
from collections import namedtuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache_bt3")
RESULT_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULT_DIR, exist_ok=True)
Trade = namedtuple("Trade", ["code", "name", "signal_date", "buy_date", "sell_date",
                              "buy_price", "sell_price", "pnl_pct", "hold_days", "exit_reason"])

def load_sh_index():
    sh_f = os.path.join(CACHE_DIR, "index_000001.pkl")
    if os.path.exists(sh_f):
        return pd.read_pickle(sh_f)
    import akshare as ak
    sh = ak.stock_zh_index_daily(symbol="sh000001")
    sh["date"] = pd.to_datetime(sh["date"])
    sh.to_pickle(sh_f)
    return sh

def run():
    sh = load_sh_index()
    sc = sh["close"].values.astype(float)
    sd = sh["date"].values
    sh_ma60 = {}
    for i in range(59, len(sc)):
        d = pd.Timestamp(sd[i]).strftime("%Y-%m-%d")
        sh_ma60[d] = float(np.mean(sc[i-59:i+1]))
    sh_close = {}
    for i in range(len(sc)):
        d = pd.Timestamp(sd[i]).strftime("%Y-%m-%d")
        sh_close[d] = float(sc[i])

    files = sorted([f for f in os.listdir(CACHE_DIR) if f.startswith("stock_") and f.endswith(".pkl") and f != "stock_list.pkl"])

    events = []  # (date, type, dict)  type: buy/sell
    signal_count = 0

    for idx, fname in enumerate(files):
        code = fname.replace("stock_", "").replace(".pkl", "")
        try:
            df = pd.read_pickle(os.path.join(CACHE_DIR, fname))
        except:
            continue
        if len(df) < 80:
            continue
        name = df["name"].iloc[0] if "name" in df.columns else code
        c_arr = df["close"].values.astype(float)
        o_arr = df["open"].values.astype(float)
        v_arr = df["volume"].values.astype(float)
        cm_arr = df["circ_mv"].values.astype(float) if "circ_mv" in df.columns else np.zeros(len(df))
        dates = df["date"].values
        n = len(dates)

        for i in range(70, n):
            ma60 = np.mean(c_arr[i-59:i+1])
            ma60_prev = np.mean(c_arr[i-60:i])
            cp = c_arr[i]
            if not (c_arr[i-1] < ma60_prev and cp >= ma60):
                continue
            vol_ma60 = np.mean(v_arr[i-59:i+1])
            if vol_ma60 <= 0 or v_arr[i] / vol_ma60 < 1.5:
                continue
            if i >= 20:
                if (cp / c_arr[i-20] - 1) * 100 > 25:
                    continue
            cm = cm_arr[i]
            if cm < 20 or cm > 500:
                continue
            d = pd.Timestamp(dates[i]).strftime("%Y-%m-%d")
            if d in sh_ma60 and d in sh_close:
                if sh_close[d] < sh_ma60[d]:
                    continue
            if i + 1 >= n: continue
            buy_open = float(o_arr[i+1])
            buy_price = buy_open * 1.001 * 1.00025
            buy_date = str(pd.Timestamp(dates[i+1]).date())

            sell_price = None; sell_date = None; reason = "end"
            for j in range(i+2, n):
                if j >= 4:
                    ma5 = np.mean(c_arr[j-4:j+1])
                    if c_arr[j] < ma5:
                        if j + 1 < n:
                            sell_open = float(o_arr[j+1])
                            sell_price = sell_open * 0.999 * 0.9985
                            sell_date = str(pd.Timestamp(dates[j+1]).date())
                            reason = "break_ma5"
                        else:
                            sell_price = float(c_arr[j] * 0.999 * 0.9985)
                            sell_date = str(pd.Timestamp(dates[j]).date())
                            reason = "end"
                        break
            if sell_price is None:
                sell_price = float(c_arr[-1] * 0.999 * 0.9985)
                sell_date = str(pd.Timestamp(dates[-1]).date())
                reason = "end"

            events.append((buy_date, "buy", {
                "code": code, "name": name, "signal_date": d,
                "buy_price": buy_price, "sell_price": sell_price,
                "sell_date": sell_date, "exit_reason": reason,
            }))
            events.append((sell_date, "sell", {
                "code": code, "buy_price": buy_price, "sell_price": sell_price,
                "name": name,
            }))
            signal_count += 1

        if (idx+1) % 200 == 0:
            print(f"  scan {idx+1}/{len(files)}, signals={signal_count}")

    print(f"  扫描完成: {signal_count} signals")

    # 统一事件流
    events.sort(key=lambda x: (x[0], 0 if x[1]=="buy" else 1))

    cash = 1000000.0
    cap_per = 1000000 * 0.20
    positions = {}
    trades = []
    equity_curve = [1000000.0]
    curve_dates = ["2024-01-02"]

    for dt, etype, data in events:
        if etype == "buy":
            if data["code"] in positions:
                continue
            if len(positions) >= 5:
                continue
            cost = cap_per
            if cost > cash:
                cost = cash
            if cost < data["buy_price"] * 100:
                continue
            shares = int(cost / data["buy_price"])
            if shares <= 0:
                continue
            cash -= shares * data["buy_price"]
            positions[data["code"]] = {
                "shares": shares, "buy_price": data["buy_price"],
                "buy_date": data["signal_date"], "name": data["name"],
                "sell_price": data["sell_price"],
            }

        elif etype == "sell":
            if data["code"] not in positions:
                continue
            pos = positions.pop(data["code"])
            proceeds = pos["shares"] * data["sell_price"]
            pnl = (data["sell_price"] / pos["buy_price"] - 1) * 100
            hold = (pd.Timestamp(dt) - pd.Timestamp(pos["buy_date"])).days
            trades.append(Trade(
                data["code"], pos["name"], pos["buy_date"],
                pos["buy_date"], dt,
                round(pos["buy_price"], 4), round(data["sell_price"], 4),
                round(pnl, 2), hold, pos.get("sell_reason", "break_ma5"),
            ))
            cash += proceeds
            total = cash + sum(p["shares"] * data["sell_price"]
                               for c, p in positions.items())
            equity_curve.append(round(total, 2))
            curve_dates.append(dt)

    # 指标
    total_ret = (equity_curve[-1] / 1000000 - 1) * 100
    annual_ret = ((1 + total_ret/100) ** (1/2.5) - 1) * 100
    max_dd = 0; peak = equity_curve[0]
    for v in equity_curve:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd
    daily_rets = []
    for k in range(1, len(equity_curve)):
        r = (equity_curve[k] - equity_curve[k-1]) / equity_curve[k-1] if equity_curve[k-1] > 0 else 0
        daily_rets.append(r)
    sharpe = np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252) if np.std(daily_rets) > 0 else 0

    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    wr = len(wins)/len(trades)*100
    avg_w = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_l = np.mean([t.pnl_pct for t in losses]) if losses else 0
    total_w = sum(t.pnl_pct for t in wins) or 1
    total_l = sum(abs(t.pnl_pct) for t in losses) or 1
    pf = total_w / total_l
    wh = np.mean([t.hold_days for t in wins]) if wins else 0
    lh = np.mean([t.hold_days for t in losses]) if losses else 0

    metrics = {
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
        "total_signals": signal_count,
    }

    # 打印
    print("\n" + "=" * 80)
    print("绩效指标")
    print("=" * 80)
    for k, v in metrics.items():
        print(f"  {k:<25} {str(v):>15}")

    st = sorted(trades, key=lambda t: t.buy_date)
    print("\n前20笔:")
    for t in st[:20]:
        print(f"  {t.code} {t.name[:6]:<6} {t.buy_date}->{t.sell_date}  {t.pnl_pct:+7.2f}%  {t.hold_days}d  {t.exit_reason}")

    print("\n分年度:")
    ymap = {}
    for t in st:
        ymap.setdefault(t.buy_date[:4], []).append(t)
    for y in sorted(ymap):
        ts = ymap[y]
        w = [t for t in ts if t.pnl_pct > 0]
        print(f"  {y}: {len(ts)}笔, 胜率{len(w)/len(ts)*100:.0f}%, 合计{sum(t.pnl_pct for t in ts):+.1f}%")

    print("\n盈利vs亏损持有天数:")
    print(f"  盈利: {wh:.1f}天, 亏损: {lh:.1f}天")

    # 案例
    print("\n案例验证:")
    for code, dt_str in [("300679","2026-04-08"),("301392","2026-04-01"),("603083","2026-04-08"),
                          ("002259","2026-01-05"),("002238","2026-02-03")]:
        fp = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
        if not os.path.exists(fp): continue
        df = pd.read_pickle(fp)
        c_arr = df["close"].values.astype(float)
        v_arr = df["volume"].values.astype(float)
        cm_arr = df["circ_mv"].values.astype(float)
        name = df["name"].iloc[0]
        mask = [str(d)[:10] for d in df["date"].values]
        if dt_str not in mask: continue
        i = mask.index(dt_str)
        cp = c_arr[i]; ma60 = np.mean(c_arr[i-59:i+1])
        cross = bool(c_arr[i-1] < np.mean(c_arr[i-60:i]) and cp >= ma60)
        vr = v_arr[i]/np.mean(v_arr[i-59:i+1]) if np.mean(v_arr[i-59:i+1])>0 else 0
        chg20 = (cp/c_arr[i-20]-1)*100 if i>=20 else 0
        cm = cm_arr[i]
        sel = cross and vr>=1.5 and chg20<=25 and 20<=cm<=500
        print(f"  {name}({code}) {dt_str}: {'入选' if sel else '过滤'}  "
              f"cross={cross} vr={vr:.1f}x chg20={chg20:.1f}% cm={cm:.0f}亿")

    # 保存
    result = {
        "version": "simplified_v3_unified_events",
        "metrics": metrics,
        "trades": [t._asdict() for t in st],
        "equity": [float(v) for v in equity_curve],
        "dates": curve_dates,
    }
    with open(os.path.join(RESULT_DIR, "result_simplified.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果: {os.path.join(RESULT_DIR, 'result_simplified.json')}")

if __name__ == "__main__":
    print("简化版回测 v3 — 统一事件流")
    t0 = time.time()
    run()
    print(f"耗时: {time.time()-t0:.0f}s")