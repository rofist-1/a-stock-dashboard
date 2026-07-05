# -*- coding: gbk -*-
"""
波段信号策略回测 v1.0
================
基于 2026年1月~6月 真实市场数据模拟全流程：
  市场评分 -> 选股 -> 低吸买入 -> 阶梯止盈/移动止盈/时间止损/板块轮动
"""

import json, os, sys, math, csv
from datetime import datetime, timedelta
from collections import defaultdict

# ── 配置 ──
INITIAL_CAPITAL = 1_000_000
STATS_FILE = r"C:\Users\Rofis\Desktop\a股波段看板_2026-06-04.json"
SECTOR_DB = {
    "通信": ["603236.SH", "600745.SH", "000063.SZ", "300502.SZ", "002792.SZ"],
    "芯片": ["002371.SZ", "603986.SH", "600171.SH", "300782.SZ", "688981.SH"],
    "机器人": ["002230.SZ", "300124.SZ", "688169.SH", "002747.SZ", "600580.SH"],
    "电力": ["600900.SH", "601985.SH", "600886.SH", "003816.SZ", "600011.SH"],
    "化工": ["600160.SH", "601678.SH", "600141.SH", "002601.SZ", "600352.SH"],
    "算力": ["603019.SH", "000977.SZ", "600839.SH", "300308.SZ", "688041.SH"],
    "医药": ["600276.SH", "300760.SZ", "000538.SZ", "300015.SZ", "600196.SH"],
    "人工智能": ["002230.SZ", "600570.SH", "002415.SZ", "300033.SZ", "688111.SH"],
    "光伏": ["601012.SH", "600438.SH", "601877.SH", "300274.SZ", "688599.SH"],
    "锂电池": ["002460.SZ", "002074.SZ", "600884.SH", "300750.SZ", "002709.SZ"],
    "智能电网": ["600406.SH", "601567.SH", "300360.SZ", "002028.SZ", "600312.SH"],
    "商业航天": ["600118.SH", "002025.SZ", "600879.SH", "300447.SZ", "688070.SH"],
    "有色金属": ["601899.SH", "600547.SH", "002460.SZ", "000630.SZ", "600362.SH"],
    "元器件": ["000725.SZ", "002475.SZ", "300433.SZ", "600183.SH", "002916.SZ"],
    "煤炭": ["601088.SH", "600188.SH", "601225.SH", "600985.SH", "000983.SZ"],
    "基础建设": ["601668.SH", "601390.SH", "601186.SH", "601800.SH", "600031.SH"],
}
DIP_MIN = 0.03
DIP_MAX = 0.12
VOL_SHRINK = 0.85
DIP_SCORE_THRESHOLD = 50
TOP_N = 2
ALLOW_LEVELS = ("B", "A", "S")


