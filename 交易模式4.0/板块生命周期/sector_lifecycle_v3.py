# -*- coding: utf-8 -*-
"""
板块生命周期分析模块 v3
新增：锚点日数据窗口检测 + 状态持久化累积
"""
import sys, json, re, os
sys.stdout.reconfigure(encoding='utf-8')

STATE_FILE = r"C:\Users\Rofis\Desktop\sector_lifecycle_state.json"

# ============================================================
# 原始数据
# ============================================================
raw_data = [
    ("2026-07-01", 34500, 149,
     "芯片(120,20↑) [存储+47, 第三代半导体+38] · 机器人(24,8↑) [外骨骼+2, AGV+1] · 医药(19,5↑) [创新药+14, CRO+8]",
     "算力(18,2↑) [液冷+14, 数据中心+5] · 通信(17,3↑) [CPO+7, 5G+6] · 化工(14,7↑) [氢氟酸+4, 制冷剂+4]"),
    ("2026-07-02", 34505, 91,
     "芯片(42,9↑) [存储+16, 光刻胶+14] · 机器人(17,3↑) [传感器+1, 灵巧手+1] · 医药(15,2↑) [创新药+12, 仿制药+4]",
     "化工(9,1↑) [制冷剂+5, 氟化工+5] · 光通信(8,4↑) [光模块+4, CPO+4] · 算力(6,0↑) [液冷+3, 数据中心+2]"),
    ("2026-07-03", 32053, 104,
     "机器人(28,15↑) [灵巧手+4, 宇树机器人+3] · 芯片(24,12↑) [存储+10, 先进封装+6] · 医药(20,6↑) [创新药+16, CRO+7]",
     "通信(10,5↑) [光模块+5, CPO+4] · 算力(10,4↑) [液冷+7, 数据中心+3] · 证券(6,1↑) [参控股基金+5]"),
    ("2026-07-06", 30991, 64,
     "芯片(26,13↑) [存储+11, 汽车芯片+9] · 机器人(16,3↑) [灵巧手+2, 宇树机器人+1] · 医药(11,3↑) [创新药+10, cro+3]",
     "算力(9,3↑) [液冷+8, 数据中心+4] · ST(6,3↑) · 证券(5,1↑) [参股基金+3]"),
    ("2026-07-07", 25881, 33,
     "芯片(17,7↑) [存储+7, 汽车芯片+6] · 机器人(10,5↑) [滚珠丝杆+1] · 算力(9,5↑) [液冷+8, 数据中心+3]",
     "通信(4,3↑) [交换机+2, 5G+2] · 医药(3,2↑) [创新药+4, CRO+2] · AI应用(3,2↑) [智能体+2, AI电商+1]"),
    ("2026-07-08", 25826, 46,
     "芯片(15,4↑) [汽车芯片+6, 存储+6] · 算力(9,4↑) [液冷+8, 数据中心+3] · 医药(4,2↑) [创新药+4, CRO+3]",
     "通信(4,1↑) [交换机+3, CPO+2] · 物理AI(3,2↑) [机器视觉+2] · ST板块(2,0↑)"),
    ("2026-07-09", 29137, 74,
     "芯片(26,12↑) [存储+12, 先进封装+9] · 算力(11,3↑) [液冷+9, 数据中心+4] · 医药(6,2↑) [创新药+6, cro+4]",
     "通信(5,0↑) [交换机+3, 5G+2] · 机器人(3,0↑) [宇树机器人+1] · 物理AI(3,0↑) [机器视觉+2]"),
    ("2026-07-10", 33885, 88,
     "商业航天(24,0↑) · 医药(9,0↑) · 机器人(8,0↑)",
     "医药(15,9↑) [创新药+14, CRO+9] · 芯片(12,7↑) [先进封装+7, 存储+6] · 算力(7,4↑) [液冷+7, 数据中心+4]"),
    ("2026-07-13", 28178, 27,
     "医药(11,1↑) [创新药+9, CRO+5] · 芯片(7,4↑) [存储+3, 汽车芯片+2] · 算力(5,2↑) [液冷+3, 服务器+2]",
     "通信(3,3↑) [CPO+2, 交换机+2] · 物理AI(2,0↑) [机器视觉+2] · 其他(9,6↑)"),
]

# ============================================================
# 解析
# ============================================================
def parse_sector_text(text):
    sectors = {}
    pattern = r'([^\s()·]+?)\((\d+)(?:,\d+↑?)?\)'
    matches = re.findall(pattern, text)
    for name, count in matches:
        name = name.strip()
        if name and name not in ('—', '✎', '✕'):
            sectors[name] = int(count)
    return sectors

daily_sectors = {}
for date, mkt_val, total_lu, left_text, right_text in raw_data:
    sectors = {}
    if left_text and left_text != '—':
        sectors.update(parse_sector_text(left_text))
    if right_text and right_text != '—':
        sectors.update(parse_sector_text(right_text))
    daily_sectors[date] = sectors

trade_dates = sorted(daily_sectors.keys())
today = trade_dates[-1]

