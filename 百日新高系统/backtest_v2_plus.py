# -*- coding: utf-8 -*-
"""v2.0+ 升级版回测: RPS主线 + 三级买点优先级"""
import sys,os,pickle,glob,json
import numpy as np
import pandas as pd
from collections import defaultdict

BASE = r'C:\Users\Rofis\Desktop'; os.chdir(BASE)
import akshare as ak
idx = ak.stock_zh_index_daily(symbol='sh000001')
idx['date'] = pd.to_datetime(idx['date']); idx = idx.set_index('date').sort_index()
cache = os.path.join(BASE,'百日新高系统','kline_cache')
sm = json.load(open(os.path.join(BASE,'百日新高系统','sector_map.json'),encoding='utf-8'))
all_files = glob.glob(os.path.join(cache,'*.pkl'))

TRACKED = {'002156':'通富微电','600584':'长电科技','002185':'华天科技',
           '000021':'深科技','603728':'鸣志电器','600703':'三安光电'}

def load_df(fpath, dates):
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
    cmn=[d for d in df.index if d in dates]
    if len(cmn)<60: return None
    return df.loc[cmn]

def compute_rps(universe, date):
    """计算各行业RPS(10/20/60)"""
    sec_ret = defaultdict(list)
    for code, info in universe.items():
        df = info['df']; sec = info['sector']
        if date not in df.index: continue
        idx_d = df.index.get_loc(date)
        for w in [10,20,60]:
            if idx_d >= w:
                r = (df['close'].iloc[idx_d]-df['close'].iloc[idx_d-w])/df['close'].iloc[idx_d-w]*100
                sec_ret[(sec,w)].append(r)
    sec_avg = {}
    for (s,w), rets in sec_ret.items():
        if len(rets)>=3: sec_avg[(s,w)] = np.mean(rets)
    rps_out = {}
    for w in [10,20,60]:
        pairs = [(s,v) for (ss,ww),v in sec_avg.items() if ww==w]
        if len(pairs)<3: continue
        vals = [v for _,v in pairs]; ranks = np.argsort(np.argsort(vals))
        for i,(s,_) in enumerate(pairs):
            if s not in rps_out: rps_out[s]={}
            rps_out[s][w] = ranks[i]/max(len(ranks)-1,1)*100
    return rps_out

def compute_nh(universe, date):
    """各行业3日累计百日新高"""
    sec_nh = defaultdict(int)
    for code, info in universe.items():
        df = info['df']; sec = info['sector']
        if date not in df.index: continue
        idx_d = df.index.get_loc(date)
        if idx_d<100: continue
        for back in range(3):
            j = idx_d - back
            if j<100: continue
            c100 = df['close'].iloc[j-100:j+1]
            if df['close'].iloc[j] >= c100.max():
                sec_nh[sec] += 1
    return sec_nh

def get_core_sectors(universe, date, rps_threshold=85):
    """核心主线 = RPS>=85 AND 百日新高Top5"""
    rps = compute_rps(universe, date)
    nh = compute_nh(universe, date)
    qualified = [s for s in rps if all(rps[s].get(w,0)>=rps_threshold for w in [10,20,60])]
    top5 = [s[0] for s in sorted(nh.items(),key=lambda x:x[1],reverse=True)[:5]]
    return [s for s in qualified if s in top5], qualified, top5

# ========= 买点检测 =========
def find_divergence_buy(df, di, idx_d):
    """P1: 启动分歧买点"""
    c=df['close']; h=df.get('high'); l=df.get('low'); a=df.get('amount')
    if h is None or l is None: return []
    res=[]
    for back in range(4):
        j=idx_d-back
        if j<1: continue
        pct=(c.iloc[j]-c.iloc[j-1])/c.iloc[j-1]*100
        if pct<7: continue
        m60j=c.iloc[max(0,j-60):j+1].mean()
        if c.iloc[j]<=m60j: continue
        m60=c.iloc[max(0,idx_d-60):idx_d+1].mean()
        m60p=c.iloc[max(0,idx_d-61):idx_d].mean() if idx_d>=61 else m60
        if m60<m60p*0.98: continue
        dist=(c.iloc[idx_d]-m60)/m60*100
        if dist<-2 or dist>20: continue
        amp=(h.iloc[idx_d]-l.iloc[idx_d])/c.iloc[max(0,idx_d-1)]*100
        if amp<4: continue
        v=df.get('volume')
        if v is not None:
            a5=v.iloc[max(0,idx_d-5):idx_d].mean()
            if a5>0 and v.iloc[idx_d]<a5*1.5: continue
        ma5=c.iloc[max(0,idx_d-5):idx_d+1].mean()
        if c.iloc[idx_d]<=ma5: continue
        if idx_d+2>=len(di): continue
        ni=idx_d+1
        if a is not None and a.iloc[ni]>=a.iloc[idx_d]*0.6: continue
        body=abs(c.iloc[ni]-df['open'].iloc[ni])
        is_small=body<c.iloc[ni]*0.03; is_bull=c.iloc[ni]>=df['open'].iloc[ni]
        if not (is_small or is_bull): continue
        bi=ni+1
        if bi>=len(di): continue
        bp=df['open'].iloc[bi]; bd=di[bi]
        mx=c.iloc[bi:min(bi+21,len(di))].max(); mg=(mx-bp)/bp*100
        # Stop loss
        buy_low=l.iloc[bi]; sl=min(buy_low*0.97, c.iloc[max(0,bi-10):bi+1].mean())
        stopped=False
        for k in range(bi+1,min(bi+21,len(di))):
            if df['low'].iloc[k]<sl: stopped=True; break
        res.append({'type':'P1分歧','buy_date':bd,'buy_p':bp,'max_g':mg,'dist':dist,'stopped':stopped})
        break
    return res

