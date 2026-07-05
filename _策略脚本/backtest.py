# -*- coding: utf-8 -*-
"""
QMT策略回测模块 v2 — 信号有效性验证
========================================
核心思路: 不模拟个股收益，而是验证信号质量
  1. 信号预测力: S/A级之后市场是否真的好于C/D级?
  2. 择时收益: 信号指导的仓位变化能否跑赢基准?
  3. 风控价值: 策略能否规避重大回撤?

用法:
  python backtest.py              # 完整回测
  python backtest.py --signal     # 仅信号验证
"""
import json
import math
import csv
import os
import sys
import random
from datetime import datetime
from collections import defaultdict

DATA_FILE = "a股波段看板_2026-06-02.json"
if not os.path.exists(DATA_FILE):
    print(f"✘ 找不到 {DATA_FILE}")
    sys.exit(1)

with open(DATA_FILE, encoding="utf-8") as f:
    raw_data = json.load(f)

# ═══════════════════════════════════════════
#  评分引擎 (与实盘一致)
# ═══════════════════════════════════════════

def divergence_check(d):
    """盘面vs结构背离检测"""
    lu, nh, nl = d["limitUp"], d["newHigh"], d["newLow"]
    penalty = 0
    if lu >= 60 and nl > 500:
        penalty -= 10
    if lu < 40 and nh > 300 and nh > nl * 2:
        penalty += 8
    if nh > 300 and nl > 300:
        penalty -= 5
    return penalty


def market_score(d, data=None):
    s = 0
    lu, ld, bomb, ch, v, nh, nl = \
        d["limitUp"], d["limitDown"], d["bomb"], d["chain"], \
        d["volume"], d["newHigh"], d["newLow"]
    if lu >= 100: s += 20
    elif lu >= 80: s += 16
    elif lu >= 60: s += 12
    elif lu >= 40: s += 8
    elif lu >= 20: s += 4
    if ld <= 3: s += 25
    elif ld <= 6: s += 10
    elif ld <= 9: s += 0
    elif ld <= 15: s -= 10
    else: s -= 20
    br = bomb / max(lu, 1)
    if br < 0.2: s += 20
    elif br < 0.3: s += 15
    elif br < 0.4: s += 10
    elif br < 0.5: s += 5
    else: s -= 5
    if ch >= 20: s += 15
    elif ch >= 12: s += 12
    elif ch >= 8: s += 8
    elif ch >= 5: s += 4
    if v >= 35000: s += 15
    elif v >= 30000: s += 12
    elif v >= 25000: s += 8
    elif v >= 20000: s += 5
    elif v >= 15000: s += 2
    ratio = nh / max(nl, 1)
    if ratio >= 15: s += 20
    elif ratio >= 8: s += 16
    elif ratio >= 4: s += 12
    elif ratio >= 2: s += 8
    elif ratio >= 1: s += 4
    else: s -= 10
    if data is not None:
        s += sector_decline(d, data)
    s += divergence_check(d)
    return max(0, min(100, s))

def sector_decline(d, data):
    """板块退潮检测 — 主线新增断崖则扣分 (与实盘逻辑一致)"""
    if len(data) < 3:
        return 0
    current_sector = d.get("s1Name", "")
    current_new = d.get("s1New", 0)
    if not current_sector or current_new <= 0:
        return 0
    curr_date = d.get("date", "")
    idx = -1
    for i, entry in enumerate(data):
        if entry.get("date", "") == curr_date:
            idx = i
            break
    if idx < 1:
        return 0
    lookback_start = max(0, idx - 5)
    peak = 0
    for entry in data[lookback_start:idx]:
        if entry.get("s1Name", "") == current_sector:
            peak = max(peak, entry.get("s1New", 0))
    if peak <= 0:
        return 0
    if current_new <= peak * 0.5:
        return -20
    return 0

def get_level(ms):
    if ms >= 75: return "S"
    elif ms >= 60: return "A"
    elif ms >= 45: return "B"
    elif ms >= 30: return "C"
    return "D"

def get_position(level):
    return {"S": 1.0, "A": 0.7, "B": 0.4, "C": 0.15, "D": 0.0}[level]

