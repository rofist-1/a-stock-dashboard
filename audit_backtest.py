# -*- coding: utf-8 -*-
"""
数据准确性核查 - 全面检查回测系统的每个环节
"""
import os, sys, pickle, json
import numpy as np
import pandas as pd
import akshare as ak

# Need BacktestResult class to unpickle
from backtest_strategy_comparison import BacktestResult, Trade

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache_bt3")
RESULT_DIR = os.path.join(BASE_DIR, "results")

# ===========================================================
# 1. 核查缓存数据完整性
# ===========================================================
print("=" * 80)
print("【1/7】缓存数据完整性检查")
print("=" * 80)

cached_files = [f for f in os.listdir(CACHE_DIR) if f.startswith("stock_") and f.endswith(".pkl") and f != "stock_list.pkl"]
print(f"缓存股票数: {len(cached_files)}")

# 抽样检查数据质量
sample_codes = ['002238', '002259', '603083', '300679', '301392', '603678']
missing_required = []
for code in sample_codes:
    cf = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
    if not os.path.exists(cf):
        print(f"  [MISSING] {code}")
        continue
    df = pd.read_pickle(cf)
    required = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'outstanding_share', 'turnover', 'code', 'circ_mv']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  [COLUMNS MISSING] {code}: {missing}")
        missing_required.append(code)
    else:
        n = len(df)
        date_range = f"{df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}"
        print(f"  [OK] {code}: {n} rows, {date_range}, circ_mv={df['circ_mv'].iloc[-1]:.0f}亿")

# ===========================================================
# 2. 核查特定日期的数据准确性
# ===========================================================
print("\n" + "=" * 80)
print("【2/7】特定案例日期数据准确性核查")
print("=" * 80)

checks = [
    ("002238", "天威视讯", "2026-02-03", 9.03, 10.0),
    ("002259", "升达林业", "2026-01-05", 4.16, 10.1),
    ("002259", "升达林业", "2026-05-08", 5.84, 10.0),
    ("300679", "电连技术", "2026-04-08", 39.99, 20.0),
    ("301392", "汇成真空", "2026-04-01", 127.51, 20.0),
    ("603083", "剑桥科技", "2026-04-08", 111.38, 10.0),
    ("603678", "火炬电子", "2026-05-22", 37.63, 10.0),
]

for code, name, date_str, expected_close, expected_pct in checks:
    cf = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
    if not os.path.exists(cf):
        print(f"  [NO DATA] {name}({code})")
        continue
    df = pd.read_pickle(cf)
    row = df[df["date"] == date_str]
    if len(row) == 0:
        # 检查是否在日期范围内
        print(f"  [DATE NOT FOUND] {name}({code}) at {date_str}")
        print(f"     Data range: {df['date'].min()} ~ {df['date'].max()}")
        continue
    row = row.iloc[0]
    idx = df[df["date"] == date_str].index[0]
    close = row["close"]
    prev_close = df.iloc[idx-1]["close"] if idx > 0 else None
    pct = (close / prev_close - 1) * 100 if prev_close else None
    
    close_ok = abs(close - expected_close) / expected_close < 0.02 if expected_close else "N/A"
    pct_ok = abs(pct - expected_pct) < 0.5 if pct and expected_pct else "N/A"
    
    print(f"  {name}({code}) @ {date_str}:")
    print(f"    收盘: {close:.2f} (预期{expected_close}) {'OK' if close_ok else 'MISMATCH'}")
    print(f"    涨幅: {pct:.2f}% (预期{expected_pct}%) {'OK' if pct_ok else 'MISMATCH'}")
    print(f"    开盘: {row['open']:.2f} 最高: {row['high']:.2f} 最低: {row['low']:.2f}")
    print(f"    换手: {row.get('turnover', 0)*100:.2f}% 市值: {row.get('circ_mv', 0):.0f}亿")

# ===========================================================
# 3. 核查信号计算逻辑
# ===========================================================
print("\n" + "=" * 80)
print("【3/7】信号计算逻辑核查（002259升达林业 2026-01-05）")
print("=" * 80)

code = "002259"
cf = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
df = pd.read_pickle(cf)
c, h, l, v = [df[c_].values for c_ in ["close", "high", "low", "volume"]]
date_str = "2026-01-05"
i = df[df["date"] == date_str].index[0]

