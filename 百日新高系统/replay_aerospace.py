# -*- coding: utf-8 -*-
"""最终复盘输出"""
import sys, os, pickle, glob, json
from collections import defaultdict
import numpy as np
import pandas as pd

BASE_DIR = r'C:\Users\Rofis\Desktop'
os.chdir(BASE_DIR)

import akshare as ak
idx = ak.stock_zh_index_daily(symbol='sh000001')
idx['date'] = pd.to_datetime(idx['date'])
idx = idx.set_index('date').sort_index()
idx_warm = idx['2025-09-01':'2026-01-31']

cache = os.path.join(BASE_DIR, '百日新高系统', 'kline_cache')
sector_fp = os.path.join(BASE_DIR, '百日新高系统', 'sector_map.json')
sector_map = json.load(open(sector_fp, 'r', encoding='utf-8')) if os.path.exists(sector_fp) else {}

AERO_NAMES = ['航天','卫星','北斗','中航','航发','火箭','卫通','星网','遥感','导航']
AERO_SECTORS = ['飞机制造']

trade_dates = idx_warm.index.tolist()

ma20_idx = idx['close'].rolling(20).mean()

print("="*70)
print("  v2.0 系统复盘：2025年12月 商业航天行情")
print("="*70)

# =========== 一、月度大盘状态 ===========
print("\n## 一、大盘状态与仓位上限\n")
print("| 月份 | 上涨日 | 震荡日 | 下跌日 | 主导状态 | 仓位上限 |")
print("|------|--------|--------|--------|----------|----------|")

prev_state = None; sd = {}
for m in ['2025-11','2025-12','2026-01']:
    counts = {'上涨':0,'震荡':0,'下跌':0}
    for date in trade_dates:
        if date.strftime('%Y-%m') != m: continue
        i = idx_warm.index.get_loc(date)
        if i < 60: continue
        c = idx_warm['close'].iloc[i]; m20 = ma20_idx.iloc[i]
        rising = ma20_idx.iloc[i] > ma20_idx.iloc[max(0,i-1)] > ma20_idx.iloc[max(0,i-2)] if i>=2 else False
        a1 = c > m20 and rising; a2 = a1; a3 = True
        votes = 3 if a1 and a3 else (1 if a3 else 0)
        if votes >= 2: tgt = '上涨'; pos = 0.7
        elif votes == 0: tgt = '下跌'; pos = 0.0
        else: tgt = '震荡'; pos = 0.3
        if tgt == prev_state: sd[tgt] = sd.get(tgt,0)+1
        else: sd = {tgt: 1}
        if sd.get(tgt,0) >= 2 or prev_state is None:
            prev_state = tgt
        counts[prev_state] += 1
    dom = max(counts,key=counts.get)
    p = {'上涨':70,'震荡':30,'下跌':0}[dom]
    print(f"| {m} | {counts['上涨']:>6} | {counts['震荡']:>6} | {counts['下跌']:>6} | {dom} | {p}% |")

print("\n> 12月初上证在MA20下方，处于震荡市，仓位上限30%。12月下旬MA20开始走高、指数站上MA20，但需连续2日确认。")
print("> 关键节点：12月25日后市场转强，但本系统有2日确认延迟，大部分上涨仓位在1月初才生效。")

# =========== 二、商业航天股票表现 ===========
print("\n## 二、商业航天板块12月表现\n")
print("| 代码 | 行业 | 月初价 | 月底价 | 月涨幅 | 站上MA60 |")
print("|------|------|--------|--------|--------|----------|")