def load_stats(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def market_score(d):
    s = 0
    lu = d["limitUp"]; ld = d["limitDown"]
    bomb = d["bomb"]; ch = d["chain"]
    v = d["volume"]; nh = d["newHigh"]; nl = d["newLow"]
    limitup_t = ((100,20),(80,16),(60,12),(40,8),(20,4))
    limitdown_t = ((3,25),(6,10),(9,0),(15,-10),(999,-20))
    bomb_t = ((0.2,20),(0.3,15),(0.4,10),(0.5,5),(999,-5))
    chain_t = ((20,15),(12,12),(8,8),(5,4))
    volume_t = ((35000,15),(30000,12),(25000,8),(20000,5),(15000,2))
    nhnl_t = ((15,20),(8,16),(4,12),(2,8),(1,4),(0,-10))
    for t, sc in limitup_t:
        if lu >= t: s += sc; break
    for t, sc in limitdown_t:
        if ld <= t: s += sc; break
    br = bomb / max(lu, 1)
    for t, sc in bomb_t:
        if br < t: s += sc; break
    for t, sc in chain_t:
        if ch >= t: s += sc; break
    for t, sc in volume_t:
        if v >= t: s += sc; break
    ratio = nh / max(nl, 1)
    for t, sc in nhnl_t:
        if ratio >= t: s += sc; break
    return max(0, min(100, s))


def get_level(ms):
    if ms >= 75: return "S"
    if ms >= 60: return "A"
    if ms >= 45: return "B"
    if ms >= 30: return "C"
    return "D"


def sim_price(code, day_idx, base=50):
    """模拟个股价格：随机游走，回测用"""
    import hashlib
    h = int(hashlib.md5(code.encode()).hexdigest()[:8], 16)
    r = ((h + day_idx * 7919) % 10000) / 10000
    drift = (r - 0.48) * 0.03
    noise = (r - 0.5) * 0.02
    return round(base * (1 + drift + noise), 2)


def check_dip(code, day_idx, klines):
    """简化低吸判断"""
    if not klines or len(klines) < 8:
        return {"is_dip": False, "score": 0, "price": 50}
    price = klines[-1]
    recent_high = max(klines[-8:-1]) if len(klines) > 5 else max(klines)
    pullback = (price - recent_high) / recent_high
    closes = [k for k in klines if k > 0]
    if len(closes) < 6:
        return {"is_dip": False, "score": 0, "price": price}
    avg_vol_est = 1.0
    cur_vol_est = 0.7 + (day_idx % 10) / 20
    vol_ratio = cur_vol_est / avg_vol_est
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else sum(closes) / len(closes)
    above_ma20 = price >= ma20 * 0.98
    is_dip = (pullback <= -DIP_MIN and pullback >= -DIP_MAX and vol_ratio <= VOL_SHRINK and above_ma20)
    score = 0
    if pullback <= -DIP_MIN: score += min(30, int(abs(pullback) / DIP_MIN * 25))
    if vol_ratio <= VOL_SHRINK: score += min(25, int((1 - vol_ratio) * 60))
    if above_ma20: score += 25
    if is_dip: score += 20
    return {"is_dip": is_dip, "score": min(100, score), "price": price,
            "pullback": round(pullback * 100, 1), "ma20": round(ma20, 2)}


def run_backtest(stats):
    stats.sort(key=lambda x: x["date"])
    cash = INITIAL_CAPITAL
    positions = {}  # code -> {volume, cost, peak, add_date, sector, shares_outstanding}
    equity_curve = []
    trades = []
    total_asset = INITIAL_CAPITAL

    for idx, day in enumerate(stats):
        date = day["date"]
        ms = market_score(day)
        level = get_level(ms)
        top_sec_name = day.get("s1Name", "")
        top_sec_new = day.get("s1New", 0)

        # ── 更新持仓市价 ──
        for code in list(positions.keys()):
            pos = positions[code]
            price = sim_price(code, idx, 50)
            pos["current_price"] = price
            if price > pos["peak"]: pos["peak"] = price

        # ── 卖出检查 ──
        for code in list(positions.keys()):
            pos = positions[code]
            price = pos["current_price"]
            cost = pos["cost"]
            vol = pos["volume"]
            gain = (price - cost) / cost

            # 硬止损 -10%
            if gain <= -0.10:
                proceeds = price * vol
                cash += proceeds
                trades.append((date, code, "SELL(止损)", vol, price, gain))
                del positions[code]
                continue

            # 阶梯止盈
            if gain >= 0.25:
                half = max(vol // 2, 100)
                if half >= 100 and half < vol:
                    proceeds = price * half
                    cash += proceeds
                    pos["volume"] -= half
                    trades.append((date, code, f"SELL(TP3)", half, price, gain))
                    continue
            if gain >= 0.15:
                sell_vol = max(int(vol * 0.5), 100)
                if sell_vol >= 100 and sell_vol < vol:
                    proceeds = price * sell_vol
                    cash += proceeds
                    pos["volume"] -= sell_vol
                    trades.append((date, code, f"SELL(TP2)", sell_vol, price, gain))
                    continue
            if gain >= 0.08:
                sell_vol = max(int(vol * 0.33), 100)
                if sell_vol >= 100 and sell_vol < vol:
                    proceeds = price * sell_vol
                    cash += proceeds
                    pos["volume"] -= sell_vol
                    trades.append((date, code, f"SELL(TP1)", sell_vol, price, gain))
                    continue

            # 移动止盈
            if gain > 0:
                retreat = (pos["peak"] - price) / pos["peak"]
                if retreat >= 0.03:
                    proceeds = price * vol
                    cash += proceeds
                    trades.append((date, code, f"SELL(移动止盈)", vol, price, gain))
                    del positions[code]
                    continue

            # 时间止损（8日涨幅<2%）
            add_date = pos.get("add_date", date)
            held = (datetime.strptime(date, "%Y-%m-%d") - datetime.strptime(add_date, "%Y-%m-%d")).days
            if held >= 8 and gain < 0.02 and gain > -0.10:
                proceeds = price * vol
                cash += proceeds
                trades.append((date, code, f"SELL(时间止损{held}d)", vol, price, gain))
                del positions[code]
                continue

            # 板块轮动
            if top_sec_name and pos.get("sector", "") != top_sec_name:
                proceeds = price * vol
                cash += proceeds
                trades.append((date, code, f"SELL(轮动)", vol, price, gain))
                del positions[code]
                continue

        # ── 补仓检查（分批买入的剩余1/3） ──
        for code in list(positions.keys()):
            pos = positions[code]
            if not pos.get("dip_entry") or pos.get("batch_done"): continue
            nx = pos.get("batch_next", 0)
            if nx <= 0: continue
            price = pos["current_price"]
            if price > 0 and price <= nx:
                per = pos.get("batch_target", 0)
                vol = min(per, max(int(cash / price // 100 * 100), 100))
                if vol >= 100 and vol * price <= cash:
                    cash -= price * vol
                    pos["cost"] = (pos["cost"] * pos["volume"] + price * vol) / (pos["volume"] + vol)
                    pos["volume"] += vol
                    pos["batch_done"] = True
                    trades.append((date, code, f"BUY(补仓)", vol, price, 0))

        # ── 情绪过热减仓（涨停>120 + 连板>25） ──
        if day["limitUp"] >= 120 and day.get("chain", 0) >= 25:
            for code in list(positions.keys()):
                pos = positions[code]
                half = max(pos["volume"] // 2, 100)
                if 100 <= half < pos["volume"]:
                    price = pos["current_price"]
                    cash += price * half
                    pos["volume"] -= half
                    trades.append((date, code, f"SELL(情绪减半)", half, price, 0))

        # ── 买入 ──
        if level in ALLOW_LEVELS and top_sec_name and top_sec_new >= 5\
           and day["limitDown"] <= 20:
            stocks = SECTOR_DB.get(top_sec_name, [])
            if stocks:
                candidates = []
                for code in stocks:
                    if code in positions: continue
                    klines = [sim_price(code, max(0, idx - i - 20), 50) for i in range(30)]
                    klines = klines[::-1]
                    dip = check_dip(code, idx, klines)
                    if dip["score"] >= DIP_SCORE_THRESHOLD:
                        candidates.append((code, dip))
                candidates.sort(key=lambda x: -x[1]["score"])
                per_stock = total_asset * 0.25
                for code, dip in candidates[:TOP_N]:
                    price = dip["price"]
                    if price <= 0: continue
                    vol = max(int(per_stock * 0.67 / price // 100 * 100), 100)
                    if vol * price > cash:
                        vol = max(int(cash / price // 100 * 100), 100)
                    if vol < 100: continue
                    cash -= price * vol
                    positions[code] = {
                        "volume": vol, "cost": price, "peak": price,
                        "add_date": date, "sector": top_sec_name,
                        "dip_entry": True, "current_price": price,
                        "batch_target": max(int(per_stock * 0.33 / price // 100 * 100), 100),
                        "batch_next": round(price * 0.97, 2),
                        "batch_done": False,
                    }
                    trades.append((date, code, f"BUY(低吸)", vol, price, dip["score"]))

        # ── 权益曲线 ──
        pos_value = sum(p["current_price"] * p["volume"] for p in positions.values())
        total_asset = cash + pos_value
        equity_curve.append({"date": date, "asset": round(total_asset, 2),
                             "cash": round(cash, 2), "pos": round(pos_value, 2),
                             "level": level, "ms": ms,
                             "sector": top_sec_name, "positions": len(positions)})

    return equity_curve, trades


def print_report(curve, trades, stats):
    if not curve:
        print("无交易记录"); return
    start = INITIAL_CAPITAL
    end = curve[-1]["asset"]
    ret = (end - start) / start * 100
    days = len(curve)
    ann_ret = ret * 252 / max(days, 1)

    buy_trades = [t for t in trades if t[2].startswith("BUY")]
    sell_trades = [t for t in trades if t[2].startswith("SELL")]
    win_trades = [t for t in sell_trades if t[5] > 0]
    win_rate = len(win_trades) / max(len(sell_trades), 1) * 100

    peak = max(c["asset"] for c in curve)
    max_dd = max((peak - c["asset"]) / peak * 100 for c in curve) if peak > 0 else 0

    avg_gain = sum(t[5] * 100 for t in sell_trades) / max(len(sell_trades), 1)

    print("=" * 60)
    print("  波段信号策略回测报告")
    print(f"  回测区间: {curve[0]['date']} ~ {curve[-1]['date']} ({days}个交易日)")
    print("=" * 60)
    print(f"  初始资金: {INITIAL_CAPITAL:>10,.0f}")
    print(f"  最终权益: {end:>12,.0f}")
    print(f"  总收益率: {ret:>+8.2f}%")
    print(f"  年化收益: {ann_ret:>+8.2f}%")
    print(f"  最大回撤: {max_dd:>8.2f}%")
    print(f"  交易次数: {len(buy_trades)} 买入 / {len(sell_trades)} 卖出")
    print(f"  胜率:     {win_rate:>8.1f}%")
    print(f"  平均盈亏: {avg_gain:>+8.2f}%")
    print("=" * 60)
    print()

    print("--- 等级分布 ---")
    level_count = defaultdict(int)
    for c in curve:
        level_count[c["level"]] += 1
    for lv in ["S", "A", "B", "C", "D"]:
        n = level_count.get(lv, 0)
        if n:
            print(f"  {lv}级: {n}天 ({n/max(len(curve),1)*100:.1f}%)")

    if sell_trades:
        print("\n--- 卖出盈亏损益分布 ---")
        bins = [(-100, -10), (-10, -5), (-5, -2), (-2, 0), (0, 2), (2, 5), (5, 10), (10, 50)]
        for lo, hi in bins:
            n = sum(1 for t in sell_trades if lo <= t[5] * 100 < hi)
            if n:
                bar = "█" * n
                print(f"  {lo:>+5}% ~ {hi:>+4}%: {n}笔 {bar}")

    print("\n--- 最终持仓 ---")
    pos_hold = [t for t in trades if t[2].startswith("BUY")]
    sold_codes = set(t[1] for t in sell_trades)
    hold_codes = set(t[1] for t in pos_hold) - sold_codes
    if hold_codes:
        for code in hold_codes:
            last_trade = [t for t in pos_hold if t[1] == code]
            if last_trade:
                print(f"  {code}: 持有中 ({last_trade[-1][3]}股)")
    else:
        print("  (空仓)")

    print("\n--- 月度收益 ---")
    monthly = defaultdict(float)
    for c in curve:
        if c["date"][:7] >= "2026-01":
            month = c["date"][:7]
            monthly[month] = c["asset"]
    prev_val = INITIAL_CAPITAL
    for m in sorted(monthly.keys()):
        val = monthly[m]
        mret = (val - prev_val) / prev_val * 100
        print(f"  {m}: {mret:>+6.2f}% (权益{val:>10,.0f})")
        prev_val = val


if __name__ == "__main__":
    print("加载数据...")
    stats = load_stats(STATS_FILE)
    print(f"  共 {len(stats)} 条记录, {stats[0]['date']} ~ {stats[-1]['date']}")

    print("运行回测...")
    curve, trades = run_backtest(stats)

    print_report(curve, trades, stats)

    # 导出csv
    out = os.path.join(os.path.dirname(STATS_FILE), "回测结果.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "权益", "现金", "持仓市值", "等级", "评分", "板块", "持仓数"])
        for c in curve:
            w.writerow([c["date"], c["asset"], c["cash"], c["pos"],
                        c["level"], c["ms"], c["sector"], c["positions"]])
    print(f"\n详细数据已导出: {out}")
