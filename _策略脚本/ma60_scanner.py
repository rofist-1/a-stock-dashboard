"""
涨停穿MA60 · 分歧转一致扫描
=============================
全A股扫描(baostock), QMT内用xtdata更快

用法:
  python ma60_scanner.py              # 全量扫描(慢)
  python ma60_scanner.py --limit 500  # 只扫前500只测试
  python ma60_scanner.py --code 600032  # 单只分析
"""

import sys, json, time
from datetime import datetime
import baostock as bs


def log(msg=""):
    print(msg)


def get_stocks():
    bs.login()
    rs = bs.query_all_stock(day="2026-06-03")
    stocks = []
    while rs.next():
        row = rs.get_row_data()
        code, name = row[0], row[1]
        raw = code.replace("sh.", "").replace("sz.", "")
        if raw.startswith("30") or raw.startswith("688") or raw.startswith("8") or raw.startswith("4"):
            continue
        if name and not name.replace(".", "").replace("-", "").isdigit():
            stocks.append({"code": code, "name": name, "raw": raw})
    bs.logout()
    return stocks


def kline(code, start, end):
    """获取K线数据(使用已登录的session)"""
    rs = bs.query_history_k_data_plus(
        code, "date,close,volume,pctChg",
        start_date=start, end_date=end, frequency="d", adjustflag="2"
    )
    data = []
    while rs.next():
        row = rs.get_row_data()
        if row[0]:
            try:
                data.append({
                    "d": row[0], "c": float(row[1]),
                    "v": float(row[2]) if row[2] else 0,
                    "p": float(row[3]) if row[3] else 0,
                })
            except:
                pass
    return data


def scan_single(code):
    """扫描单只股票 → 返回匹配结果或None"""
    recent = kline(code, "2026-05-26", "2026-06-03")
    if not any(k["p"] >= 9.0 for k in recent):
        return None

    full = kline(code, "2025-09-01", "2026-06-03")
    if len(full) < 60:
        return None

    n = len(full)
    close = [k["c"] for k in full]
    ma60 = [None] * 59
    for i in range(59, n):
        ma60.append(sum(close[i-59:i+1]) / 60)

    # 找最近5天内的涨停穿MA60
    for off in range(1, 6):
        idx = n - off
        if idx < 1 or ma60[idx] is None or ma60[idx-1] is None:
            continue
        k = full[idx]
        prev = full[idx-1]
        if k["p"] < 9.0 or not (prev["c"] < ma60[idx-1] and k["c"] > ma60[idx]):
            continue

        # 评分
        score = 50
        pts = []

        pre = full[max(0, idx-8):idx]
        near = sum(1 for p in pre if ma60[full.index(p)] and abs(p["c"] - ma60[full.index(p)]) / ma60[full.index(p)] < 0.04)
        wash = sum(1 for p in pre if p["p"] < -2)
        if near >= 2: score += 15; pts.append(f"前{near}次接近MA60")
        elif near >= 1: score += 8; pts.append("接近MA60")
        if wash >= 1: score += 10; pts.append(f"回调{wash}日洗盘")

        vr = k["v"] / max(prev["v"], 1)
        if vr > 2: score += 10; pts.append(f"放量{vr:.0f}倍")
        elif vr > 1.5: score += 5

        post = full[idx+1:]
        if post:
            below = sum(1 for p in post if ma60[full.index(p)] and p["c"] < ma60[full.index(p)])
            if below == 0: score += 15; pts.append(f"站稳{len(post)}日")
            elif below <= 1: score += 8

        cur = full[-1]
        dist = (cur["c"] / ma60[-1] - 1) * 100
        if 0 <= dist < 10: score += 10; pts.append(f"距MA60+{dist:.0f}%")
        elif dist < 20: score += 5

        if k["p"] >= 9.5: score += 5; pts.append("涨停")
        score = max(0, min(100, score))

        gain = (cur["c"] / k["c"] - 1) * 100 if score >= 60 else 0
        return {
            "break_date": k["d"], "score": score,
            "price": cur["c"], "gain": gain,
            "detail": " | ".join(pts),
        } if score >= 60 else None
    return None