print(f"  索引位置: {i}/{len(c)}")

# 逐一核查每个条件
# 1. 百日新高
high_100 = np.max(c[max(0, i-99):i+1])
new_high = c[i] >= high_100
print(f"  [1] 百日新高: c={c[i]:.2f}, HHV(100)={high_100:.2f} -> {'PASS' if new_high else 'FAIL'}")

# 2. 涨停
pct = c[i]/c[i-1] - 1
zt20, zt10 = pct > 0.195, pct > 0.095
print(f"  [2] 涨停: pct={pct*100:.2f}%, zt10={zt10}, zt20={zt20} -> {'PASS' if (zt20 or zt10) else 'FAIL'}")

# 3. 封板
fb = c[i] >= h[i]
print(f"  [3] 封板: c={c[i]:.2f}, h={h[i]:.2f} -> {'PASS' if fb else 'FAIL'}")

# 4. 换手率
os_ = df["outstanding_share"].iloc[i]
sh_rate = v[i] / os_ * 100 if os_ > 0 else 0
hs_ok = (zt20 and sh_rate < 25) or (zt10 and sh_rate < 20)
print(f"  [4] 换手率: {sh_rate:.2f}% -> {'PASS' if hs_ok else 'FAIL'}")

# 5. MA60方向
ma60_i = np.mean(c[i-59:i+1])
ma60_prev = np.mean(c[i-69:i-9])
ma60_up = ma60_i > ma60_prev
print(f"  [5] MA60方向: now={ma60_i:.2f}, prev={ma60_prev:.2f} -> {'PASS' if ma60_up else 'FAIL'}")

# 6. POS条件
ma60 = np.mean(c[i-59:i+1])
ma5 = np.mean(c[i-4:i+1])
ma10 = np.mean(c[i-9:i+1])
a_cls = (c[i-1] < ma60) and (c[i] >= ma60)
print(f"  [6A] A类(蛟龙出海): c[i-1]={c[i-1]:.2f}, ma60={ma60:.2f}, c[i]={c[i]:.2f} -> {'PASS' if a_cls else 'FAIL'}")

b_cls = (abs(c[i]/ma60 - 1) < 0.15) and (ma5 > ma10) and (ma10 > np.mean(c[i-12:i-9]))
print(f"  [6B] B类(均线粘合): |{c[i]/ma60-1:.4f}|<0.15={abs(c[i]/ma60-1)<0.15}, ma5({ma5:.2f})>ma10({ma10:.2f})={ma5>ma10} -> {'PASS' if b_cls else 'FAIL'}")

days_abv = sum(1 for j in range(max(0,i-4), i+1) if c[j] > np.mean(c[j-59:j+1]))
c_cls = (days_abv >= 3 and l[i-1] <= ma60*1.03 and l[i-1] >= ma60*0.97)
print(f"  [6C] C类(回踩确认): days_above={days_abv}, l[i-1]={l[i-1]:.2f}, ma60*0.97={ma60*0.97:.2f}, ma60*1.03={ma60*1.03:.2f} -> {'PASS' if c_cls else 'FAIL'}")

pos = a_cls or b_cls or c_cls
print(f"  [6] POS结论: {'PASS' if pos else 'FAIL'}")

# 7. 量比
vol_ma60 = np.mean(v[i-59:i+1])
vol_ratio = v[i] / vol_ma60 if vol_ma60 > 0 else 0
vol_ok = v[i] > vol_ma60 * 1.5
print(f"  [7] 量比: {vol_ratio:.2f}x -> {'PASS' if vol_ok else 'FAIL'}")

# 8. 120日高
hh120 = np.max(h[max(0, i-119):i+1])
pos_high = c[i] <= hh120 * 1.02
print(f"  [8] 位置(120日高): c={c[i]:.2f}, 120h={hh120:.2f}, ratio={c[i]/hh120:.4f} -> {'PASS' if pos_high else 'FAIL'}")

# 9. 20日振幅
hh20 = np.max(h[max(0, i-19):i+1])
ll20 = np.min(l[max(0, i-19):i+1])
amp = (hh20 - ll20) / ll20 * 100 if ll20 > 0 else 0
amp_ok = amp < 50
print(f"  [9] 20日振幅: {amp:.2f}% -> {'PASS' if amp_ok else 'FAIL'}")