CORE_SECTORS = ['芯片', '医药', '机器人', '算力', '通信', '商业航天', 'AI应用', '物理AI']

# ============================================================
# 状态持久化
# ============================================================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"history": {}, "confirmed_anchors": {}}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

state = load_state()

# 累积历史数据：把今日解析的 daily_sectors 注入 state["history"]
for d, sectors in daily_sectors.items():
    if d not in state["history"]:
        state["history"][d] = sectors

# ============================================================
# 锚点窗口检测
# ============================================================
def check_window_adequacy(sector, lu_by_date):
    """
    检测数据窗口是否足以确定锚点日。
    返回: (adequate: bool, reason: str)
    
    不足的情况：
    1. 第一个有数据的日期涨停数就 >= 10 → 锚点在窗口之前
    2. 数据天数不足，无法做5日温和判断
    """
    first_with_data = None
    for d, c in lu_by_date:
        if c > 0:
            first_with_data = (d, c)
            break
    
    if first_with_data is None:
        return False, "无任何涨停记录"
    
    first_date, first_count = first_with_data
    
    # 第一条记录就很高 → 行情可能早已启动
    if first_count >= 10:
        return False, "首个数据日涨停数已达{}家，锚点可能在窗口之前".format(first_count)
    
    # 数据天数足够做判断 (至少需要5天)
    nonzero_days = [(d, c) for d, c in lu_by_date if c > 0]
    if len(nonzero_days) < 3 and len(trade_dates) < 5:
        return False, "数据窗口不足5个交易日"
    
    return True, "数据窗口充足"


def determine_anchor_type_v3(sector, lu_by_date):
    """返回 (anchor_idx, anchor_date, anchor_type, anchor_count, anchor_confirmed)"""
    date_list = [d for d, c in lu_by_date]
    count_list = [c for d, c in lu_by_date]
    
    window_ok, window_reason = check_window_adequacy(sector, lu_by_date)
    
    # 找第一个涨停>=5的候选日
    candidates = [(i, d, c) for i, (d, c) in enumerate(lu_by_date) if c >= 5]
    
    if not candidates:
        # 萌芽型：没有任何一天>=5
        nonzero = [(i, d, c) for i, (d, c) in enumerate(lu_by_date) if c > 0]
        if nonzero:
            return nonzero[0][0], nonzero[0][1], "萌芽型", nonzero[0][2], window_ok
        return None, None, "萌芽型", 0, False
    
    # 选锚点
    anchor = None
    for i, d, c in candidates:
        if c >= 10:
            anchor_idx, anchor_date, anchor_count = i, d, c
            break
    if anchor is None:
        anchor_idx, anchor_date, anchor_count = candidates[0]
    
    post_5 = count_list[anchor_idx:anchor_idx+6]
    
    # === 游资型判定 ===
    if anchor_count >= 15:
        has_sharp_drop = False
        for j in range(1, len(post_5)):
            if post_5[j-1] > 0 and post_5[j] < post_5[j-1] * 0.5:
                has_sharp_drop = True
                break
        if has_sharp_drop:
            return anchor_idx, anchor_date, "游资型", anchor_count, window_ok
    
    # === 趋势型判定 ===
    if len(post_5) >= 2:
        first_half = post_5[:min(3, len(post_5))]
        second_half = post_5[min(3, len(post_5)):]
        if second_half:
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            if avg_second >= avg_first * 0.8:
                return anchor_idx, anchor_date, "趋势型", anchor_count, window_ok
    
    return anchor_idx, anchor_date, "趋势型", anchor_count, window_ok


def calibrate_lifecycle(anchor_type, trading_days, lu_by_date, anchor_confirmed):
    count_list = [c for d, c in lu_by_date]
    max_lu = max(count_list) if count_list else 0
    latest_lu = count_list[-1] if count_list else 0
    
    if anchor_type == "萌芽型":
        return "萌芽期", max_lu, latest_lu
    
    # 基础标签
    if anchor_type == "游资型":
        if trading_days < 8: base = "游资-初期"
        elif trading_days <= 15: base = "游资-中期"
        else: base = "游资-末期"
    else:
        if trading_days < 20: base = "趋势-初期"
        elif trading_days <= 40: base = "趋势-中期"
        else: base = "趋势-末期"
    
    drop_pct = (max_lu - latest_lu) / max_lu * 100 if max_lu > 0 else 0
    
    # 校准 (仅在锚点确认后生效)
    if anchor_confirmed:
        if "初期" in base and drop_pct > 70:
            base = base.replace("初期", "中期")
        if "中期" in base and drop_pct > 90 and max_lu >= 10:
            base = base.replace("中期", "末期")
    
    return base, max_lu, latest_lu


# ============================================================
# 分析
# ============================================================
print("=" * 115)
print("  板块生命周期分析 v3 — {}".format(today))
print("  状态文件: {}".format(STATE_FILE))
print("=" * 115)

results = []

