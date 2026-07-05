# -*- coding: utf-8 -*-
"""v2.0复盘: 半导体4月行情 (修复版)"""
import sys,os,pickle,glob,json,requests
from collections import defaultdict
import numpy as np
import pandas as pd

BASE = r'C:\Users\Rofis\Desktop'
os.chdir(BASE)

# ========= 数据加载 =========
import akshare as ak
idx = ak.stock_zh_index_daily(symbol='sh000001')
idx['date'] = pd.to_datetime(idx['date'])
idx = idx.set_index('date').sort_index()
idx = idx['2026-01-01':'2026-06-30']
ma20_idx = idx['close'].rolling(20).mean()
dates_all = idx.index.tolist()

cache = os.path.join(BASE,'百日新高系统','kline_cache')
sector_fp = os.path.join(BASE,'百日新高系统','sector_map.json')
sector_map = json.load(open(sector_fp,'r',encoding='utf-8')) if os.path.exists(sector_fp) else {}

START='2026-03-01'; END='2026-06-30'

# ========= 从迪雅API获取股票名称映射 =========
name_map = {}
try:
    resp = requests.get('https://api.cxdy.vip/api/hslb', 
                        headers={'Authorization':'Bearer 4377183a3f71a9eda95741cd2eb8e6a944c6fe90'},
                        timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list):
            for s in data:
                name_map[s['code']] = s.get('name','')
            print(f"股票名称映射: {len(name_map)}只")
except Exception as e:
    print(f"名称映射获取失败: {e}")

# ========= 芯片/半导体识别 =========
CHIP_SECTORS = ['电子器件', '电子信息', '电子制造', '元器件', '半导体']
TRACK_CODES = {'002156':'通富微电','600584':'长电科技','002185':'华天科技','600703':'三安光电',
               '603986':'兆易创新', '603501':'韦尔股份'}

all_files = glob.glob(os.path.join(cache, '*.pkl'))
print("="*70)
print("  v2.0 系统复盘：2026年4月 半导体/芯片行情")
print("="*70)

# ========= 大盘 =========
print("\n## 一、大盘状态与仓位上限\n")
print("| 月份 | 上涨日 | 震荡日 | 下跌日 | 主导 | 仓位 |")
print("|------|--------|--------|--------|------|------|")

prev_st=None; sd={}
for m in ['2026-03','2026-04','2026-05','2026-06']:
    cnt={'上涨':0,'震荡':0,'下跌':0}
    for d in dates_all:
        if d.strftime('%Y-%m')!=m: continue
        i=idx.index.get_loc(d)
        if i<60: continue
        c=idx['close'].iloc[i]; m20=ma20_idx.iloc[i]
        rising = ma20_idx.iloc[i] > ma20_idx.iloc[max(0,i-1)] > ma20_idx.iloc[max(0,i-2)] if i>=2 else False
        a1=c>m20 and rising; a2=a1; a3=True
        votes=3 if a1 and a3 else (1 if a3 else 0)
        if votes>=2: tgt='上涨'; pos=0.7
        elif votes==0: tgt='下跌'; pos=0.0
        else: tgt='震荡'; pos=0.3
        if tgt==prev_st: sd[tgt]=sd.get(tgt,0)+1
        else: sd={tgt:1}
        if sd.get(tgt,0)>=2 or prev_st is None: prev_st=tgt
        cnt[prev_st]+=1
    dom=max(cnt,key=cnt.get); p={'上涨':70,'震荡':30,'下跌':0}[dom]
    print(f"| {m} | {cnt['上涨']:>6} | {cnt['震荡']:>6} | {cnt['下跌']:>6} | {dom} | {p}% |")

# ========= 识别芯片股 =========
print("\n## 二、半导体/芯片相关股票 (4月)\n")
print("| 代码 | 名称 | 行业 | 月初 | 月底 | 涨跌 | MA60站上 |")
print("|------|------|------|------|------|------|----------|")