def find_pullback_buy(df, di, bo_idx, ma_type='MA10'):
    """P2/P3: 缩量回踩买点 (MA10 or MA20)"""
    c=df['close']; a=df.get('amount'); res=[]
    ba=a.iloc[bo_idx] if a is not None else 0
    for j in range(bo_idx+2, min(bo_idx+25, len(di))):
        cj=c.iloc[j]; ma=c.iloc[max(0,j-(10 if ma_type=='MA10' else 20)):j+1].mean()
        tolerance=0.02 if ma_type=='MA10' else 0.05
        if abs(cj-ma)/ma>tolerance: continue
        if ba>0 and a is not None and a.iloc[j]>ba*0.5: continue
        if j>=1 and df['low'].iloc[j]<df['low'].iloc[j-1]: continue
        if j+1>=len(di): continue
        bp=df['open'].iloc[j+1]; bd=di[j+1]
        mx=c.iloc[j+1:min(j+21,len(di))].max(); mg=(mx-bp)/bp*100
        # MA30 stop
        sl=c.iloc[max(0,j+1-30):j+2].mean(); stopped=False
        for k in range(j+2,min(j+21,len(di))):
            if df['close'].iloc[k]<sl: stopped=True; break
        res.append({'type':f'P{"2" if ma_type=="MA10" else "3"}回踩{ma_type}','buy_date':bd,'buy_p':bp,'max_g':mg,'stopped':stopped})
        break
    return res