for sector in sorted(CORE_SECTORS):
    lu_by_date = [(d, daily_sectors.get(d, {}).get(sector, 0)) for d in trade_dates]
    nonzero = [(d, c) for d, c in lu_by_date if c > 0]
    
    if not nonzero:
        results.append({"sector": sector, "anchor_date": None, "anchor_type": "—",
                        "trading_days": 0, "lifecycle": "—", "max_lu": 0, "latest_lu": 0,
                        "drop_pct": 0, "strategy": "—", "anchor_note": "", "confirmed": False})
        continue
    
    anchor_idx, anchor_date, anchor_type, anchor_count, anchor_confirmed = \
        determine_anchor_type_v3(sector, lu_by_date)
    
    if anchor_date is None:
        anchor_date = nonzero[0][0] if nonzero else trade_dates[0]
        anchor_type = "萌芽型"
        anchor_confirmed = False
    
    today_idx = len(trade_dates) - 1
    anchor_idx_actual = trade_dates.index(anchor_date) if anchor_date in trade_dates else 0
    trading_days = today_idx - anchor_idx_actual
    
    lifecycle, max_lu, latest_lu = calibrate_lifecycle(
        anchor_type, trading_days, lu_by_date, anchor_confirmed)
    
    drop_pct = round((max_lu - latest_lu) / max_lu * 100, 1) if max_lu > 0 else 0
    
    # 锚点日备注
    if not anchor_confirmed:
        anchor_note = "⚠ 锚点日待确认（数据窗口有限）"
    else:
        anchor_note = ""
    
    # 策略
    if "初期" in lifecycle:
        strategy = "🟢 优先参与"
    elif "中期" in lifecycle:
        strategy = "🟡 选择性参与"
    elif "末期" in lifecycle:
        strategy = "🔴 仅龙头回流"
    elif "萌芽" in lifecycle:
        strategy = "🟢 优先参与"
    else:
        strategy = "—"
    
    # 存储确认状态以便下次运行
    state["confirmed_anchors"][sector] = {
        "anchor_date": anchor_date,
        "anchor_type": anchor_type,
        "confirmed": anchor_confirmed,
        "last_check": today,
    }
    
    results.append({
        "sector": sector, "anchor_date": anchor_date, "anchor_type": anchor_type,
        "trading_days": trading_days, "lifecycle": lifecycle,
        "max_lu": max_lu, "latest_lu": latest_lu, "drop_pct": drop_pct,
        "strategy": strategy, "anchor_note": anchor_note, "confirmed": anchor_confirmed,
    })

save_state(state)

# ============================================================
# 输出
# ============================================================
stage_order = {"萌芽期": 0, "游资-初期": 1, "趋势-初期": 2, "趋势-中期": 3, "游资-中期": 4, "游资-末期": 5, "趋势-末期": 6, "—": 9}

print()
print(f"{'板块':<10} {'锚点日':<12} {'锚点状态':<22} {'类型':<6} {'运行天':<5} {'生命周期':<10} {'峰值':<5} {'最新':<5} {'回落%':<6} {'策略'}")
print("-" * 110)
for r in sorted(results, key=lambda x: (stage_order.get(x["lifecycle"], 9), -x["max_lu"])):
    anchor = r["anchor_date"] or "—"
    note = r["anchor_note"] or "✓ 已确认"
    print(f"{r['sector']:<10} {anchor:<12} {note:<22} {r['anchor_type']:<6} {r['trading_days']:<5} {r['lifecycle']:<10} {r['max_lu']:<5} {r['latest_lu']:<5} {r['drop_pct']:<5.0f}% {r['strategy']}")

# 简报插入格式
print()
print("=" * 115)
print("  每日简报「核心概念战场」插入格式")
print("=" * 115)
print()
print("{:<8} {:>4} {:>5}  {:<12} {:5}   {}".format("板块", "涨停", "涨跌", "生命周期", "锚点确认", "策略"))
print("-" * 60)
for r in sorted(results, key=lambda x: (stage_order.get(x["lifecycle"], 9), -x["max_lu"])):
    arrow = "+{}".format(r["drop_pct"]) if r["drop_pct"] > 0 else "—"
    confirm = "✓" if r["confirmed"] else "⚠"
    print("{:<8} {:>4} {:>5}  {:<12} {:5}   {}".format(
        r["sector"], r["latest_lu"], arrow, r["lifecycle"], confirm, r["strategy"]))

# 确认状态汇总
print()
print("=" * 115)
print("  锚点日确认状态")
print("=" * 115)
confirmed_list = [r for r in results if r["confirmed"]]
pending_list = [r for r in results if not r["confirmed"] and r["lifecycle"] != "—"]
print(f"  ✓ 已确认: {len(confirmed_list)} 个板块 — {', '.join(r['sector'] for r in confirmed_list)}")
print(f"  ⚠ 待确认: {len(pending_list)} 个板块")
for r in pending_list:
    print(f"    {r['sector']:<10} → 首个数据日涨停{r['max_lu']}家，实际锚点可能在数据窗口之前")
    print(f"               建议: 补充{r['anchor_date']}之前的历史数据，或继续累积3-5个交易日后自动确认")