chip_codes = set()
for code, sec in sector_map.items():
    clean = code.replace('sh','').replace('sz','').replace('bj','')
    # 行业匹配
    if any(s in sec for s in CHIP_SECTORS):
        chip_codes.add(clean)
    # 追踪股票
    if clean in TRACK_CODES:
        chip_codes.add(clean)

chip_stocks = []
for f in all_files:
    try:
        code = os.path.basename(f).replace('.pkl','')
        clean = code.replace('sh','').replace('sz','').replace('bj','')
        if clean[-6:] not in chip_codes and clean not in chip_codes:
            continue

        with open(f,'rb') as fh:
            df_data = pickle.load(fh)
        df = df_data.get('df', df_data) if isinstance(df_data, dict) else df_data
        if not hasattr(df,'iloc') or len(df) < 100: continue

        cols_l = {c.lower(): c for c in df.columns}
        dc = cols_l.get('date', None)
        if dc is None: continue

        df['date'] = pd.to_datetime(df[dc])
        df = df.set_index('date').sort_index()
        df = df[~df.index.duplicated()]

        # 标准化close
        for cn in df.columns:
            if cn.lower() == 'close':
                df['close'] = pd.to_numeric(df[cn], errors='coerce')
                break
        if 'close' not in df.columns: continue

        cmn = [d for d in df.index if d in dates_all]
        if len(cmn) < 60: continue
        closes = df['close'].loc[cmn]

        if pd.Timestamp('2026-04-01') not in cmn or pd.Timestamp('2026-04-30') not in cmn:
            continue

        i0 = cmn.index(pd.Timestamp('2026-04-01'))
        i1 = cmn.index(pd.Timestamp('2026-04-30'))
        c0 = closes.iloc[i0]; c1 = closes.iloc[i1]
        chg = (c1 - c0) / c0 * 100

        crossed = False
        for j in range(i0, i1+1):
            m60 = closes.iloc[max(0,j-60):j+1].mean()
            if closes.iloc[j] > m60 and j >= 61:
                m1 = closes.iloc[max(0,j-61):j].mean()
                m2 = closes.iloc[max(0,j-62):j-1].mean()
                if m60 > m1 > m2:
                    crossed = True; break

        c6 = clean[-6:] if len(clean) >= 6 else clean
        name = name_map.get(c6, name_map.get(clean, ''))
        sec_val = sector_map.get(code, sector_map.get(clean, ''))
        tag = ' ★' if (c6 in TRACK_CODES or clean in TRACK_CODES) else ''

        chip_stocks.append({
            'code': code, 'clean': c6, 'name': name, 'sec': sec_val,
            'c0': c0, 'c1': c1, 'chg': chg, 'crossed': crossed,
            'file': f
        })

        print(f"| {c6:>6} | {name:8s} | {sec_val:6s} | {c0:>6.1f} | {c1:>6.1f} | {chg:>+6.1f}% | {'✓' if crossed else '✗'}{tag} |")
    except Exception as e:
        pass

print(f"\n> {len(chip_stocks)}只芯片股, {sum(1 for c in chip_stocks if c['crossed'])}只站上MA60")
print(f"> {sum(1 for c in chip_stocks if c['chg']>20)}只4月涨幅>20%")

# ========= 突破观测池 =========
print(f"\n## 三、大阳线站上60日线 · 突破观测池 (4月)\n")
print("| 代码 | 名称 | 突破日 | 价 | MA60 | 距% | 量比 | 标签 |")
print("|------|------|--------|-----|------|-----|------|------|")

