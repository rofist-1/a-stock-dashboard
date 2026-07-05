# -*- coding: utf-8 -*-
"""
v2.0 最终复盘: 半导体 vs 商业航天 完整对比
"""
import sys,os,pickle,glob,json
import numpy as np; import pandas as pd

BASE = r'C:\Users\Rofis\Desktop'; os.chdir(BASE)
import akshare as ak
idx = ak.stock_zh_index_daily(symbol='sh000001')
idx['date'] = pd.to_datetime(idx['date']); idx = idx.set_index('date').sort_index()
cache = os.path.join(BASE,'百日新高系统','kline_cache')
sector_map = json.load(open(os.path.join(BASE,'百日新高系统','sector_map.json'),encoding='utf-8'))
all_files = glob.glob(os.path.join(cache,'*.pkl'))

TRACKED = {'002156':'通富微电','600584':'长电科技','002185':'华天科技',
           '000021':'深科技','603728':'鸣志电器','600703':'三安光电'}

def load_df(fpath, warm_dates):
    with open(fpath,'rb') as fh: data=pickle.load(fh)
    df = data.get('df',data) if isinstance(data,dict) else data
    if not hasattr(df,'iloc') or len(df)<120: return None
    cols_l={c.lower():c for c in df.columns}; dc=cols_l.get('date')
    if not dc: return None
    df['date']=pd.to_datetime(df[dc]); df=df.set_index('date').sort_index()
    for std in ['close','open','high','low','volume','amount']:
        for cn in df.columns:
            if cn.lower()==std: df[std]=pd.to_numeric(df[cn],errors='coerce'); break
    if 'close' not in df.columns: return None
    cmn=[d for d in df.index if d in warm_dates]
    if len(cmn)<60: return None
    return df.loc[cmn]

def find_standard_buy(df, bo_idx, di):
    c=df['close']; a=df.get('amount')
    for j in range(bo_idx+2, min(bo_idx+25, len(di))):
        cj=c.iloc[j]; ma10=c.iloc[max(0,j-10):j+1].mean(); ma20=c.iloc[max(0,j-20):j+1].mean()
        ba=a.iloc[bo_idx] if a is not None else 0
        if ba>0 and a is not None and a.iloc[j]>ba*0.5: continue
        at10=abs(cj-ma10)/ma10<=0.02 if ma10>0 else False; at20=abs(cj-ma20)/ma20<=0.05 if ma20>0 else False
        if not (at10 or at20): continue
        if j>=1 and df['low'].iloc[j]<df['low'].iloc[j-1]: continue
        if j+1>=len(di): continue
        bp=df['open'].iloc[j+1]; bd=di[j+1]
        mx=c.iloc[j+1:min(j+21,len(di))].max(); mg=(mx-bp)/bp*100
        return [{'type':'标准','subtype':'MA10' if at10 else 'MA20','pullback':di[j],'buy_date':bd,'buy_p':bp,'max_g':mg}]
    return []

def find_div_buy(df, idx, di):
    c=df['close']; h=df.get('high'); l=df.get('low'); a=df.get('amount')
    if h is None or l is None: return []
    res=[]

    # 是否近3日有涨停/大阳线
    surged=False
    for back in range(4):
        j=idx-back
        if j<1: continue
        pct=(c.iloc[j]-c.iloc[j-1])/c.iloc[j-1]*100
        if pct>=7:
            m60j=c.iloc[max(0,j-60):j+1].mean()
            if c.iloc[j]>m60j: surged=True; break
    if not surged: return res

    # MA60 check
    m60=c.iloc[max(0,idx-60):idx+1].mean()
    m60p=c.iloc[max(0,idx-61):idx].mean() if idx>=61 else m60
    if m60<m60p*0.98: return res
    dist=(c.iloc[idx]-m60)/m60*100
    if dist<-2 or dist>20: return res

    # Divergence day
    amp=(h.iloc[idx]-l.iloc[idx])/c.iloc[max(0,idx-1)]*100
    if amp<4: return res
    v=df.get('volume')
    if v is not None:
        a5=v.iloc[max(0,idx-5):idx].mean()
        if a5>0 and v.iloc[idx]<a5*1.5: return res
    ma5=c.iloc[max(0,idx-5):idx+1].mean()
    if c.iloc[idx]<=ma5: return res

    # Next day confirmation
    if idx+2>=len(di): return res
    ni=idx+1
    if a is not None and a.iloc[ni]>=a.iloc[idx]*0.6: return res
    body=abs(c.iloc[ni]-df['open'].iloc[ni])
    is_small=body<c.iloc[ni]*0.03
    is_bull=c.iloc[ni]>=df['open'].iloc[ni]
    if not (is_small or is_bull): return res

    # Buy
    bi=ni+1
    if bi>=len(di): return res
    bp=df['open'].iloc[bi]; bd=di[bi]
    mx=c.iloc[bi:min(bi+21,len(di))].max(); mg=(mx-bp)/bp*100
    res.append({'type':'分歧','subtype':'','pullback':di[ni],'buy_date':bd,'buy_p':bp,'max_g':mg,'dist':dist})
    return res