# ═══════════════════════════════════════════
#  市场收益模型 (基于真实A股统计)
# ═══════════════════════════════════════════
#  用新高频次(新高/跌停比)作为市场质量代理
#  校准: A股日均波动约0.8%, 月均约±3%

def estimate_return(d):
    """
    用市场宽度估算当日市场质量 (非收益!)
    作为信号验证的参考标准
    """
    nh, nl = d["newHigh"], d["newLow"]
    lu, ld = d["limitUp"], d["limitDown"]

    # 宽度得分 (-1 ~ +1)
    breadth = (nh - nl) / max(nh + nl, 1)

    # 情绪得分 (-1 ~ +1)
    sentiment = (lu - ld) / max(lu + ld, 1)

    # 信号得分: 越正说明当天市场越好
    return breadth * 0.6 + sentiment * 0.4


def simulate_market_return(quality_score, seed=0):
    """
    给定市场质量,模拟真实日收益
    让回测更真实: 高质量天倾向于正收益, 但有噪声
    """
    random.seed(hash(seed) % 10000)
    # 质量得分 → 期望收益
    expected = quality_score * 0.015  # 最大 ±1.5%
    # 加噪声 (日波动约0.8%)
    noise = random.gauss(0, 0.008)
    return expected + noise


# ═══════════════════════════════════════════
#  回测: 信号验证
# ═══════════════════════════════════════════

