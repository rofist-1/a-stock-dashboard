# -*- coding: utf-8 -*-
"""L3 Gene Scanner - Simple: bottom big yang + break MA60"""
import json, os, sys, time
from datetime import datetime
from collections import defaultdict

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)
from wudao_client_ext import get_kline, get_stock_screener, _get

DATA_DIR = _script_dir
BATCH = 20

def log(msg): print(msg, flush=True)
def sf(v, d=0.0):
    try: return float(v)
    except: return d

def sma(vals, n):
    if len(vals) < n: return None
    return sum(vals[-n:]) / n

def batch_klines(codes, days=120):
    result = {}
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i+BATCH]
        try:
            resp = _get('kline', {'codes': batch, 'days': days})
            items = resp.get('data', {}).get('items', [])
            for item in items:
                if item.get('ok'):
                    code = item.get('stock', {}).get('code', '')
                    result[code] = item.get('data', [])
        except Exception as e:
            log(f'  [batch] {e}')
        time.sleep(1)
    return result

def phase1(date):
    """Phase 1A: Today's big yang + MA60 + volume spike"""
    log('[P1A] Big yang + MA60 + volume...')
    params = {
        'date': date, 'limit': 300, 'excludeST': 'true',
        'aboveMa': [60],
        'volumeRatioMin': 1.5,
        'closePctChgMin': 5,
        'marketCapMinYi': 20,
        'marketCapMaxYi': 500,
        'sortBy': 'closePctChg', 'sortOrder': 'desc',
    }
    stocks = get_stock_screener(params)
    log(f'  Pool: {len(stocks)} stocks')
    return stocks

def phase1_confirm(date):
    """Phase 1B: Stocks that broke out 1-5 days ago, now consolidating
    Criteria: above MA60, low volume today (consolidation), cap 20-500B"""
    log('[P1B] Confirmation pool (post-breakout consolidating)...')
    params = {
        'date': date, 'limit': 300, 'excludeST': 'true',
        'aboveMa': [60],
        'volumeRatioMax': 1.2,  # Low volume today
        'closePctChgMin': -3,   # Not crashing
        'closePctChgMax': 3,    # Not surging either (consolidating)
        'marketCapMinYi': 20,
        'marketCapMaxYi': 500,
        'sortBy': 'volumeRatio', 'sortOrder': 'asc',
    }
    stocks = get_stock_screener(params)
    log(f'  Pool: {len(stocks)} stocks')
    return stocks

def check_recent_breakout(klines):
    """Did this stock have a big yang + volume spike in the last 1-5 days?"""
    if len(klines) < 10: return False, None
    
    for lookback in range(1, 6):
        i = len(klines) - 1 - lookback
        if i < 0: continue
        pct = sf(klines[i].get('pct_chg', 0))
        vol = sf(klines[i].get('amount', 0))
        if pct > 5:
            avg_vol = sum(sf(klines[j].get('amount', 0)) for j in range(max(0, i-5), i)) / 5
            if avg_vol > 0 and vol / avg_vol > 1.3:
                return True, {
                    'date': klines[i].get('date', ''),
                    'pct': round(pct, 1),
                    'days_ago': lookback
                }
    return False, None

def check_pos_quality(klines):
    """Evaluate position quality: low position + consolidation pattern
    Returns (score, details)"""
    if len(klines) < 60: return 0, {}
    
    closes = [sf(k['close']) for k in klines]
    highs = [sf(k['high']) for k in klines]
    current = closes[-1]
    ma60 = sma(closes, 60)
    
    if not ma60 or ma60 <= 0: return 0, {}
    
    details = {}
    
    # 1. 120-day position: prefer 30%-70%
    high_120 = max(highs[-120:]) if len(highs) >= 120 else max(highs)
    low_120 = min(closes[-120:]) if len(closes) >= 120 else min(closes)
    pos_120 = (current - low_120) / (high_120 - low_120) * 100 if high_120 > low_120 else 50
    details['pos120'] = round(pos_120, 0)
    
    # 2. MA60 distance: prefer close to MA60 (< 25%)
    ma60_dist = (current - ma60) / ma60 * 100
    details['ma60_dist'] = round(ma60_dist, 1)
    
    # 3. Recent consolidation: 30-day range < 40% shows consolidation
    range_30 = (max(closes[-30:]) - min(closes[-30:])) / min(closes[-30:]) * 100
    details['range30'] = round(range_30, 1)
    
    # 4. Prior washout in last 40 days
    washout = None
    for i in range(max(0, len(klines)-40), len(klines)-1):
        pct = sf(klines[i].get('pct_chg', 0))
        if pct < -4:
            washout = {'date': klines[i].get('date', ''), 'pct': round(pct, 1)}
    details['wash'] = washout
    
    # 5. MA60 direction
    ma60_prev = sma(closes[:-10], 60)
    if ma60_prev and ma60_prev > 0:
        ma60_trend = (ma60 - ma60_prev) / ma60_prev * 100
        details['ma60_trend'] = round(ma60_trend, 1)
    else:
        details['ma60_trend'] = 0
    
    # Scoring
    score = 50
    if pos_120 >= 30 and pos_120 <= 75:
        score += 15  # good position
    if abs(ma60_dist) < 15:
        score += 15  # close to MA60
    if range_30 < 40:
        score += 10  # consolidation
    if washout:
        score += 10  # prior washout is bullish
    if details['ma60_trend'] >= -2:
        score += 10  # MA60 not severely declining
    
    return score, details

