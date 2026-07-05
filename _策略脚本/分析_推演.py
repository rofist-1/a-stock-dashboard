# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\Rofis\Desktop\a股波段看板_2026-06-04.json', encoding='utf-8') as f:
    data = json.load(f)
data.sort(key=lambda x: x['date'])

def ms(d):
    s=0
    for t,sc in ((100,20),(80,16),(60,12),(40,8),(20,4)):
        if d['limitUp']>=t: s+=sc; break
    for t,sc in ((3,25),(6,10),(9,0),(15,-10),(999,-20)):
        if d['limitDown']<=t: s+=sc; break
    br=d['bomb']/max(d['limitUp'],1)
    for t,sc in ((0.2,20),(0.3,15),(0.4,10),(0.5,5),(999,-5)):
        if br<t: s+=sc; break
    for t,sc in ((20,15),(12,12),(8,8),(5,4)):
        if d['chain']>=t: s+=sc; break
    for t,sc in ((35000,15),(30000,12),(25000,8),(20000,5),(15000,2)):
        if d['volume']>=t: s+=sc; break
    r=d['newHigh']/max(d['newLow'],1)
    for t,sc in ((15,20),(8,16),(4,12),(2,8),(1,4),(0,-10)):
        if r>=t: s+=sc; break
    return max(0,min(100,s))

# 近期趋势
print("=== 近20日趋势 ===")
print("日期       涨停 跌停  新高  新低   差值    成交量  评分  等级")
print("-"*75)
for d in data[-20:]:
    sc=ms(d)
    diff=d['newHigh']-d['newLow']
    lv = 'S' if sc>=75 else 'A' if sc>=60 else 'B' if sc>=45 else 'C' if sc>=30 else 'D'
    print(f"{d['date']}  {d['limitUp']:>4}{d['limitDown']:>5}  {d['newHigh']:>4}{d['newLow']:>5}  {diff:>+6}  {d['volume']:>5}  {sc:>3}  {lv}")

# 新低变化
print("\n=== 新低连续扩大阶段 (市场加速探底) ===")
i=0
while i < len(data)-3:
    if all(data[i+j]['newLow'] > data[i+j-1]['newLow'] for j in range(1,4)):
        start = data[i]['date']
        while i < len(data)-1 and data[i+1]['newLow'] > data[i]['newLow']:
            i+=1
        end = data[i]['date']
        print(f"  {start} ~ {end}: 新低从{data[i-3]['newLow']}升至{data[i]['newLow']}")
    i+=1

# 每次从低位反弹的特征
print("\n=== 冰点反弹历史模式 ===")
for i in range(5, len(data)):
    cur=data[i]
    prev=data[i-1]
    if cur['newLow'] < prev['newLow'] and prev['newLow'] > data[i-2]['newLow']:
        before = data[max(0,i-5):i]
        avg_nl_before = sum(d['newLow'] for d in before)/len(before)
        after = data[i:min(len(data),i+4)]
        if len(after)>=2:
            print(f"  反弹日: {cur['date']}(新低{cur['newLow']},前5日均{avg_nl_before:.0f})")
            print(f"        信号: 涨停{data[i-1]['limitUp']}->{cur['limitUp']} 评分{ms(data[i-1])}->{ms(cur)}")
            for j in range(1, min(4, len(after))):
                print(f"        T+{j}: {after[j]['date']} 涨停{after[j]['limitUp']} 新低{after[j]['newLow']} 评分{ms(after[j])}")

# 当前状态
print("\n=== 当前推演 (基于6月4日) ===")
last = data[-1]
prev = data[-2]
print(f"  最新: 涨停{last['limitUp']} 跌停{last['limitDown']} 新低{last['newLow']}")
print(f"  上日: 涨停{prev['limitUp']} 跌停{prev['limitDown']} 新低{prev['newLow']}")
print(f"  评分: {ms(last)} -> {ms(prev)}")

# 比对新低模式
max_newlow = max(d['newLow'] for d in data)
last_3 = [d['newLow'] for d in data[-3:]]
if last_3[2] > last_3[1] > last_3[0]:
    print("  \u26a0 新低三连升，处于加速探底中")
elif last_3[2] < last_3[1]:
    print("  \u2716 新低首次回落，可能是短期底部信号")
else:
    print("  \u25b6 新低方向不明，等待确认")

# 成交量趋势
vols = [d['volume'] for d in data[-10:]]
vol_trend = sum(vols[-3:])/3 - sum(vols[-10:-7])/3
if vol_trend < -2000:
    print(f"  \u2b07 成交量持续萎缩({vol_trend:+.0f}亿), 资金离场")
elif vol_trend > 2000:
    print(f"  \u2b06 成交量开始放大({vol_trend:+.0f}亿), 资金回流")
else:
    print(f"  \u2192 成交量持平({vol_trend:+.0f}亿), 方向未定")