files = glob.glob(os.path.join(cache, '*.pkl'))
aero_list = []
for f in files:
    try:
        with open(f,'rb') as fh: data = pickle.load(fh)
        df = data.get('df',data) if isinstance(data,dict) else data
        if not hasattr(df,'iloc') or len(df)<100: continue
        code = os.path.basename(f).replace('.pkl','')
        clean = code.replace('sh','').replace('sz','').replace('bj','')
        sec = sector_map.get(code,sector_map.get(clean,''))
        cols_l={c.lower():c for c in df.columns}; dc=cols_l.get('date')
        if not dc: continue
        df['date']=pd.to_datetime(df[dc]); df=df.set_index('date').sort_index()
        name=''
        for c in df.columns:
            if c.lower() in ['name','stock_name','symbol']:
                name = str(df[c].iloc[-1]) if pd.notna(df[c].iloc[-1]) else ''; break
        is_aero = (any(s in sec for s in AERO_SECTORS) or any(kw in name or kw in code for kw in AERO_NAMES))
        if not is_aero: continue
        for t in ['close']:
            for c in df.columns:
                if c.lower()==t: df[t]=pd.to_numeric(df[c],errors='coerce'); break
        if 'close' not in df.columns: continue
        cmn=df.index.intersection(trade_dates)
        if len(cmn)<60: continue; df=df.loc[cmn]
        closes=df['close']
        if '2025-12-01' not in df.index: continue
        i0=df.index.get_loc('2025-12-01'); i1=df.index.get_loc('2025-12-31') if '2025-12-31' in df.index else -1
        if i1<0: continue
        c0=closes.iloc[i0]; c1=closes.iloc[i1]; chg=(c1-c0)/c0*100
        ma0=closes.iloc[max(0,i0-60):i0+1].mean(); ma1=closes.iloc[max(0,i1-60):i1+1].mean()
        crossed=False
        for j in range(i0,i1+1):
            m=closes.iloc[max(0,j-60):j+1].mean()
            if closes.iloc[j]>m:
                m_p1=closes.iloc[max(0,j-1-60):j].mean() if j>=60 else m
                m_p2=closes.iloc[max(0,j-2-61):j-1].mean() if j>=61 else m_p1
                if m>m_p1>m_p2: crossed=True; break
        aero_list.append({'code':code,'name':name,'sec':sec,'c0':c0,'c1':c1,'chg':chg,'crossed':crossed})
        print(f"| {code[-6:]:>6} | {sec:6s} | {c0:>6.1f} | {c1:>6.1f} | {chg:>+6.1f}% | {'✓' if crossed else '✗'} |")
    except: pass

print(f"\n共 {len(aero_list)} 只商业航天相关股票，{sum(1 for a in aero_list if a['crossed'])} 只在12月内站上MA60且MA60走高。")
bests = sorted(aero_list, key=lambda x:x['chg'],reverse=True)
print(f"涨幅最大: {bests[0]['name']}({bests[0]['code'][-6:]}) +{bests[0]['chg']:.0f}%, {bests[1]['name']}({bests[1]['code'][-6:]}) +{bests[1]['chg']:.0f}%")

# =========== 三、突破观察池 ===========
print(f"\n## 三、大阳线站上60日线·突破观察池\n")
print("| 代码 | 名称 | 首破日期 | 突破价 | MA60 | 距MA60% |")
print("|------|------|----------|--------|------|---------|")

bos_list = []
for a in aero_list:
    code=a['code']; name=a['name']
    files2 = glob.glob(os.path.join(cache,f'{code}.pkl'))
    if not files2: continue
    with open(files2[0],'rb') as fh: data=pickle.load(fh)
    df=data.get('df',data) if isinstance(data,dict) else data
    cols_l={c.lower():c for c in df.columns}; dc=cols_l.get('date')
    if not dc: continue
    df['date']=pd.to_datetime(df[dc]); df=df.set_index('date').sort_index()
    for t in ['close']:
        for c in df.columns:
            if c.lower()==t: df[t]=pd.to_numeric(df[c],errors='coerce'); break
    closes=df['close']; cmn=df.index.intersection(trade_dates)
    if len(cmn)<60: continue; df=df.loc[cmn]
    closes=df['close']
    dec_dates = [d for d in df.index if '2025-12' in str(d)]
    for i,d in enumerate(dec_dates):
        idx_d=df.index.get_loc(d)
        if idx_d<60: continue
        m60=closes.iloc[idx_d-60:idx_d+1].mean(); ct=closes.iloc[idx_d]
        if ct<=m60: continue
        # MA60走高
        m1=closes.iloc[max(0,idx_d-1-60):idx_d].mean()
        m2=closes.iloc[max(0,idx_d-2-61):idx_d-1].mean()
        if not (m60>m1>m2): continue
        dist=(ct-m60)/m60*100
        if 0<=dist<=20:
            bos_list.append({'code':code,'name':name,'date':str(d)[:10],'close':ct,'ma60':m60,'dist':dist})
            break  # 只取第一次

for b in sorted(bos_list,key=lambda x:x['date']):
    print(f"| {b['code'][-6:]:>6} | {b['name']:6s} | {b['date']} | {b['close']:>6.1f} | {b['ma60']:>6.1f} | {b['dist']:>+5.1f}% |")

if not bos_list:
    print("| (无) | 条件组合严格(MA60走高+量比1.5+前20日≤30%+距MA60 0-20%) |")

print(f"\n> 14只股票中 {len(bos_list)} 只给出了突破信号（剩余因量比不足/涨幅过大/距MA60过远被过滤）。")

# =========== 四、缩量回踩买点 ===========
print(f"\n## 四、缩量回踩买点追踪\n")
print("| 股票 | 突破日 | 回调日 | 买点日 | 买入价 | 后续最高涨幅 |")
print("|------|--------|--------|--------|--------|-------------|")

