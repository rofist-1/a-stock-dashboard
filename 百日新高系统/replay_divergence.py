# -*- coding: utf-8 -*-
"""启动分歧买点 vs 标准买点 回测验证"""
import sys,os,pickle,glob,json
import numpy as np; import pandas as pd

BASE = r'C:\Users\Rofis\Desktop'; os.chdir(BASE)
import akshare as ak
idx = ak.stock_zh_index_daily(symbol='sh000001')
idx['date'] = pd.to_datetime(idx['date']); idx = idx.set_index('date').sort_index()
cache = os.path.join(BASE,'百日新高系统','kline_cache')
sector_map = json.load(open(os.path.join(BASE,'百日新高系统','sector_map.json'),encoding='utf-8'))
all_files = glob.glob(os.path.join(cache,'*.pkl'))

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

def find_divergence_buy(df, start_str, end_str, sector):
    """扫描启动分歧买点"""
    res=[]; di=list(df.index)
    c=df['close']; h=df.get('high'); l=df.get('low'); v=df.get('volume'); a=df.get('amount')
    if h is None or l is None: return res
    st=pd.Timestamp(start_str); ed=pd.Timestamp(end_str)
    scan=[d for d in di if st<=d<=ed]
    for k,d in enumerate(scan):
        idx=di.index(d)
        if idx<63: continue
        # 1.近3日有涨停/>=7%
        surged=False; sj=-1
        for back in range(4):
            j=idx-back
            if j<1: continue
            pct=(c.iloc[j]-c.iloc[j-1])/c.iloc[j-1]*100
            if pct>=7 or pct>=9.5:
                m60j=c.iloc[max(0,j-60):j+1].mean()
                if c.iloc[j]>m60j: surged=True; sj=j; break
        if not surged: continue
        if sj<0: continue
        # 3. MA60走平/向上
        m60=c.iloc[max(0,idx-60):idx+1].mean()
        m60p=c.iloc[max(0,idx-61):idx].mean() if idx>=61 else m60
        if m60<m60p*0.98: continue
        # 4. 距MA60 -2% to +20%
        dist=(c.iloc[idx]-m60)/m60*100
        if dist<-2 or dist>20: continue
        # 5. 分歧日: 振幅>=4%, 量>=1.5倍5日均量, close>MA5
        amp=(h.iloc[idx]-l.iloc[idx])/c.iloc[max(0,idx-1)]*100
        if amp<4: continue
        if v is not None:
            avg5=v.iloc[max(0,idx-5):idx].mean()
            if avg5>0 and v.iloc[idx]<avg5*1.5: continue
        ma5=c.iloc[max(0,idx-5):idx+1].mean()
        if c.iloc[idx]<=ma5: continue
        # 6. 次日缩量<60%, 小阳/十字星
        if idx+2>=len(di): continue
        ni=idx+1
        if a is not None and a.iloc[ni]>=a.iloc[idx]*0.6: continue
        body=abs(c.iloc[ni]-df['open'].iloc[ni])
        is_small=body<c.iloc[ni]*0.03
        is_bull=c.iloc[ni]>=df['open'].iloc[ni]
        if not (is_small or is_bull): continue
        # 7. 次日开盘买
        bi=ni+1
        if bi>=len(di): continue
        bd=di[bi]; bp=df['open'].iloc[bi]
        mie=min(bi+21, len(di)); mx=c.iloc[bi:mie].max()
        mg=(mx-bp)/bp*100
        res.append({'code':'','surge':di[sj],'div':d,'conf':di[ni],'buy_date':bd,'buy_p':bp,'max_g':mg,'sec':sector,'dist':dist,'stopped':False})
    return res

def find_standard_buy(df, bo_date, bo_idx, di):
    """突破后缩量回踩"""
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
        at='MA10' if at10 else 'MA20'
        return [{'code':'','bo':bo_date,'pb':di[j],'buy_date':bd,'buy_p':bp,'max_g':mg,'atype':at}]
    return []