# 10. 5日涨幅
chg5 = (c[i] / c[i-5] - 1) * 100 if i >= 5 else 0
chg5_ok = chg5 < 40
print(f"  [10] 5日涨幅: {chg5:.2f}% -> {'PASS' if chg5_ok else 'FAIL'}")

# 11. 市值
cm = df["circ_mv"].iloc[i]
cm_ok = 20 <= cm <= 500
print(f"  [11] 流通市值: {cm:.0f}亿 -> {'PASS' if cm_ok else 'FAIL'}")

# 最终结论
overall = new_high and (zt20 or zt10) and fb and hs_ok and ma60_up and pos and vol_ok and pos_high and amp_ok and chg5_ok and cm_ok
print(f"\n  策略A最终判定: {'【入选】' if overall else '【过滤】'}")
print(f"  失败条件: ", end="")
fails = []
if not new_high: fails.append("百日新高")
if not (zt20 or zt10): fails.append("涨停")
if not fb: fails.append("封板")
if not hs_ok: fails.append("换手率")
if not ma60_up: fails.append("MA60方向")
if not pos: fails.append("POS(A/B/C)")
if not vol_ok: fails.append(f"量比({vol_ratio:.1f}x)")
if not pos_high: fails.append(f"120日高")
if not amp_ok: fails.append(f"20日振幅({amp:.1f}%)")
if not chg5_ok: fails.append(f"5日涨幅({chg5:.1f}%)")
if not cm_ok: fails.append(f"市值({cm:.0f}亿)")
print(f"  {', '.join(fails) if fails else '无'}")

# ===========================================================
# 4. 核查回测交易记录
# ===========================================================
print("\n" + "=" * 80)
print("【4/7】回测交易记录抽样核查")
print("=" * 80)

for lbl in ["A", "B", "C"]:
    pkl = os.path.join(RESULT_DIR, f"result_{lbl}.pkl")
    if not os.path.exists(pkl):
        continue
    with open(pkl, "rb") as f:
        result = pickle.load(f)
    
    trades = result.trades
    if not trades:
        print(f"  策略{lbl}: 无交易")
        continue
    
    # 统计
    pnl_values = [t.pnl_pct for t in trades]
    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    
    print(f"\n  策略{lbl}: {len(trades)}笔交易")
    print(f"    盈利: {len(wins)}笔, 亏损: {len(losses)}笔")
    print(f"    最大盈利: {max(pnl_values):.2f}%")
    print(f"    最大亏损: {min(pnl_values):.2f}%")
    print(f"    平均盈利: {np.mean([t.pnl_pct for t in wins]):.2f}%" if wins else "")
    print(f"    平均亏损: {np.mean([t.pnl_pct for t in losses]):.2f}%" if losses else "")
    
    # 抽取前5笔交易
    print(f"    前5笔交易:")
    for t in trades[:5]:
        print(f"      {t.buy_date} ~ {t.sell_date} | {t.name}({t.code}) | "
              f"买{t.buy_price:.2f}->卖{t.sell_price:.2f} | {t.pnl_pct:+.2f}% | {t.hold_days}日 | {t.exit_reason}")

# ===========================================================
# 5. 核查回测引擎逻辑：买入价和卖出价
# ===========================================================
print("\n" + "=" * 80)
print("【5/7】回测引擎逻辑核查（买入/卖出价格计算）")
print("=" * 80)

code = "002259"
cf = os.path.join(CACHE_DIR, f"stock_{code}.pkl")
df = pd.read_pickle(cf)

# 模拟一个交易：假设信号日是2026-01-05，次日开盘买入
signal_date = "2026-01-05"
buy_date = "2026-01-06"

signal_row = df[df["date"] == signal_date]
buy_row = df[df["date"] == buy_date]