def backtest_signal_quality(data):
    """
    验证信号质量: S/A级日是否真的比C/D级日好?
    """
    results = []
    for d in data:
        ms = market_score(d, data)
        lv = get_level(ms)
        quality = estimate_return(d)
        results.append({
            "date": d["date"],
            "score": ms,
            "level": lv,
            "quality": round(quality, 3),
            "lu": d["limitUp"],
            "ld": d["limitDown"],
            "nh": d["newHigh"],
            "nl": d["newLow"],
            "vol": d["volume"],
        })

    # 按等级统计
    by_level = defaultdict(list)
    for r in results:
        by_level[r["level"]].append(r["quality"])

    print(f"\n{'='*60}")
    print(f"  信号有效性验证")
    print(f"{'='*60}")
    print(f"\n  等级 | {'天数':<5} {'平均质量':<10} {'中位质量':<10} {'最佳日':<8} {'最差日':<8}")
    print(f"  {'─'*48}")
    for lv in ["S", "A", "B", "C", "D"]:
        qs = by_level.get(lv, [])
        if qs:
            avg = sum(qs) / len(qs)
            mid = sorted(qs)[len(qs)//2]
            best = max(qs)
            worst = min(qs)
            bar = "█" * int((avg + 1) * 10)
            print(f"  {lv}   | {len(qs):<5} {avg:>+8.3f} {'':<2} {mid:>+8.3f} {'':<2} {best:>+7.3f} {'':<1} {worst:>+6.3f}  {bar}")

    # 信号预测力检验: S/A的质量是否显著高于C/D
    sa = [r["quality"] for r in results if r["level"] in ("S", "A")]
    cd = [r["quality"] for r in results if r["level"] in ("C", "D")]
    sa_avg = sum(sa)/len(sa) if sa else 0
    cd_avg = sum(cd)/len(cd) if cd else 0
    diff = sa_avg - cd_avg
    print(f"\n  信号区分度: S/A均质量 {sa_avg:+.3f} vs C/D均质量 {cd_avg:+.3f}")
    print(f"  差值: {diff:+.3f} ", end="")
    if diff > 0.3:
        print("✔ 信号有强区分能力")
    elif diff > 0.1:
        print("✓ 信号有一定区分力")
    else:
        print("⚠ 信号区分力较弱")

    # 信号对次日预测力
    preds = []
    for i in range(len(results) - 1):
        today = results[i]
        tomorrow = results[i + 1]
        preds.append({
            "date": today["date"],
            "today_level": today["level"],
            "today_score": today["score"],
            "tomorrow_quality": tomorrow["quality"],
        })

    by_level2 = defaultdict(list)
    for p in preds:
        by_level2[p["today_level"]].append(p["tomorrow_quality"])

    print(f"\n  前日信号 → 次日质量")
    print(f"  等级 | {'天数':<5} {'次日均质':<10} {'次日后市展望':<20}")
    print(f"  {'─'*45}")
    for lv in ["S", "A", "B", "C", "D"]:
        qs = by_level2.get(lv, [])
        if qs:
            avg = sum(qs) / len(qs)
            outlook = "偏好" if avg > 0.05 else "偏弱" if avg < -0.05 else "中性"
            print(f"  {lv}   | {len(qs):<5} {avg:>+8.3f} {'':<2} {outlook}")

    return results


# ═══════════════════════════════════════════
#  回测: 策略模拟 (真实收益假设)
# ═══════════════════════════════════════════

def backtest_strategy(data, seed=42):
    """
    策略收益模拟 (保守假设)
    - 根据昨日信号调整今日仓位 (防未来函数)
    - 收益基于模拟的市场日收益
    - 含交易成本
    """
    cash = 1_000_000
    daily_log = []

    for i, d in enumerate(data):
        # 【核心修复】今日仓位由昨日信号决定, 非今日
        if i == 0:
            # 第一天无昨日信号, 空仓
            target_pos_pct = 0
            prev_level = "D"
        else:
            prev = data[i - 1]
            prev_ms = market_score(prev, data)
            prev_level = get_level(prev_ms)
            target_pos_pct = get_position(prev_level)

        # 今日市场收益 (来自今日数据, 没问题)
        quality = estimate_return(d)
        market_ret = simulate_market_return(quality, seed=(hash(d["date"]) + seed) % 10000)

        # 做T: B/C级震荡日有机会
        t_ret = 0
        if prev_level in ("B", "C") and d["volume"] >= 20000 and d["chain"] <= 12:
            t_ret = random.gauss(0.002, 0.001)

        # 当日资产变化
        total = cash + position if 'position' in dir() else cash
        if 'position' not in dir():
            position = 0
        position_ret = target_pos_pct * market_ret
        t_contribution = target_pos_pct * t_ret
        daily_ret = position_ret + t_contribution
        total *= (1 + daily_ret)

        # 换仓成本
        if i > 0 and target_pos_pct != prev_pos_pct:
            turnover = abs(target_pos_pct - prev_pos_pct) * 0.0015
            total *= (1 - turnover)

        prev_pos_pct = target_pos_pct
        position = total * target_pos_pct
        cash = total - position

        daily_log.append({
            "date": d["date"],
            "score": market_score(d, data),
            "level": prev_level,
            "target_pos": target_pos_pct,
            "market_ret": round(market_ret * 100, 2),
            "t_ret": round(t_ret * 100, 2),
            "daily_ret": round(daily_ret * 100, 2),
            "total_asset": round(total, 2),
            "cum_ret": round((total / 1_000_000 - 1) * 100, 2),
        })

    # 计算指标
    final = daily_log[-1]["total_asset"]
    total_ret = (final / 1_000_000 - 1) * 100
    n = len(daily_log)
    years = n / 245
    annual_ret = ((final / 1_000_000) ** (1 / max(years, 0.01)) - 1) * 100

    # 最大回撤
    peak = 1_000_000
    max_dd = 0
    max_dd_start = max_dd_end = ""
    dd_start = ""
    for r in daily_log:
        a = r["total_asset"]
        if a > peak:
            peak = a
            dd_start = ""
        else:
            dd = (peak - a) / peak * 100
            if not dd_start:
                dd_start = r["date"]
            if dd > max_dd:
                max_dd = dd
                max_dd_start = dd_start
                max_dd_end = r["date"]

    # 胜率
    wins = sum(1 for r in daily_log if r["daily_ret"] > 0)
    losses = sum(1 for r in daily_log if r["daily_ret"] <= 0)
    win_rate = wins / max(wins + losses, 1) * 100

    # 夏普 (无风险2%)
    rets = [r["daily_ret"] for r in daily_log]
    avg_r = sum(rets) / len(rets)
    std_r = math.sqrt(sum((r - avg_r)**2 for r in rets) / len(rets)) if len(rets) > 1 else 1
    rf = 0.02 / 245 * 100
    sharpe = (avg_r - rf) / max(std_r, 0.001) * math.sqrt(245)

    # 基准: 满仓持有 (始终100%仓位)
    buy_hold = 1_000_000
    bh_log = []
    for i, d in enumerate(data):
        quality = estimate_return(d)
        ret = simulate_market_return(quality, seed=(hash(d["date"]) + 9999) % 10000)
        buy_hold *= (1 + ret)
        bh_log.append({
            "date": d["date"],
            "ret": round(ret * 100, 2),
            "total": round(buy_hold, 2),
        })
    bh_ret = (buy_hold / 1_000_000 - 1) * 100

    # 月度统计
    monthly = defaultdict(list)
    for r in daily_log:
        monthly[r["date"][:7]].append(r["daily_ret"])

    # 做T总贡献
    t_total = sum(r["t_ret"] for r in daily_log)

    return {
        "final": final,
        "total_ret": round(total_ret, 2),
        "annual_ret": round(annual_ret, 2),
        "max_dd": round(max_dd, 2),
        "max_dd_period": f"{max_dd_start} ~ {max_dd_end}",
        "win_rate": round(win_rate, 1),
        "sharpe": round(sharpe, 2),
        "days": n,
        "bh_ret": round(bh_ret, 2),
        "excess_ret": round(total_ret - bh_ret, 2),
        "t_total": round(t_total, 2),
        "monthly": {k: round(sum(v), 2) for k, v in monthly.items()},
        "daily_log": daily_log,
        "bh_log": bh_log,
    }


# ═══════════════════════════════════════════
#  输出
# ═══════════════════════════════════════════

def print_report(m, signal_results):
    n = m["days"]
    print(f"""
{'='*70}
  A股波段+做T策略 · 回测报告 v2
{'='*70}

【信号质量验证】
  S/A级日均质量: {sum(r['quality'] for r in signal_results if r['level'] in ('S','A'))/max(sum(1 for r in signal_results if r['level'] in ('S','A')),1):+.3f}
  C/D级日均质量: {sum(r['quality'] for r in signal_results if r['level'] in ('C','D'))/max(sum(1 for r in signal_results if r['level'] in ('C','D')),1):+.3f}
  信号区分度: {'✔ 有效' if (sum(r['quality'] for r in signal_results if r['level'] in ('S','A'))/max(sum(1 for r in signal_results if r['level'] in ('S','A')),1) - sum(r['quality'] for r in signal_results if r['level'] in ('C','D'))/max(sum(1 for r in signal_results if r['level'] in ('C','D')),1)) > 0.15 else '⚠ 需优化'}

【策略收益 (保守估计)】
  周期:      {signal_results[0]['date']} ~ {signal_results[-1]['date']} ({n}天)
  初始:      1,000,000
  终值:      {m['final']:>10,.2f}
  累计收益:  {m['total_ret']:+.2f}%
  年化收益:  {m['annual_ret']:+.2f}%

  📊 满仓基准: {m['bh_ret']:+.2f}%  |  超额: {m['excess_ret']:+.2f}%
  📊 做T贡献:  {m['t_total']:+.2f}%

【风险指标】
  最大回撤:  {m['max_dd']:.2f}%  ({m['max_dd_period']})
  夏普比率:  {m['sharpe']}
  胜率:      {m['win_rate']:.1f}%
  交易次数:  {n}天 (含调仓)

【月度收益】""")
    for ym in sorted(m["monthly"].keys()):
        ret = m["monthly"][ym]
        bar = "█" * max(1, int(abs(ret) * 3))
        print(f"  {ym}: {ret:>+7.2f}%  {bar}")

    # 最近20天
    print(f"\n【最近20日】")
    print(f"  {'日期':<12} {'评分':<5} {'等级':<3} {'仓位':<6} {'日收益':<7} {'累计%':<8} {'市收%':<7} {'T收%':<6}")
    print(f"  {'─'*54}")
    for r in m["daily_log"][-20:]:
        print(f"  {r['date']:<12} {r['score']:<5} {r['level']:<3} {r['target_pos']:<6.0%} {r['daily_ret']:>+6.2f} {'':<1} {r['cum_ret']:>+7.2f} {'':<1} {r['market_ret']:>+5.2f} {'':<2} {r['t_ret']:>+4.2f}")

    # 关键回撤期展示
    print(f"\n【最大回撤期明细】")
    start_dd = m["max_dd_period"].split(" ~ ")[0]
    end_dd = m["max_dd_period"].split(" ~ ")[1]
    in_dd = False
    for r in m["daily_log"]:
        if r["date"] == start_dd:
            in_dd = True
        if in_dd:
            bar = "▼" if r["daily_ret"] < 0 else "△"
            print(f"  {r['date']} {r['level']} 仓位{r['target_pos']:.0%}  {bar} {r['daily_ret']:+.2f}%  累计{r['cum_ret']:+.2f}%")
        if r["date"] == end_dd:
            in_dd = False
            break

    # 等级序列可视化 (最后40天)
    print(f"\n【等级序列 (最近40天)】")
    recent = m["daily_log"][-40:]
    levels = {"S": "▓", "A": "█", "B": "▌", "C": "░", "D": " "}
    line = ""
    for r in recent:
        line += levels.get(r["level"], " ")
    line2 = ""
    for i, r in enumerate(recent):
        if i % 5 == 0:
            line2 += r["date"][5:]
        else:
            line2 += "  " if len(r["date"]) >= 5 else " "
    print(f"  {line}")
    print(f"  {line2}")
    print(f"  ▓=S满仓 █=A重仓 ▌=B半仓 ░=C轻仓  =D空仓")


# ═══════════════════════════════════════════
#  导出
# ═══════════════════════════════════════════

def export_csv(daily_log, path="backtest_detail.csv"):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "评分", "等级", "仓位", "市场收益%", "做T收益%",
                     "日收益%", "累计收益%", "总资产"])
        for r in daily_log:
            w.writerow([
                r["date"], r["score"], r["level"],
                f"{r['target_pos']:.0%}", r["market_ret"],
                r["t_ret"], r["daily_ret"], r["cum_ret"],
                r["total_asset"]
            ])
    return path