# ========= 主回测 =========
def run_backtest(name, target_sectors, START, END, warm_start):
    print(f'\n{"="*60}')
    print(f'  {name}')
    print(f'{"="*60}')
    warm_dates = idx[warm_start:END].index.tolist()
    dates_all = idx[START:END].index.tolist()
    st_ts = pd.Timestamp(START); ed_ts = pd.Timestamp(END)
    
    # 识别板块股票
    target_codes = set()
    for cd, sc in sm.items():
        cl = cd.replace('sh','').replace('sz','').replace('bj','')
        if any(s in sc for s in target_sectors): target_codes.add(cl)
    
    # 加载universe
    universe = {}
    for f in all_files:
        cd = os.path.basename(f).replace('.pkl','')
        cl = cd.replace('sh','').replace('sz','').replace('bj','')
        c6 = cl[-6:] if len(cl)>=6 else cl
        if c6 not in target_codes and cl not in target_codes: continue
        df = load_df(f, warm_dates)
        if df is None: continue
        sc = sm.get(cd, sm.get(cl, ''))
        universe[cd] = {'df': df, 'sector': sc}
    
    print(f'  {len(universe)} stocks loaded')
    
    # 逐日扫描
    buys = []  # all buy signals
    monthly_core = defaultdict(set)
    
    for d in dates_all:
        if d < st_ts: continue
        # Weekly RPS calibration (Monday)
        rps_thr = 85
        # Get core sectors for this date
        core, _, _ = get_core_sectors(universe, d, rps_thr)
        if core:
            for s in core: monthly_core[d.strftime('%Y-%m')].add(s)
        
        for cd, info in universe.items():
            df = info['df']; di = list(df.index); c = df['close']
            if d not in di: continue
            idx_d = di.index(d)
            if idx_d < 63: continue
            sec = info['sector']
            if core and sec not in core: continue  # 非主线不买
            
            # 突破检测
            m60 = c.iloc[idx_d-60:idx_d+1].mean(); ct = c.iloc[idx_d]
            if ct <= m60: continue
            m1 = c.iloc[idx_d-61:idx_d].mean() if idx_d>=61 else m60
            m2 = c.iloc[idx_d-62:idx_d-1].mean() if idx_d>=62 else m1
            if not (m60 > m1 > m2): continue
            # Volume
            vv = df.get('volume'); vr_ok = True
            if vv is not None and idx_d >= 5:
                a5 = vv.iloc[idx_d-5:idx_d].mean()
                if a5 > 0 and vv.iloc[idx_d] / a5 < 1.5: vr_ok = False
            if not vr_ok: continue
            # 20d gain
            if idx_d >= 20:
                c20 = (ct - c.iloc[idx_d-20]) / c.iloc[idx_d-20] * 100
                if c20 > 30: continue
            # MA60 distance
            ds = (ct - m60) / m60 * 100
            if ds < 0 or ds > 20: continue
            
            # 找到突破！检测所有买点类型
            c6 = cd.replace('sh','').replace('sz','').replace('bj','')[-6:]
            tracked = '★' if c6 in TRACKED else ''
            
            # P1: 分歧买点
            for db in find_divergence_buy(df, di, idx_d):
                db['code'] = c6; db['bo_date'] = d; db['tracked'] = tracked
                buys.append(db)
            
            # P2: 中继买点 (回踩MA10)
            for pb in find_pullback_buy(df, di, idx_d, 'MA10'):
                pb['code'] = c6; pb['bo_date'] = d; pb['tracked'] = tracked
                buys.append(pb)
            
            # P3: 启动买点 (回踩MA20)
            for pb in find_pullback_buy(df, di, idx_d, 'MA20'):
                pb['code'] = c6; pb['bo_date'] = d; pb['tracked'] = tracked
                buys.append(pb)
    
    # 报告
    for ptype in ['P1分歧', 'P2回踩MA10', 'P3回踩MA20']:
        sub = [b for b in buys if b['type'].startswith(ptype.split('回')[0])]
        if not sub: continue
        g = [s['max_g'] for s in sub]; w = sum(1 for x in g if x>5)
        print(f'\n  [{ptype}] {len(sub)}信号 有效(>5%):{w}({w*100//len(sub)}%) 均{np.mean(g):+.1f}% 最高{max(g):+.0f}%')
        for s in sorted(sub, key=lambda x:x['max_g'], reverse=True)[:5]:
            sg = '++' if s['max_g']>15 else ('+' if s['max_g']>5 else '-')
            print(f"    {sg} {s['code']}{s['tracked']} +{s['max_g']:.0f}% {s.get('type','')}")

    # Tracked stocks
    tracked_buys = [b for b in buys if b.get('tracked')]
    print(f'\n  重点关注股票:')
    for tc in TRACKED:
        tb = [b for b in buys if b['code']==tc]
        if tb:
            for b in tb:
                print(f"    {tc} {TRACKED[tc]}: {b['type']} +{b['max_g']:.0f}%")
        else:
            print(f"    {tc} {TRACKED[tc]}: 未触发任何买点")

    # Monthly core sectors
    if monthly_core:
        print(f'\n  逐月核心主线:')
        for m in sorted(monthly_core):
            print(f"    {m}: {', '.join(sorted(monthly_core[m]))}")
    
    return buys

# ========= 运行 =========
print("="*60)
print("  v2.0+ 升级版回测: RPS主线 + 三级买点")
print("="*60)

# 商业航天
aero = run_backtest(
    '商业航天 2025/12 (飞机制造)',
    ['飞机制造'],
    '2025-12-01', '2026-01-31', '2025-09-01'
)

# 半导体
semi = run_backtest(
    '半导体 2026/04 (电子器件+电子信息)',
    ['电子器件', '电子信息'],
    '2026-04-01', '2026-04-30', '2026-01-01'
)

# 对比
print(f"\n{'='*60}")
print(f'  v2.0+ 最终对比')
print(f"{'='*60}")

for nm, buys in [('商业航天', aero), ('半导体', semi)]:
    print(f'\n{nm}:')
    for ptype in ['P1分歧', 'P2回踩MA10', 'P3回踩MA20']:
        sub = [b for b in buys if b['type'].startswith(ptype.split('回')[0])]
        if sub:
            g = [s['max_g'] for s in sub]; w = sum(1 for x in g if x>5)
            print(f'  {ptype}: {len(sub)}信号 有效{w}({w*100//len(sub)}%) 均{np.mean(g):+.1f}% 最高{max(g):+.0f}%')
        else:
            print(f'  {ptype}: 0信号')
    
    total = len(buys)
    if total:
        all_g = [b['max_g'] for b in buys]
        all_w = sum(1 for x in all_g if x>5)
        tracked_hit = sum(1 for b in buys if b.get('tracked'))
        print(f'  合计: {total}信号 有效{all_w}({all_w*100//total}%) 均{np.mean(all_g):+.1f}%  重点股命中:{tracked_hit}只')