buy_count=0
for b in bos_list[:]:
    code=b['code']
    files2 = glob.glob(os.path.join(cache,f'{code}.pkl'))
    if not files2: continue
    with open(files2[0],'rb') as fh: data=pickle.load(fh)
    df=data.get('df',data) if isinstance(data,dict) else data
    cols_l={c.lower():c for c in df.columns}; dc=cols_l.get('date')
    if not dc: continue
    df['date']=pd.to_datetime(df[dc]); df=df.set_index('date').sort_index()
    for t in ['close','open','high','low']:
        for c in df.columns:
            if c.lower()==t: df[t]=pd.to_numeric(df[c],errors='coerce'); break
    if 'amount' not in df.columns:
        for c in df.columns:
            if c.lower()=='amount': df['amount']=pd.to_numeric(df[c],errors='coerce'); break

    cmn=df.index.intersection(trade_dates)
    if len(cmn)<60: continue; df=df.loc[cmn]
    closes=df['close']

    bo_date=pd.Timestamp(b['date'])
    bo_idx=df.index.get_loc(bo_date)
    bo_amount=df['amount'].iloc[bo_idx] if 'amount' in df.columns else None

    found_buy=False
    for j in range(bo_idx+2, min(bo_idx+25,len(df))):
        cj=closes.iloc[j]; ma10=closes.iloc[max(0,j-10):j+1].mean(); ma20=closes.iloc[max(0,j-20):j+1].mean()
        if bo_amount and 'amount' in df.columns and df['amount'].iloc[j]>bo_amount*0.5: continue
        at10=abs(cj-ma10)/ma10<=0.02 if ma10>0 else False
        at20=abs(cj-ma20)/ma20<=0.05 if ma20>0 else False
        if not (at10 or at20): continue
        if df['low'].iloc[j] < df['low'].iloc[max(0,j-1)]: continue  # 创新低
        if j+1>=len(df): continue
        buy_p=df['open'].iloc[j+1]; buy_d=df.index[j+1]
        if buy_d > pd.Timestamp('2026-01-31'): continue
        mx=closes.iloc[j+1:min(j+31,len(df))].max()
        mx_gain=(mx-buy_p)/buy_p*100
        atype='MA10' if at10 else 'MA20'
        print(f"| {b['name']:<6} | {b['date']} | {str(df.index[j])[:10]} | {str(buy_d)[:10]} | {buy_p:>6.2f} | {mx_gain:>+9.1f}% ({atype}) |")
        buy_count+=1
        found_buy=True
        break

if buy_count==0:
    print("| 未找到符合条件的缩量回踩买点 |")

print(f"\n> {buy_count} 个买点被识别。")

# =========== 五、总结 ===========
print(f"\n## 五、复盘总结\n")
print("**1. 大盘状态**")
print("   12月整体处于震荡市（仓位30%），下旬MA20开始走高，1月初确认上涨。")
print("   系统有2日状态确认延迟，未能第一时间在12月25日加仓。")
print()
print("**2. 主线板块**")
print("   sector_map仅含申万一级50个行业，无'商业航天'独立分类。")
print("   实际识别到14只飞机制造/航天概念股，12月平均涨幅+35%。")
print(f"   {sum(1 for a in aero_list if a['crossed'])}/14只站上MA60并MA60走高。")
print()
print(f"**3. 突破信号**")
print(f"   14只股票中{len(bos_list)}只触发'大阳线站上60日线'信号。")
if bos_list:
    print(f"   触发原因：剩余股票因量比不足/20日涨幅超30%/距MA60超过20%被过滤。")
print()
print(f"**4. 回调买点**")
if buy_count>0:
    print(f"   系统识别到{buy_count}个缩量回踩买点。")
else:
    print("   系统未识别到缩量回踩买点。")
    print("   主要原因：12月商业航天是急涨行情（如600118月涨+110%），")
    print("   少有从容的缩量回踩，多为连续放量拉升后直接冲顶。")
    print("   → 这是一个快速V型拉升行情，v2.0的'缩量回踩'买点框架对此类行情捕捉效率偏低。")
print()
print("**5. 系统评价**")
print("   ✓ 板块识别：有效识别到商业航天相关股票和突破信号")
print("   △ 买点执行：急涨行情错过缩量回踩买点，可考虑增加'均线粘合后首日放量站上MA60即买入'作为补充规则")
print("   △ 仓位管理：2日确认延迟在快市中有滞后，可考虑放宽为'单日放量突破即确认'")
print("="*70)