def phase2(stocks, date):
    """Verify and score each candidate"""
    log('[P2] K-line scoring...')
    codes = [s['code'] for s in stocks if s.get('code')]
    log(f'  Fetching {len(codes)} klines...')
    kmap = batch_klines(codes, 120)
    log(f'  Got {len(kmap)}')
    
    results = []
    
    for s in stocks:
        code = s.get('code', '')
        kl = kmap.get(code, [])
        if len(kl) < 60: continue
        
        score, details = check_pos_quality(kl)
        if score < 50: continue  # below average, skip
        
        cur_close = sf(kl[-1]['close'])
        today_vol = sf(kl[-1].get('amount', 0))
        avg10 = sum(sf(k['amount']) for k in kl[-11:-1]) / 10
        vol_r = today_vol / avg10 if avg10 > 0 else 1
        
        results.append({
            'code': code,
            'name': s.get('name', ''),
            'industry': s.get('industry', ''),
            'close': round(cur_close, 2),
            'pct_chg': round(sf(kl[-1].get('pct_chg', 0)), 2),
            'vol_ratio': round(vol_r, 1),
            'amount_yi': round(today_vol / 1e8, 1),
            'score': score,
            'ma60_dist': details['ma60_dist'],
            'pos120': details['pos120'],
            'range30': details['range30'],
            'wash': details['wash'],
            'mcap': round(sf(s.get('marketCapYi', 0)), 1),
        })
    
    results.sort(key=lambda x: -x['score'])
    log(f'  Scored: {len(results)} (score>=50)')
    return results

def report(candidates, confirmed=None):
    if confirmed is None: confirmed = []
    lines = ['# L3 Gene Scanner v6', '',
             '## FIRE Signals (today big yang)',
             f'{len(candidates)} stocks', '']
    
    if not candidates:
        lines.append('No candidates found today.')
        return '\n'.join(lines)
    
    lines.append('Code     Name         Sector        Close   Chg%   VolR  Score  MA60%  Pos120% Range30  Wash  Mcap')
    lines.append('-------- ------------ ------------- ------- ----- ----- -----  ------ ------- ------- ------ --------')
    for c in candidates[:30]:
        wr = f'-{c["wash"]["pct"]}%' if c['wash'] else '-'
        lines.append(
            f'{c["code"]:<8} {c["name"]:<12} {c["industry"][:13]:<13} '
            f'{c["close"]:>6.2f} {c["pct_chg"]:>+5.1f} {c["vol_ratio"]:>5.1f} '
            f'{c["score"]:>5d} {c["ma60_dist"]:>+5.1f}% {c["pos120"]:>5.0f}% '
            f'{c["range30"]:>5.1f}%  {wr:<6} {c["mcap"]:>7.1f}'
        )
    
    lines.append('')
    lines.append('---')
    lines.append('Rules: Bottom big yang + Volume spike + MA60 breakthrough + Not at peak')
    return '\n'.join(lines)

def run(date=None):
    date = date or datetime.now().strftime('%Y%m%d')
    t0 = time.time()
    print('=' * 60)
    print(f'  L3 - Big Yang + MA60 Break + Confirm')
    print(f'  Date: {date[:4]}-{date[4:6]}-{date[6:8]}')
    print('=' * 60)
    print()
    
    # Pool A: Today's breakout
    p1a = phase1(date)
    print()
    p2a = phase2(p1a, date)
    print()
    
    # Pool B: Post-breakout confirmation (broke out 1-5 days ago)
    p1b = phase1_confirm(date)
    print()
    
    log('[P2B] Checking recent breakout history...')
    codes_b = [s['code'] for s in p1b if s.get('code')]
    kmap_b = batch_klines(codes_b, 80)
    confirmed = []
    for s in p1b:
        code = s.get('code', '')
        kl = kmap_b.get(code, [])
        if len(kl) < 60: continue
        ok, brk = check_recent_breakout(kl)
        if not ok: continue
        score, details = check_pos_quality(kl)
        if score < 50: continue
        
        cur_close = sf(kl[-1]['close'])
        confirmed.append({
            'code': code, 'name': s.get('name', ''),
            'industry': s.get('industry', ''),
            'close': round(cur_close, 2),
            'pct_chg': round(sf(kl[-1].get('pct_chg', 0)), 2),
            'break_date': brk['date'], 'break_pct': brk['pct'],
            'days_ago': brk['days_ago'],
            'score': score, 'ma60_dist': details['ma60_dist'],
            'mcap': round(sf(s.get('marketCapYi', 0)), 1),
        })
    confirmed.sort(key=lambda x: -x['score'])
    log(f'  Confirmed: {len(confirmed)} stocks')
    print()
    
    # Report
    r = report(p2a, confirmed)
    elapsed = time.time() - t0
    log(f'\nTotal: {elapsed:.1f}s')
    print()
    print(r)
    
    path = os.path.join(DATA_DIR, f'l3_scan_{date}.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(r)
    log(f'\nSaved: {path}')

if __name__ == '__main__':
    d = None
    for i, a in enumerate(sys.argv):
        if a == '--date' and i+1 < len(sys.argv):
            d = sys.argv[i+1]
    run(date=d)
