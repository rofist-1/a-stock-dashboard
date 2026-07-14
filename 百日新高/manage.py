#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
百日新高智能跟踪系统
用法：
  python manage.py report    → 生成智能报表 Excel
  python manage.py show      → 终端查看汇总
"""
import json
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
EXCEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "百日新高_报表.xlsx")

# ── 颜色 ──
DARK_BG = "0f1923"
HEADER_BG = "243447"
ROW1 = "1a2736"
ROW2 = "162230"
RED = "ef5350"
GREEN = "4caf50"
ORANGE = "ffb74d"
DEEP_ORANGE = "ff6b35"
WHITE = "ffffff"
GRAY = "aaaaaa"
LIGHT_GRAY = "888888"
CYAN = "4fc3f7"
YELLOW = "ffeb3b"

fill_header = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid")
fill_row1 = PatternFill(start_color=ROW1, end_color=ROW1, fill_type="solid")
fill_row2 = PatternFill(start_color=ROW2, end_color=ROW2, fill_type="solid")
fill_hot2 = PatternFill(start_color="3e2723", end_color="3e2723", fill_type="solid")
fill_hot3 = PatternFill(start_color="4e342e", end_color="4e342e", fill_type="solid")
fill_hot4 = PatternFill(start_color="7f1d1d", end_color="7f1d1d", fill_type="solid")
fill_new = PatternFill(start_color="1b3a1b", end_color="1b3a1b", fill_type="solid")
fill_gold = PatternFill(start_color="4a3a00", end_color="4a3a00", fill_type="solid")

font_header = Font(name="Microsoft YaHei", size=11, bold=True, color=GRAY)
font_white = Font(name="Microsoft YaHei", size=11, color=WHITE)
font_red = Font(name="Microsoft YaHei", size=11, color=RED, bold=True)
font_green = Font(name="Microsoft YaHei", size=11, color=GREEN, bold=True)
font_link = Font(name="Microsoft YaHei", size=11, color=CYAN, underline="single", bold=True)
font_orange = Font(name="Microsoft YaHei", size=11, color=ORANGE, bold=True)
font_gray = Font(name="Microsoft YaHei", size=11, color=LIGHT_GRAY)
font_title = Font(name="Microsoft YaHei", size=16, bold=True, color=DEEP_ORANGE)
font_subtitle = Font(name="Microsoft YaHei", size=12, bold=True, color=ORANGE)
center = Alignment(horizontal="center", vertical="center")
left = Alignment(horizontal="left", vertical="center")


def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════
# 智能分析引擎
# ═══════════════════════════════════════

def parse_main_net(val):
    """解析主力净额字符串为数值（万元）"""
    if not val:
        return 0
    s = str(val).replace("+", "").replace(",", "")
    try:
        if "亿" in s:
            return float(s.replace("亿", "")) * 10000
        elif "万" in s:
            return float(s.replace("万", ""))
        else:
            return float(s) / 10000
    except:
        return 0


def parse_turnover(val):
    """解析成交额字符串为数值（万元）"""
    if not val:
        return 0
    s = str(val).replace("+", "").replace(",", "").replace("Z", "")
    try:
        if "亿" in s:
            return float(s.replace("亿", "")) * 10000
        elif "万" in s:
            return float(s.replace("万", ""))
        else:
            return float(s) / 10000
    except:
        return 0


def analyze(data):
    """全维度分析"""
    records = data["records"]
    dates = sorted(set(r["date"] for r in records))
    date_index = {d: i for i, d in enumerate(dates)}

    # 每只股票的跨日数据
    stock_days = defaultdict(list)  # code -> [{date, stock}]
    for r in records:
        for s in r["stocks"]:
            stock_days[s["code"]].append({"date": r["date"], "stock": s})

    results = {}
    for code, days in stock_days.items():
        days.sort(key=lambda d: d["date"])
        name = days[0]["stock"]["name"]
        latest = days[-1]["stock"]
        count = len(days)
        date_list = [d["date"] for d in days]

        # ── 连续交易日检测 ──
        consecutive_streak = 1
        max_consecutive = 1
        for i in range(1, len(date_list)):
            # 检查是否连续（间隔 ≤ 7 天视为同一连续段，因周末+假期）
            d1 = datetime.strptime(date_list[i - 1], "%Y-%m-%d")
            d2 = datetime.strptime(date_list[i], "%Y-%m-%d")
            if (d2 - d1).days <= 7:
                consecutive_streak += 1
                max_consecutive = max(max_consecutive, consecutive_streak)
            else:
                consecutive_streak = 1

        # ── 主力资金趋势 ──
        main_nets = [parse_main_net(d["stock"].get("mainNet", "")) for d in days]
        main_net_latest = parse_main_net(latest.get("mainNet", ""))
        main_net_total = sum(main_nets)
        main_trend = 0
        if len(main_nets) >= 2:
            recent_avg = sum(main_nets[-min(3, len(main_nets)):]) / min(3, len(main_nets))
            earlier_avg = sum(main_nets[:-min(3, len(main_nets))]) / max(1, len(main_nets) - min(3, len(main_nets)))
            main_trend = 1 if recent_avg > earlier_avg and recent_avg > 0 else (-1 if recent_avg < earlier_avg else 0)

        # ── 涨幅趋势 ──
        changes = [d["stock"]["changePct"] for d in days]
        avg_change = sum(changes) / len(changes)
        latest_change = latest.get("changePct", 0)
        prev_change = changes[-2] if len(changes) >= 2 else None

        # ── 成交额趋势 ──
        turnovers = [parse_turnover(d["stock"].get("turnover", "")) for d in days]
        latest_turnover = parse_turnover(latest.get("turnover", ""))

        # ── 信号判定（聚焦回调）──
        signals = []
        if count == 1:
            if latest_change < 2:
                signals.append("新入回调")
            else:
                signals.append("新入榜")

        if max_consecutive >= 3:
            signals.append(f"连续{max_consecutive}日")
        elif max_consecutive >= 2:
            signals.append(f"连续{max_consecutive}日")

        # 主力动态
        if main_trend > 0 and main_net_total > 5000:
            signals.append("主力加仓")
        elif main_trend < 0 and main_net_total < -5000:
            signals.append("主力减仓")

        # ═══ 回调相关信号 ═══
        pullback_signals = []

        # 1. 高量回调：今日下跌或微涨，但成交额大（放量滞涨/高位出货）
        if latest_change <= 1 and latest_turnover > 50000:
            pullback_signals.append("放量滞涨")
        elif latest_change < 0 and latest_turnover > 30000:
            pullback_signals.append("放量下跌")

        # 2. 涨幅收窄：多次上榜但涨幅递减
        if prev_change is not None and 0 <= latest_change < prev_change * 0.5 and prev_change > 3:
            pullback_signals.append("涨幅收窄")

        # 3. 高位整理：多次上榜 + 小涨小跌（±2%以内）+ 非首日
        if count >= 2 and -2 <= latest_change <= 2:
            pullback_signals.append("高位整理")

        # 4. 首日即回调：首日上榜但收跌或微涨
        if count == 1 and latest_change < 0:
            pullback_signals.append("首日回调")
        elif count == 1 and latest_change <= 1:
            pullback_signals.append("首日滞涨")

        # 合并回调信号
        signals.extend(pullback_signals)

        # 计算回调强度（用于排序优先级）
        pullback_score = 0
        if latest_change <= 0:
            pullback_score = abs(latest_change) * 10  # 跌幅越大越关注
        elif latest_change <= 2:
            pullback_score = (5 - latest_change) * 2  # 微涨也关注
        if count >= 2:
            pullback_score += count * 3  # 多次上榜更值得关注
        if main_trend > 0:
            pullback_score += 5  # 主力还在加仓的回调最好

        results[code] = {
            "name": name,
            "count": count,
            "dates": date_list,
            "max_consecutive": max_consecutive,
            "latest": latest,
            "sectors": list(set(d["stock"]["sector"] for d in days)),
            "main_net_total": main_net_total,
            "main_trend": main_trend,
            "avg_change": avg_change,
            "signals": signals,
            "pullback_score": pullback_score,
            "latest_change": latest_change,
            "prev_change": prev_change,
            "latest_turnover": latest_turnover,
        }

    # ── 板块分析 ──
    sector_by_date = {}  # date -> {sector -> count}
    for r in records:
        date_sectors = defaultdict(int)
        for s in r["stocks"]:
            for sec in s["sector"].split():
                date_sectors[sec] += 1
        sector_by_date[r["date"]] = dict(date_sectors)

    all_sectors = set()
    for d in sector_by_date.values():
        all_sectors.update(d.keys())

    # 板块趋势
    sector_trends = {}
    for sec in all_sectors:
        counts = []
        for d in dates:
            counts.append(sector_by_date.get(d, {}).get(sec, 0))
        total = sum(counts)
        if total >= 2:
            recent = sum(counts[-min(3, len(counts)):]) / min(3, len(counts))
            earlier = sum(counts[:-min(3, len(counts))]) / max(1, len(counts) - min(3, len(counts)))
            trend = "⬆升温" if recent > earlier else ("⬇降温" if recent < earlier else "➡持平")
        else:
            trend = "🆕新晋"
        sector_trends[sec] = {
            "total": total,
            "counts": counts,
            "trend": trend,
            "latest_count": counts[-1] if counts else 0,
        }

    return {
        "stocks": results,
        "sectors": sector_trends,
        "dates": dates,
        "all_sectors": sorted(all_sectors, key=lambda s: -sector_trends[s]["total"]),
    }


# ═══════════════════════════════════════
# Excel 生成
# ═══════════════════════════════════════

def write_title(ws, row, text, cols=12):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=cols)
    c = ws.cell(row=row, column=1, value=text)
    c.font = font_title
    c.alignment = center
    ws.row_dimensions[row].height = 36


def write_header(ws, row, headers):
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=col, value=h)
        c.font = font_header
        c.fill = fill_header
        c.alignment = center
    ws.row_dimensions[row].height = 28


def write_row(ws, row, values, fills=None, fonts=None):
    for col, val in enumerate(values, 1):
        c = ws.cell(row=row, column=col, value=val)
        c.font = fonts[col - 1] if fonts and col - 1 < len(fonts) else font_white
        c.fill = fills[col - 1] if fills and col - 1 < len(fills) else fill_row1
        c.alignment = center
    ws.row_dimensions[row].height = 26


def generate_excel():
    data = load_data()
    analysis = analyze(data)
    dates = analysis["dates"]
    stocks = analysis["stocks"]
    sectors = analysis["sectors"]

    # 排序：回调优先 > 连续上榜 > 主力流入
    def hot_score(item):
        code, info = item
        score = info.get("pullback_score", 0) * 5  # 回调强度
        score += info["count"] * 10 + info["max_consecutive"] * 5
        if info["main_trend"] > 0:
            score += 8
        return -score

    sorted_stocks = sorted(stocks.items(), key=hot_score)

    wb = Workbook()

    # ═══════════════ Sheet 1: 智能跟踪 ═══════════════
    ws1 = wb.active
    ws1.title = "智能跟踪"

    write_title(ws1, 1, f"百日新高 · 智能跟踪  ({dates[0]} ~ {dates[-1]})")

    # 统计卡片行
    total = len(stocks)
    multi2 = sum(1 for v in stocks.values() if v["count"] >= 2)
    multi3 = sum(1 for v in stocks.values() if v["count"] >= 3)
    pullback_count = sum(1 for v in stocks.values() if any(s in v["signals"] for s in ["放量下跌", "放量滞涨", "涨幅收窄", "高位整理", "首日回调", "首日滞涨"]))
    new_back = sum(1 for v in stocks.values() if v["count"] == 1 and v.get("latest_change", 999) <= 2)
    high_vol_drop = sum(1 for v in stocks.values() if "放量下跌" in v["signals"] or "放量滞涨" in v["signals"])

    ws1.merge_cells("A2:L2")
    stat = ws1.cell(row=2, column=1,
                    value=f"总{total}只 | 回调股:{pullback_count}只 | 高量异常:{high_vol_drop}只 | 新入回调:{new_back}只 | 覆盖{len(dates)}日")
    stat.font = font_gray
    stat.alignment = center
    ws1.row_dimensions[2].height = 22

    headers1 = ["回调信号", "股票名称", "代码", "上榜次数", "连续上榜", "出现日期", "最新价", "今日涨幅%",
                "板块", "成交额", "主力净额", "主力累计(万)"]
    write_header(ws1, 4, headers1)

    for i, (code, info) in enumerate(sorted_stocks):
        row = 5 + i
        cnt = info["count"]
        latest = info["latest"]
        is_odd = i % 2 == 0
        bg = fill_row1 if is_odd else fill_row2

        # 信号列
        sig_text = " ".join(info["signals"]) if info["signals"] else "-"

        # 连续标签
        cons = info["max_consecutive"]
        if cons >= 4:
            cons_str = f"💥{cons}日"
            cons_fill = fill_hot4
        elif cons >= 3:
            cons_str = f"🔥{cons}日"
            cons_fill = fill_hot3
        elif cons >= 2:
            cons_str = f"🔁{cons}日"
            cons_fill = fill_hot2
        else:
            cons_str = f"{cons}日"
            cons_fill = bg

        # 回调信号判定
        pullback_types = {"放量下跌", "放量滞涨", "涨幅收窄", "高位整理", "首日回调", "首日滞涨"}
        has_pullback = any(s in info["signals"] for s in pullback_types)
        has_danger = any(s in info["signals"] for s in ["放量下跌", "放量滞涨"])

        # 行背景：有回调信号的加底色
        if has_danger:
            row_fill = [PatternFill(start_color="2a1515", end_color="2a1515", fill_type="solid")] * len(headers1)
        elif has_pullback:
            row_fill = [PatternFill(start_color="1a2416", end_color="1a2416", fill_type="solid")] * len(headers1)
        elif cnt >= 4:
            row_fill = [PatternFill(start_color=ROW1, end_color="2a1010", fill_type="solid")] * len(headers1)
        elif cnt >= 3:
            row_fill = [fill_hot3 if c == 1 else bg for c in range(1, len(headers1) + 1)]
        elif cnt >= 2:
            row_fill = [fill_hot2 if c == 1 else bg for c in range(1, len(headers1) + 1)]
        else:
            row_fill = [bg] * len(headers1)

        values = [
            sig_text,
            info["name"],
            code,
            cnt,
            cons_str,
            "、".join(info["dates"]),
            latest.get("price", ""),
            latest.get("changePct", ""),
            "、".join(info["sectors"]),
            latest.get("turnover", ""),
            latest.get("mainNet", ""),
            f'{info["main_net_total"]:,.0f}' if info["main_net_total"] != 0 else "-",
        ]

        for col, val in enumerate(values, 1):
            c = ws1.cell(row=row, column=col, value=val)
            c.font = font_white
            c.fill = row_fill[col - 1] if isinstance(row_fill[0], PatternFill) else row_fill[0]
            c.alignment = center

        # 信号列颜色（按回调类型区分）
        sig_cell = ws1.cell(row=row, column=1)
        if has_danger:
            sig_cell.font = Font(name="Microsoft YaHei", size=10, color="ff4444", bold=True)
        elif has_pullback:
            sig_cell.font = Font(name="Microsoft YaHei", size=10, color="ffaa00", bold=True)
        else:
            sig_cell.font = Font(name="Microsoft YaHei", size=10, color=LIGHT_GRAY)
        sig_cell.alignment = left

        # 连续列
        cons_cell = ws1.cell(row=row, column=5)
        cons_cell.fill = cons_fill
        if cons >= 3:
            cons_cell.font = font_orange

        # 名称链接色
        ws1.cell(row=row, column=2).font = font_link

        # 涨幅颜色
        chg_cell = ws1.cell(row=row, column=8)
        chg_cell.font = font_red if latest.get("changePct", 0) >= 0 else font_green

        ws1.row_dimensions[row].height = 26

    ws1.freeze_panes = "A5"
    widths1 = [22, 14, 12, 10, 10, 26, 10, 10, 20, 14, 14, 14]
    for i, w in enumerate(widths1, 1):
        ws1.column_dimensions[get_column_letter(i)].width = w

    # ═══════════════ Sheet 2: 板块热度 ═══════════════
    ws2 = wb.create_sheet("板块热度")

    write_title(ws2, 1, "板块热度分析")
    sorted_sectors_items = sorted(sectors.items(), key=lambda x: (-x[1]["total"], x[0]))
    ws2.merge_cells("A2:J2")
    ws2.cell(row=2, column=1, value=f"板块总数: {len(sectors)} | 按累计上榜次数排序").font = font_gray
    ws2.cell(row=2, column=1).alignment = center

    headers2 = ["板块", "趋势", "累计次数", "最新日数量"] + dates
    write_header(ws2, 4, headers2)

    for i, (sec, info) in enumerate(sorted_sectors_items):
        row = 5 + i
        bg = fill_row1 if i % 2 == 0 else fill_row2

        values = [sec, info["trend"], info["total"], info["latest_count"]] + info["counts"]
        fonts_list = [font_white] * len(values)
        fonts_list[1] = font_orange if "升温" in info["trend"] else (font_green if "降温" in info["trend"] else font_gray)

        for col, val in enumerate(values, 1):
            c = ws2.cell(row=row, column=col, value=val)
            c.font = fonts_list[col - 1] if col - 1 < len(fonts_list) else font_white
            c.fill = bg
            c.alignment = center

        ws2.row_dimensions[row].height = 24

    ws2.freeze_panes = "E5"
    widths2 = [18, 10, 10, 12] + [12] * len(dates)
    for i, w in enumerate(widths2, 1):
        ws2.column_dimensions[get_column_letter(i)].width = min(w, 16)

    # ═══════════════ Sheet 3: 连续上榜 ═══════════════
    ws3 = wb.create_sheet("连续上榜")

    write_title(ws3, 1, "连续上榜 · 重点跟踪")
    consecutive = [(code, info) for code, info in sorted_stocks if info["max_consecutive"] >= 2]
    consecutive.sort(key=lambda x: -x[1]["max_consecutive"])

    headers3 = ["连续天数", "股票名称", "代码", "累计次数", "出现日期", "最新涨幅%", "板块", "信号"]
    write_header(ws3, 3, headers3)

    for i, (code, info) in enumerate(consecutive):
        row = 4 + i
        bg = fill_row1 if i % 2 == 0 else fill_row2
        cons = info["max_consecutive"]

        values = [
            f"{cons}天",
            info["name"],
            code,
            info["count"],
            "→".join(info["dates"][-cons:]),
            info["latest"]["changePct"],
            "、".join(info["sectors"]),
            " ".join(info["signals"]),
        ]

        for col, val in enumerate(values, 1):
            c = ws3.cell(row=row, column=col, value=val)
            c.font = font_white if col < 5 else (font_orange if col in [1, 8] else font_white)
            c.fill = fill_hot3 if cons >= 3 else (fill_hot2 if cons >= 2 else bg)
            c.alignment = center

        ws3.cell(row=row, column=2).font = font_link
        chg_c = ws3.cell(row=row, column=6)
        chg_c.font = font_red if info["latest"]["changePct"] >= 0 else font_green
        ws3.row_dimensions[row].height = 26

    if not consecutive:
        ws3.merge_cells("A4:H4")
        ws3.cell(row=4, column=1, value="(暂无连续上榜股票，需积累更多交易日数据)").font = font_gray
        ws3.cell(row=4, column=1).alignment = center

    ws3.freeze_panes = "A4"
    widths3 = [10, 14, 12, 10, 30, 10, 22, 24]
    for i, w in enumerate(widths3, 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    # ═══════════════ Sheet 4: 回调关注 ═══════════════
    ws_cb = wb.create_sheet("回调关注")

    write_title(ws_cb, 1, "回调关注 · 低吸候选")
    pullback_stocks = [
        (code, info) for code, info in sorted_stocks
        if any(s in info["signals"] for s in ["放量下跌", "放量滞涨", "涨幅收窄", "高位整理", "首日回调", "首日滞涨"])
    ]
    pullback_stocks.sort(key=lambda x: -x[1].get("pullback_score", 0))

    ws_cb.merge_cells("A2:J2")
    ws_cb.cell(row=2, column=1,
               value=f"回调股: {pullback_count}只 | 放量异常: {sum(1 for _, i in pullback_stocks if any(s in i['signals'] for s in ['放量下跌','放量滞涨']))}只 | 首日回调/滞涨: {sum(1 for _, i in pullback_stocks if any(s in i['signals'] for s in ['首日回调','首日滞涨']))}只").font = font_gray
    ws_cb.cell(row=2, column=1).alignment = center

    headers_cb = ["回调类型", "股票名称", "代码", "上榜次数", "今日涨幅%", "板块", "成交额", "主力净额", "主力趋势", "信号详情"]
    write_header(ws_cb, 4, headers_cb)

    for i, (code, info) in enumerate(pullback_stocks):
        row = 5 + i
        bg = fill_row1 if i % 2 == 0 else fill_row2
        latest = info["latest"]

        # 回调类型标签
        cb_tags = [s for s in info["signals"] if s in ["放量下跌", "放量滞涨", "涨幅收窄", "高位整理", "首日回调", "首日滞涨"]]
        cb_main = cb_tags[0] if cb_tags else "回调"
        is_danger = cb_main in ["放量下跌", "放量滞涨"]

        sig_text = " ".join(info["signals"])
        main_trend_label = "主力加仓" if info["main_trend"] > 0 else ("主力减仓" if info["main_trend"] < 0 else "持平")

        values = [
            cb_main,
            info["name"],
            code,
            info["count"],
            latest.get("changePct", 0),
            "、".join(info["sectors"]),
            latest.get("turnover", ""),
            latest.get("mainNet", ""),
            main_trend_label,
            sig_text,
        ]

        for col, val in enumerate(values, 1):
            c = ws_cb.cell(row=row, column=col, value=val)
            c.font = font_white
            c.fill = PatternFill(start_color="2a1515", end_color="2a1515", fill_type="solid") if is_danger else bg
            c.alignment = center

        # 回调类型颜色
        type_cell = ws_cb.cell(row=row, column=1)
        type_cell.font = Font(name="Microsoft YaHei", size=11, color="ff4444" if is_danger else "ffaa00", bold=True)

        # 名称
        ws_cb.cell(row=row, column=2).font = font_link

        # 涨幅
        chg_c = ws_cb.cell(row=row, column=5)
        chg_c.font = font_red if latest.get("changePct", 0) >= 0 else font_green

        # 主力趋势
        trend_c = ws_cb.cell(row=row, column=9)
        trend_c.font = font_red if "加仓" in main_trend_label else (font_green if "减仓" in main_trend_label else font_gray)

        ws_cb.row_dimensions[row].height = 26

    if not pullback_stocks:
        ws_cb.merge_cells("A4:J4")
        ws_cb.cell(row=4, column=1, value="(暂无回调股票，所有股票均为强势上涨)").font = font_gray
        ws_cb.cell(row=4, column=1).alignment = center

    ws_cb.freeze_panes = "A5"
    widths_cb = [12, 14, 12, 10, 10, 22, 14, 14, 10, 28]
    for i, w in enumerate(widths_cb, 1):
        ws_cb.column_dimensions[get_column_letter(i)].width = w

    # ═══════════════ Sheet 5: 每日明细 ═══════════════
    ws4 = wb.create_sheet("每日明细")
    write_title(ws4, 1, "每日原始数据")
    headers4 = ["日期", "股票名称", "代码", "价格", "涨幅%", "板块", "成交额", "主力净额", "第N次上榜"]
    write_header(ws4, 3, headers4)

    # 预计算每个代码的累计出现次数
    code_count = {}
    row = 4
    for record in data["records"]:
        date = record["date"]
        for stock in record["stocks"]:
            code = stock["code"]
            code_count[code] = code_count.get(code, 0) + 1
            nth = code_count[code]
            bg = fill_row1 if row % 2 == 0 else fill_row2

            values = [date, stock["name"], code, stock["price"], stock["changePct"], stock["sector"],
                      stock["turnover"], stock["mainNet"], nth]
            for col, val in enumerate(values, 1):
                c = ws4.cell(row=row, column=col, value=val)
                c.font = font_white
                c.fill = bg
                c.alignment = center
                if col == 2:
                    c.font = font_link
                if col == 5:
                    c.font = font_red if stock["changePct"] >= 0 else font_green
                if col == 9 and nth >= 2:
                    c.font = font_orange
                    c.fill = fill_hot2

            ws4.row_dimensions[row].height = 24
            row += 1
        row += 1  # 日期分隔

    ws4.freeze_panes = "A4"
    widths4 = [14, 14, 12, 10, 10, 22, 14, 14, 12]
    for i, w in enumerate(widths4, 1):
        ws4.column_dimensions[get_column_letter(i)].width = w

    wb.save(EXCEL_FILE)
    print(f"[OK] Excel: {EXCEL_FILE}")
    print(f"   Sheet1 智能跟踪: {total}只 | 回调股{pullback_count}只(高量异常{high_vol_drop}) | 新入回调{new_back}")
    print(f"   Sheet2 板块热度: {len(sectors)}个板块")
    print(f"   Sheet3 连续上榜: {len(consecutive)}只连续股")
    print(f"   Sheet4 回调关注: {pullback_count}只")
    print(f"   Sheet5 每日明细: {sum(len(r['stocks']) for r in data['records'])}条记录")


def cmd_report():
    generate_excel()


def cmd_show():
    data = load_data()
    analysis = analyze(data)
    stocks = analysis["stocks"]

    print("\n=== 百日新高 · 智能汇总 ===")
    print(f"交易日: {len(analysis['dates'])}天")
    print(f"总个股: {len(stocks)}只")

    # 连续上榜
    cons = [(c, i) for c, i in stocks.items() if i["max_consecutive"] >= 2]
    if cons:
        cons.sort(key=lambda x: -x[1]["max_consecutive"])
        print("\n--- 连续上榜 ---")
        for code, info in cons[:15]:
            sigs = " ".join(s for s in info["signals"] if not any(c in s for c in "\U0001f300-\U0001f9ff"))
            print(f"  {info['max_consecutive']}日 | {info['name']}({code}) | {sigs}")

    # 主力加仓
    main_up = [(c, i) for c, i in stocks.items() if any("主力加仓" in s for s in i["signals"])]
    if main_up:
        main_up.sort(key=lambda x: -x[1]["main_net_total"])
        print("\n--- 主力持续加仓 ---")
        for code, info in main_up[:10]:
            sigs = " ".join(s for s in info["signals"] if not any(c in s for c in "\U0001f300-\U0001f9ff"))
            print(f"  {info['name']}({code}) | 累计主力净额:{info['main_net_total']:,.0f}万 | {sigs}")

    # 板块趋势
    sectors = analysis["sectors"]
    hot_sec = [(s, i) for s, i in sectors.items() if "温" in i["trend"] and i["total"] >= 2]
    if hot_sec:
        hot_sec.sort(key=lambda x: -x[1]["total"])
        print("\n--- 板块热度趋势 ---")
        for sec, info in hot_sec[:10]:
            trend = info["trend"]
            # strip emoji for console
            clean_trend = "".join(c for c in trend if ord(c) < 65536)
            print(f"  {clean_trend} {sec} | 累计{info['total']}次 | 今日{info['latest_count']}只")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "report":
        cmd_report()
    elif sys.argv[1] == "show":
        cmd_show()
    else:
        print(f"未知命令: {sys.argv[1]}")