def analyze_stock(code_raw, name=""):
    """分析单只股票并打印详情"""
    code = ("sh." if code_raw.startswith("6") else "sz.") + code_raw
    print(f"\n{'='*60}")
    print(f"  分析: {code_raw} {name}")
    print(f"{'='*60}")
    
    full = kline(code, "2025-09-01", "2026-06-03")
    if len(full) < 60:
        print("  数据不足")
        return

    n = len(full)
    close = [k["c"] for k in full]
    ma60 = [None] * 59
    for i in range(59, n):
        ma60.append(sum(close[i-59:i+1]) / 60)

    print(f"\n{'日期':<12} {'收盘':>7} {'涨跌':>7} {'MA60':>8} {'距MA60':>7} {'标记':<12}")
    print(f"{'-'*55}")
    for i in range(max(0, n-30), n):
        k = full[i]
        m = ma60[i]
        zt = "★涨停" if k["p"] >= 9.0 else ""
        cross = ""
        if i > 0 and ma60[i] and ma60[i-1] and k["p"] >= 9.0 and full[i-1]["c"] < ma60[i-1] and k["c"] > ma60[i]:
            cross = "↑穿MA60"
        d = (k["c"] / m - 1) * 100 if m else 0
        print(f"{k['d']:<12} {k['c']:>7.2f} {k['p']:>+6.2f}% {m:>8.2f} {d:>+6.1f}% {zt:<8}{cross:<8}")


def run(limit=0):
    """全市场扫描"""
    log("=" * 60)
    log("  涨停穿MA60 · 分歧转一致扫描")
    log("=" * 60)

    bs.login()
    stocks = get_stocks()
    total = len(stocks)
    if limit > 0:
        stocks = stocks[:limit]
    log(f"  扫描 {len(stocks)}/{total} 只标的\n")

    results = []
    t0 = time.time()
    for i, s in enumerate(stocks):
        code = s["code"]
        if (i+1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i+1) / elapsed if elapsed > 0 else 0
            remain = (len(stocks) - i - 1) / max(rate, 1)
            log(f"  进度 {i+1}/{len(stocks)} 发现{len(results)}只 [{rate:.1f}只/秒 剩余{remain:.0f}秒]")

        r = scan_single(code)
        if r:
            r["raw"] = s["raw"]
            r["name"] = s["name"]
            results.append(r)
            log(f"\n  ✓ {s['raw']} {s['name']} ({r['score']}分) {r['detail']}")

    bs.logout()
    results.sort(key=lambda x: -x["score"])

    elapsed = time.time() - t0
    log(f"\n\n{'='*60}")
    log(f"  扫描完成: {len(results)}只 | 耗时{elapsed:.0f}秒")
    log(f"{'='*60}")

    if results:
        log(f"\n{'代码':<8} {'名称':<8} {'评分':<6} {'突破日':<12} {'涨幅':<8} {'特征'}")
        log(f"{'-'*60}")
        for r in results[:20]:
            log(f"{r['raw']:<8} {r['name']:<8} {r['score']:<6} {r['break_date']:<12} {r['gain']:<+7.1f}% {r['detail']}")

        # 保存
        out = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "results": results}
        with open("ma60_scan_result.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        log(f"\n  已保存: ma60_scan_result.json")
    else:
        log(f"\n  暂无符合条件的标的")

    return results


if __name__ == "__main__":
    # 参数解析
    limit = 0
    single = ""
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i+1 < len(sys.argv):
            limit = int(sys.argv[i+1])
        if a == "--code" and i+1 < len(sys.argv):
            single = sys.argv[i+1]

    if single:
        name = ""
        try:
            with open("ma60_scan_result.json", "r") as f:
                data = json.load(f)
                for r in data.get("results", []):
                    if r["raw"] == single:
                        name = r["name"]
                        break
        except:
            pass
        analyze_stock(single, name)
    else:
        run(limit=limit)