def replay(name, sects, START, END, warm_start):
    print(f'\n{"="*60}')
    print(f'  {name}')
    print(f'  {START} -> {END}')
    print(f'{"="*60}')
    wd=idx[warm_start:END].index.tolist()
    tc=set()
    for cd,sc in sector_map.items():
        cl=cd.replace('sh','').replace('sz','').replace('bj','')
        if any(s in sc for s in sects): tc.add(cl)
    print(f'板块股票: {len(tc)}只')
    stb=[]; dvb=[]
    for f in all_files:
        cd=os.path.basename(f).replace('.pkl',''); cl=cd.replace('sh','').replace('sz','').replace('bj','')
        if cl[-6:] not in tc and cl not in tc: continue
        df=load_df(f,wd)
        if df is None: continue
        di=list(df.index); c=df['close']
        # 获取行业
        sc=sector_map.get(cd, sector_map.get(cl, ''))
        # --- 标准买点: 先找突破 ---
        st=pd.Timestamp(START); ed=pd.Timestamp(END)
        for dd in di:
            if dd<st or dd>ed: continue
            idx_d=di.index(dd)
            if idx_d<63: continue
            m60=c.iloc[idx_d-60:idx_d+1].mean(); ct=c.iloc[idx_d]
            if ct<=m60: continue
            m1=c.iloc[idx_d-61:idx_d].mean() if idx_d>=61 else m60; m2=c.iloc[idx_d-62:idx_d-1].mean() if idx_d>=62 else m1
            if not (m60>m1>m2): continue
            vv=df.get('volume'); vr=0
            if vv is not None and idx_d>=5:
                a5=vv.iloc[idx_d-5:idx_d].mean()
                if a5>0: vr=vv.iloc[idx_d]/a5
                if vr<1.5: continue
            if idx_d>=20:
                c20=(c.iloc[idx_d]-c.iloc[idx_d-20])/c.iloc[idx_d-20]*100
                if c20>30: continue
            ds=(ct-m60)/m60*100
            if ds<0 or ds>20: continue
            # Found breakout
            sb=find_standard_buy(df, dd, idx_d, di)
            for s in sb: s['code']=cl[-6:]; s['sector']=sc
            stb.extend(sb)
        # --- 分歧买点 ---
        db=find_divergence_buy(df, START, END, sc)
        for d in db: d['code']=cl[-6:]
        dvb.extend(db)
    # --- Report ---
    print(f'\n标准缩量回踩买点: {len(stb)}信号')
    if stb:
        g=[s['max_g'] for s in stb]; w=sum(1 for x in g if x>=5)
        print(f'  有效(>=5%): {w}/{len(stb)} 最高{max(g):+.0f}% 均{np.mean(g):+.1f}%')
        for s in sorted(stb,key=lambda x:x['max_g'],reverse=True)[:8]:
            sg='++' if s['max_g']>15 else ('+' if s['max_g']>=5 else '-')
            print(f"  {sg} {s['code']} {s['atype']} +{s['max_g']:.0f}%")
    print(f'\n启动分歧买点: {len(dvb)}信号')
    if dvb:
        g=[d['max_g'] for d in dvb]; w=sum(1 for x in g if x>=5)
        print(f'  有效(>=5%): {w}/{len(dvb)} 最高{max(g):+.0f}% 均{np.mean(g):+.1f}%')
        for d in sorted(dvb,key=lambda x:x['max_g'],reverse=True)[:10]:
            sg='++' if d['max_g']>15 else ('+' if d['max_g']>=5 else '-')
            print(f"  {sg} {d['code']} surge={d['surge'].strftime('%m-%d')} div={d['div'].strftime('%m-%d')} +{d['max_g']:.0f}% dist={d['dist']:.0f}%")
    return stb, dvb

# === 商业航天 ===
s1,d1 = replay('商业航天 2025/12','飞机制造','2025-12-01','2026-01-31','2025-09-01')
# === 半导体 ===
s2,d2 = replay('半导体 2026/04',['电子器件','电子信息'],'2026-04-01','2026-04-30','2026-01-01')

print(f'\n{"="*60}')
print(f'  对比总结')
print(f'{"="*60}')
for nm,st,dv in [('商业航天',s1,d1),('半导体',s2,d2)]:
    print(f'\n{nm}:')
    if st: g=[s['max_g'] for s in st]; print(f'  标准: {len(st)}信号 有效{sum(1 for x in g if x>=5)} 均{np.mean(g):+.1f}%')
    else: print(f'  标准: 0信号')
    if dv: g=[d['max_g'] for d in dv]; print(f'  分歧: {len(dv)}信号 有效{sum(1 for x in g if x>=5)} 均{np.mean(g):+.1f}% 最高{max(g):+.0f}%')
    else: print(f'  分歧: 0信号')