bos_list = []
for cs in chip_stocks:
    f = cs['file']; code = cs['code']; name = cs['name']; c6 = cs['clean']
    with open(f, 'rb') as fh:
        df_data = pickle.load(fh)
    df = df_data.get('df', df_data) if isinstance(df_data, dict) else df_data
    cols_l = {c.lower(): c for c in df.columns}
    dc = cols_l.get('date', None)
    if dc is None: continue
    df['date'] = pd.to_datetime(df[dc])
    df = df.set_index('date').sort_index()
    # Standardize columns
    for std in ['close','volume','amount']:
        for cn in df.columns:
            if cn.lower() == std:
                df[std] = pd.to_numeric(df[cn], errors='coerce')
                break

    cmn = [d for d in df.index if d in dates_all]
    if len(cmn) < 60: continue
    closes = df['close'].loc[cmn] if 'close' in df.columns else None
    if closes is None: continue
    vols = df.get('volume', None)
    if vols is not None: vols = vols.loc[cmn]

    apr_dates = [d for d in cmn if pd.Timestamp('2026-04-01') <= d <= pd.Timestamp('2026-04-30')]
    found_bo = False
    for d in apr_dates:
        if found_bo: break
        idx_d = cmn.index(d)
        if idx_d < 60: continue
        m60 = closes.iloc[idx_d-60:idx_d+1].mean()
        ct = closes.iloc[idx_d]
        if ct <= m60: continue
        # MA60走高
        if idx_d < 62: continue
        m1 = closes.iloc[idx_d-61:idx_d].mean()
        m2 = closes.iloc[idx_d-62:idx_d-1].mean()
        if not (m60 > m1 > m2): continue
        # Volume
        vr = 0
        if vols is not None and idx_d >= 5:
            avg5 = vols.iloc[idx_d-5:idx_d].mean()
            if avg5 > 0:
                vr = vols.iloc[idx_d] / avg5
                if vr < 1.5: continue
        # 20d gain
        if idx_d >= 20:
            chg20 = (closes.iloc[idx_d] - closes.iloc[idx_d-20]) / closes.iloc[idx_d-20] * 100
            if chg20 > 30: continue
        # MA60 distance
        dist = (ct - m60) / m60 * 100
        if dist < 0 or dist > 20: continue

        tag = '★' if (c6 in TRACK_CODES) else ''
        bos_list.append({
            'code': code, 'c6': c6, 'name': name, 'date': str(d)[:10],
            'close': ct, 'ma60': m60, 'dist': dist, 'vr': vr, 'tag': tag
        })
        found_bo = True

    if found_bo:
        b = bos_list[-1]
        print(f"| {b['c6']:>6} | {b['name']:8s} | {b['date']} | {b['close']:>5.1f} | {b['ma60']:>5.1f} | {b['dist']:>+4.1f}% | {b['vr']:>4.2f} | {b['tag']} |")

if not bos_list:
    print("| — | (无突破信号) | | | | | | |")
print(f"\n> {len(bos_list)}个突破信号")

# ========= 回调买点 =========
print(f"\n## 四、缩量回踩买点\n")
print("| 股票 | 突破日 | 回调日 | 买入日 | 买入价 | 最高涨幅 | 判定 |")
print("|------|--------|--------|--------|--------|----------|------|")