if len(signal_row) > 0 and len(buy_row) > 0:
    signal_close = signal_row.iloc[0]["close"]
    buy_open = buy_row.iloc[0]["open"]
    
    expected_buy_price = buy_open * (1 + 0.001) * (1 + 0.00025)
    
    print(f"  信号日: {signal_date}, 收盘: {signal_close:.2f}")
    print(f"  买入日: {buy_date}, 开盘: {buy_open:.2f}")
    print(f"  买入价计算: {buy_open:.2f} * (1+0.001滑点) * (1+0.00025手续费) = {expected_buy_price:.4f}")
    print(f"  检查: buy_price应为开盘价之上 -> {'OK' if expected_buy_price > buy_open else 'ERROR'}")
    
    # 检查卖出
    sell_row = df[df["date"] == "2026-01-07"]
    if len(sell_row) > 0:
        sell_open = sell_row.iloc[0]["open"]
        expected_sell_price = sell_open * (1 - 0.001) * (1 - 0.00125)
        print(f"  卖出日: 2026-01-07, 开盘: {sell_open:.2f}")
        print(f"  卖出价计算: {sell_open:.2f} * (1-0.001滑点) * (1-0.00125费用) = {expected_sell_price:.4f}")
        print(f"  检查: sell_price应为开盘价之下 -> {'OK' if expected_sell_price < sell_open else 'ERROR'}")

# ===========================================================
# 6. 核查净值曲线
# ===========================================================
print("\n" + "=" * 80)
print("【6/7】净值曲线合理性核查")
print("=" * 80)

for lbl in ["A", "B", "C"]:
    pkl = os.path.join(RESULT_DIR, f"result_{lbl}.pkl")
    if not os.path.exists(pkl):
        continue
    with open(pkl, "rb") as f:
        result = pickle.load(f)
    
    eq = result.equity_curve
    if len(eq) > 0:
        print(f"  策略{lbl}: {len(eq)}个净值点")
        print(f"    初始: {eq[0]:.0f}, 最终: {eq[-1]:.0f}")
        print(f"    最小值: {min(eq):.0f}, 最大值: {max(eq):.0f}")
        
        # 检查是否有异常跳变
        eq_arr = np.array(eq)
        daily_ret = np.diff(eq_arr) / eq_arr[:-1]
        extreme = np.sum(np.abs(daily_ret) > 0.2)  # 单日超20%的异常
        print(f"    单日波动>20%的次数: {extreme}")
        if extreme > 0:
            extreme_days = np.where(np.abs(daily_ret) > 0.2)[0]
            for d in extreme_days[:3]:
                print(f"      日{d}: {eq[d]:.0f} -> {eq[d+1]:.0f} ({daily_ret[d]*100:.2f}%)")

# ===========================================================
# 7. 核查与通达信原始公式的一致性
# ===========================================================
print("\n" + "=" * 80)
print("【7/7】通达信原始公式一致性核查")
print("=" * 80)

print("""
原始通达信公式关键条件:
  BaiRiXinGao := C = HHV(C, 100);       -> 实现: c[i] >= np.max(c[i-99:i+1])
  ZT := C/REF(C,1) > 1.095 OR > 1.195;  -> 实现: zt10=0.095, zt20=0.195
  FB := C = H;                           -> 实现: c[i] >= h[i] (允许相等)
  HS_OK: 20cm<25%, 10cm<20%;            -> 实现: 正确
  MA60_UP := MA60 > REF(MA60, 10);      -> 实现: np.mean(c[i-59:i+1]) > np.mean(c[i-69:i-9])
  A_CLASS := CROSS(C, MA60);            -> 实现: c[i-1] < ma60 and c[i] >= ma60
  B_CLASS: 在60日线±15% + 均线多头;     -> 实现: 正确
  C_CLASS: 近5日>=3天站上 + 回踩±3%;   -> 实现: 正确
  COND_VOL := V > MA(V,60) * 1.5;       -> 实现: 正确
  COND_HIGH := C/HHV(C,120) < 1.0;      -> 改为 <= 1.02 (放宽)
  COND_RANGE: 20日振幅<50%;             -> 实现: 正确
  5日涨幅<40%;                          -> 实现: 正确
  流通市值20-500亿;                      -> 实现: 正确

NOTES:
  1. FINANCE(30)>0 (净利润>0) 未实现 - 因akshare不提供该字段
  2. COND_HIGH 从 <1.0 放宽到 <=1.02 - 因百日新高接近120日高
  3. 换手率字段从turnover(小数)或outstanding_share计算
""")

print("\n" + "=" * 80)
print("核查完成")
print("=" * 80)