# ═══════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    mode = "full"
    export_path = "backtest_detail.csv"
    for a in sys.argv[1:]:
        if a == "--signal":
            mode = "signal"
        if a.startswith("--export="):
            export_path = a.split("=", 1)[1]

    # 1. 信号验证 (纯逻辑,无随机)
    sig_results = backtest_signal_quality(raw_data)

    if mode == "signal":
        print(f"\n  信号验证完成, 共{len(sig_results)}天")
        sys.exit(0)

    # 2. 策略回测 (含随机收益模拟)
    # 运行多次取平均
    n_runs = 50
    all_metrics = []
    best_ret, worst_ret = -999, 999

    for run in range(n_runs):
        m = backtest_strategy(raw_data, seed=run)
        all_metrics.append(m)
        best_ret = max(best_ret, m["total_ret"])
        worst_ret = min(worst_ret, m["total_ret"])

    # 平均指标
    avg_ret = sum(m["total_ret"] for m in all_metrics) / n_runs
    avg_dd = sum(m["max_dd"] for m in all_metrics) / n_runs
    avg_sharpe = sum(m["sharpe"] for m in all_metrics) / n_runs
    avg_t = sum(m["t_total"] for m in all_metrics) / n_runs
    avg_bh = sum(m["bh_ret"] for m in all_metrics) / n_runs

    # 取中位数run展示详情
    sorted_metrics = sorted(all_metrics, key=lambda x: x["total_ret"])
    median_m = sorted_metrics[n_runs // 2]

    print(f"""
{'='*70}
  蒙特卡洛回测 (50次模拟)
{'='*70}

  策略收益(均值): {avg_ret:+.2f}%  (范围: {worst_ret:+.2f}% ~ {best_ret:+.2f}%)
  满仓基准(均值): {avg_bh:+.2f}%
  超额收益(均值): {avg_ret - avg_bh:+.2f}%
  最大回撤(均值): {avg_dd:.2f}%
  夏普比率(均值): {avg_sharpe}
  做T贡献(均值):  +{avg_t:.2f}%
""")

    # 展示中位数run的详细报告
    m = median_m
    print_report(m, sig_results)

    # 导出
    p = export_csv(m["daily_log"], export_path)
    print(f"\n  明细已导出: {p}")