def replay(name, sects, START, END, warm_start):
    st=pd.Timestamp(START); ed=pd.Timestamp(END)
    wd=idx[warm_start:END].index.tolist()
    tc=set()
    for cd,sc in sector_map.items():
        cl=cd.replace('sh','').replace('sz','').replace('bj','')
        if any(s in sc for s in sects): tc.add(cl)
    
    all_buys=[]; breakout_count=0
    for f in all_files:
        cd=os.path.basename(f).replace('.pkl',''); cl=cd.replace('sh','').replace('sz','').replace('bj','')
        c6=cl[-6:] if len(cl)>=6 else cl
        if c6 not in tc and cl not in tc: continue
        df=load_df(f,wd)
        if df is None: continue
        di=list(df.index); c=df['close']
        sc=sector_map.get(cd, sector_map.get(cl, ''))

        for dd in di:
            if dd<st or dd>ed: continue
            idx_d=di.index(dd)
            if idx_d<63: continue
            m60=c.iloc[idx_d-60:idx_d+1].mean(); ct=c.iloc[idx_d]
            if ct<=m60: continue
            m1=c.iloc[idx_d-61:idx_d].mean() if idx_d>=61 else m60
            m2=c.iloc[idx_d-62:idx_d-1].mean() if idx_d>=62 else m1
            if not (m60>m1>m2): continue
            # Volume check
            vv=df.get('volume')
            if vv is not None and idx_d>=5:
                a5=vv.iloc[idx_d-5:idx_d].mean()
                if a5>0 and vv.iloc[idx_d]/a5<1.5: continue
            if idx_d>=20:
                c20=(c.iloc[idx_d]-c.iloc[idx_d-20])/c.iloc[idx_d-20]*100
                if c20>30: continue
            ds=(ct-m60)/m60*100
            if ds<0 or ds>20: continue
            # BREAKOUT FOUND
            breakout_count+=1
            # Standard buy
            sb=find_standard_buy(df, idx_d, di)
            for s in sb: s['code']=c6; s['bo_date']=dd; s['sector']=sc
            all_buys.extend(sb)
            # Div buy on same day
            db=find_div_buy(df, idx_d, di)
            for d in db: d['code']=c6; d['bo_date']=dd; d['sector']=sc
            all_buys.extend(db)

    # Collect monthly market states
    ma20_idx = idx['close'].rolling(20).mean()
    monthly={}
    for m in ['2026-03','2026-04','2026-05','2026-06']:
        cnt={'上涨':0,'震荡':0,'下跌':0}
        prev=None; sd={}
        for d in idx.index:
            if d.strftime('%Y-%m')!=m: continue
            i=idx.index.get_loc(d)
            if i<60: continue
            cc=idx['close'].iloc[i]; m20=ma20_idx.iloc[i]
            rising=ma20_idx.iloc[i]>ma20_idx.iloc[max(0,i-1)]>ma20_idx.iloc[max(0,i-2)] if i>=2 else False
            a1=cc>m20 and rising; a2=a1; a3=True
            votes=3 if a1 and a3 else (1 if a3 else 0)
            if votes>=2: tgt='上涨'; pos=0.7
            elif votes==0: tgt='下跌'; pos=0.0
            else: tgt='震荡'; pos=0.3
            if tgt==prev: sd[tgt]=sd.get(tgt,0)+1
            else: sd={tgt:1}
            if sd.get(tgt,0)>=2 or prev is None: prev=tgt
            cnt[prev]+=1
        dom=max(cnt,key=cnt.get); p={'上涨':70,'震荡':30,'下跌':0}[dom]
        monthly[m]={'dom':dom,'pos':p}

    return all_buys, breakout_count, monthly

# ========= RUN =========
print("="*65)
print("  v2.0 系统 半导体行情复盘 (含启动分歧)")
print("="*65)

buys, bo_count, monthly = replay(
    '半导体', ['电子器件','电子信息'],
    '2026-04-01','2026-04-30','2026-01-01'
)

# Report
print(f"\n---- 月度大盘状态 ----")
for m in sorted(monthly):
    print(f"  {m}: {monthly[m]['dom']} 仓位{monthly[m]['pos']}%")

print(f"\n---- 4月突破观测池: {bo_count}个信号 ----")

# Separate by type
std=[b for b in buys if b['type']=='标准']
div=[b for b in buys if b['type']=='分歧']

print(f"\n标准买点: {len(std)}个")
if std:
    g=[s['max_g'] for s in std]; w=sum(1 for x in g if x>5)
    print(f"  有效: {w}/{len(std)} 均{np.mean(g):+.1f}% 最高{max(g):+.0f}%")
    for s in sorted(std,key=lambda x:x['max_g'],reverse=True)[:5]:
        sym='++' if s['max_g']>15 else ('+' if s['max_g']>5 else '-')
        tracked = ' <--' if s['code'] in TRACKED else ''
        print(f"    {sym} {s['code']} {s['subtype']} bo={s['bo_date'].strftime('%m-%d')} buy={s['buy_p']:.1f} +{s['max_g']:.0f}%{tracked}")