buy_count = 0
for b in bos_list:
    cs_info = next((c for c in chip_stocks if c['code'] == b['code']), None)
    if cs_info is None: continue
    f = cs_info['file']
    with open(f, 'rb') as fh:
        df_data = pickle.load(fh)
    df = df_data.get('df', df_data) if isinstance(df_data, dict) else df_data
    cols_l = {c.lower(): c for c in df.columns}
    dc = cols_l.get('date', None)
    if dc is None: continue
    df['date'] = pd.to_datetime(df[dc])
    df = df.set_index('date').sort_index()
    for std in ['close','open','high','low','amount']:
        for cn in df.columns:
            if cn.lower() == std:
                df[std] = pd.to_numeric(df[cn], errors='coerce')
                break
    cmn = [d for d in df.index if d in dates_all]
    if len(cmn) < 60: continue
    for col_name in df.columns:
        if 'close' in col_name.lower():
            df['close'] = pd.to_numeric(df[col_name], errors='coerce')
            break
    if 'close' not in df.columns: continue

    bo_date = pd.Timestamp(b['date'])
    if bo_date not in cmn: continue
    bo_idx = cmn.index(bo_date)
    bo_amt = df['amount'].iloc[bo_idx] if 'amount' in df.columns else None

    closes_s = df['close'].loc[cmn]
    found = False
    for j in range(bo_idx + 2, min(bo_idx + 25, len(cmn))):
        cj = closes_s.iloc[j]
        ma10 = closes_s.iloc[max(0, j-10):j+1].mean()
        ma20 = closes_s.iloc[max(0, j-20):j+1].mean()
        # 缩量
        if bo_amt and 'amount' in df.columns:
            amt_j = df['amount'].iloc[j]
            if amt_j > bo_amt * 0.5: continue
        # 回踩
        at10 = abs(cj - ma10) / ma10 <= 0.02 if ma10 > 0 else False
        at20 = abs(cj - ma20) / ma20 <= 0.05 if ma20 > 0 else False
        if not (at10 or at20): continue
        # 止跌
        if 'low' in df.columns and j >= 1:
            if df['low'].iloc[j] < df['low'].iloc[j-1]: continue
        buy_idx = j + 1
        if buy_idx >= len(cmn): continue
        buy_d = cmn[buy_idx]
        if buy_d > pd.Timestamp(END): continue
        buy_p = df['open'].iloc[buy_idx] if 'open' in df.columns else closes_s.iloc[buy_idx]
        mx = closes_s.iloc[buy_idx:min(buy_idx+60, len(cmn))].max()
        mx_g = (mx - buy_p) / buy_p * 100
        sym = '✓成功' if mx_g > 10 else ('△一般' if mx_g > 5 else ('✗失败' if mx_g < 0 else '○中性'))
        print(f"| {b['name']:8s} | {b['date']} | {str(cmn[j])[:10]} | {str(buy_d)[:10]} | {buy_p:>6.2f} | {mx_g:>+7.1f}% | {sym} |")
        buy_count += 1; found = True; break

if not buy_count:
    print("| — | (无缩量回踩买点) | | | | | |")

# ========= 追踪重点股票 =========
print(f"\n## 五、重点关注股票 (通富微电/长电科技等)\n")
print("| 代码 | 名称 | 在芯片池 | 在突破池 | 在买点 | 4月涨跌 |")
print("|------|------|----------|----------|--------|---------|")

for tc, name in TRACK_CODES.items():
    in_chip = any(tc == c['clean'] for c in chip_stocks)
    in_bos = any(tc == b['c6'] for b in bos_list)
    chg_val = next((c['chg'] for c in chip_stocks if c['clean'] == tc), 0)
    inv = '✓' if in_chip else '✗'
    bsv = ('✓ (' + str(sum(1 for b in bos_list if b['c6']==tc)) + '个)') if in_bos else '✗'
    byv = '需检测' if in_bos else '—'
    print(f"| {tc:>6} | {name:8s} | {inv:>8} | {bsv:>10} | {byv:>6} | {chg_val:>+6.1f}% |")

# ========= 总结 =========
print(f"\n## 六、总结\n")
print(f"芯片池: {len(chip_stocks)}只 | 4月涨>20%: {sum(1 for c in chip_stocks if c['chg']>20)}只")
print(f"突破信号: {len(bos_list)}个 | 回调买点: {buy_count}个")
print(f"\n系统评价：")
print(f"  - 大盘: 4月全月震荡, 仓位上限30%")
if len(bos_list) > 0:
    print(f"  - 板块识别: 有效, 识别到{len(chip_stocks)}只芯片/电子器件股")
    print(f"  - 突破信号: {len(bos_list)}个, 过滤标准(量比1.5/20日涨<30%/距MA60 0-20%)")
else:
    print(f"  - 突破信号: 无。过滤条件过于严格或股票数据不足")
if buy_count > 0:
    print(f"  - 买点: 系统捕捉到{buy_count}个缩量回踩买点")
else:
    print(f"  - 买点: 4月芯片行情可能缺乏经典缩量回踩形态")
print("="*70)