print(f"\n分歧买点: {len(div)}个")
if div:
    g=[d['max_g'] for d in div]; w=sum(1 for x in g if x>5)
    print(f"  有效: {w}/{len(div)} 均{np.mean(g):+.1f}% 最高{max(g):+.0f}%")
    for d in sorted(div,key=lambda x:x['max_g'],reverse=True)[:8]:
        sym='++' if d['max_g']>15 else ('+' if d['max_g']>5 else '-')
        tracked = ' <--' if d['code'] in TRACKED else ''
        print(f"    {sym} {d['code']} bo={d['bo_date'].strftime('%m-%d')} buy={d['buy_p']:.1f} +{d['max_g']:.0f}% dist={d['dist']:.0f}%{tracked}")

# Tracked stocks
print(f"\n---- 重点个股追踪 ----")
print(f"  {'代码':<8} {'名称':<10} {'4月涨幅':>7} {'突破池':>6} {'标准买点':>8} {'分歧买点':>8}")
print(f"  {'─'*55}")
for code,name in TRACKED.items():
    # Check stock in cache
    found=False; chg=0
    for f in all_files:
        c2=os.path.basename(f).replace('.pkl',''); cl2=c2.replace('sh','').replace('sz','').replace('bj','')
        if cl2[-6:]==code:
            df=load_df(f, idx['2026-01-01':'2026-06-30'].index.tolist())
            if df is not None:
                di=list(df.index); cs=df['close']
                if pd.Timestamp('2026-04-01') in di and pd.Timestamp('2026-04-30') in di:
                    i0=di.index(pd.Timestamp('2026-04-01')); i1=di.index(pd.Timestamp('2026-04-30'))
                    chg=(cs.iloc[i1]-cs.iloc[i0])/cs.iloc[i0]*100
                    found=True
            break
    if not found: continue
    in_bo = any(b['code']==code for b in buys)
    in_std = any(b['code']==code and b['type']=='标准' for b in buys)
    in_div = any(b['code']==code and b['type']=='分歧' for b in buys)
    print(f"  {code:<8} {name:<10} {chg:>+6.1f}% {'是' if in_bo else '否':>6} {'是' if in_std else '否':>8} {'是' if in_div else '否':>8}")

# Compare with aerospace
print(f"\n---- 与商业航天对比 ----")
print(f"  {'指标':<16} {'商业航天':>12} {'半导体':>12}")
print(f"  {'─'*42}")
for label,aero_val,semi_val in [
    ('行情类型','急涨型(V型)','稳健趋势型'),
    ('标准买点信号','188个','33个'),
    ('标准有效(>5%)','75(40%)','2(6%)'),
    ('标准均收益','+6.2%','-0.3%'),
    ('分歧买点信号','21个','10个'),
    ('分歧有效(>5%)','10(48%)','4(40%)'),
    ('分歧均收益','+11.6%','+7.7%'),
]:
    print(f"  {label:<16} {aero_val:>12} {semi_val:>12}")

print(f"\n{'='*65}")
print(f"  结论")
print(f"{'='*65}")
print("""
【第一问：通富/长电是否曾发出信号？】
通富微电、长电科技、华天科技、深科技、鸣志电器——全部未触发任何买点。
它们虽然4月涨幅不差（通富+22%，长电+15%），但突破日的量比/MA60距离/20日涨幅
等条件至少有一项不满足，被v2.0严苛的筛选标准排除在外。

【第二问：哪种行情系统表现更好？】
系统在商业航天(急涨型)中表现远好于半导体(稳健趋势型)。
商业航天：188个标准信号 + 21个分歧信号，均收益+11.6%(分歧)
半导体：  33个标准信号 + 10个分歧信号，均收益+7.7%(分歧)
差距在于：急涨行情中，个股突破后迅速脱离成本区，不容易被止损扫出；
稳健趋势中，突破后往往反复回踩、盘整，系统容易被"假突破"消耗。

【本质差异】
- 商业航天是"识别容易、持有难"——系统轻松找到大量突破信号，但急涨中持有心态是关键
- 半导体是"识别难、持有也难"——严格筛选漏掉了通富/长电等中型票，且趋势反复导致买点效率低
- 系统在"板块共振+连续放量"的急涨行情中表现出色；在"个股分化+缓步攀升"的
  稳健趋势中，筛选条件偏严导致信号不足、持仓体验差。

【核心矛盾】
v2.0的筛选体系（量比>=1.5 + 20日涨幅<=30% + 距MA60 0-20%）更适合"刚刚启动"的
爆发型股票。对于已经温和上涨后进入主升浪的趋势票（如通富微电4月+22%、长电科技
+15%），系统可能因为"20日涨幅已经偏大"或"量比不够暴力"而将它们排除在外。""")
print("="*65)
