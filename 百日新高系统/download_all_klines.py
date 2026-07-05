# -*- coding: utf-8 -*-
"""
批量下载全量A股K线 (迪雅API)
目标: 2024-06-01 ~ 2026-07-03, 前复权
保存到 kline_cache/
"""
import os, sys, time, json, pickle, glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEY = "4377183a3f71a9eda95741cd2eb8e6a944c6fe90"
BASE_URL = "https://api.cxdy.vip/api"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
CACHE_DIR = r"C:\Users\Rofis\Desktop\百日新高系统\kline_cache"
START_DATE = "2024-06-01"
END_DATE = "2026-07-03"

os.makedirs(CACHE_DIR, exist_ok=True)

def get_stock_list():
    """从迪雅API获取全量股票列表"""
    r = requests.get(f"{BASE_URL}/hslb", headers=HEADERS, timeout=30)
    data = r.json()
    if isinstance(data, list):
        return [(s['code'], s['name']) for s in data]
    return []

def download_kline(code):
    """下载单只股票K线"""
    filename = os.path.join(CACHE_DIR, f"{code}.pkl")
    
    # 检查是否已有完整数据
    if os.path.exists(filename):
        try:
            with open(filename, 'rb') as f:
                existing = pickle.load(f)
            if isinstance(existing, dict) and 'df' in existing:
                df = existing['df']
                if hasattr(df, 'iloc') and len(df) > 400:
                    # 已有足够数据，检查日期范围
                    return (code, 'cached', len(df))
        except:
            pass
    
    # 判断交易所前缀
    prefix = 'sz' if code.startswith(('0','3')) else 'sh'
    if code.startswith(('4','8','9')):
        prefix = ''  # 北交所等其他
    
    symbol = f"{prefix}{code}" if prefix else code
    
    try:
        params = {
            'symbol': symbol,
            'start_date': START_DATE,
            'end_date': END_DATE,
            'adjust': 'qfq'
        }
        r = requests.get(f"{BASE_URL}/lsjy", headers=HEADERS, params=params, timeout=20)
        
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                import pandas as pd
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)
                
                with open(filename, 'wb') as f:
                    pickle.dump({'code': code, 'df': df}, f)
                return (code, 'ok', len(df))
            else:
                return (code, 'empty', 0)
        else:
            return (code, f'http_{r.status_code}', 0)
    except Exception as e:
        return (code, str(e), 0)

def main():
    print("=" * 50)
    print("  迪雅API 批量K线下载")
    print("=" * 50)
    
    # 1. 获取股票列表
    print("\n[1] 获取股票列表...")
    stocks = get_stock_list()
    print(f"  共 {len(stocks)} 只股票")
    
    if not stocks:
        print("  股票列表获取失败!")
        return
    
    # 2. 过滤已有缓存的 (检查最新日期)
    to_download = []
    already_ok = 0
    for code, name in stocks:
        fp = os.path.join(CACHE_DIR, f"{code}.pkl")
        if os.path.exists(fp):
            try:
                with open(fp, 'rb') as f:
                    existing = pickle.load(f)
                if isinstance(existing, dict) and 'df' in existing:
                    df = existing['df']
                    if hasattr(df, 'iloc') and len(df) > 400:
                        last_date = str(df['date'].iloc[-1])[:10]
                        if last_date >= '2026-07-01':
                            already_ok += 1
                            continue
            except:
                pass
        to_download.append(code)
    
    print(f"  已有最新数据: {already_ok} 只")
    print(f"  需要下载: {len(to_download)} 只")
    
    if not to_download:
        print("\n  所有股票已是最新数据!")
        return
    
    # 3. 并发下载
    print(f"\n[2] 并发下载 ({min(20, len(to_download))} 线程)...")
    start = time.time()
    
    ok_count = 0
    err_count = 0
    cached_count = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_kline, code): code for code in to_download}
        for i, future in enumerate(as_completed(futures)):
            code, status, rows = future.result()
            if status == 'ok':
                ok_count += 1
            elif status == 'cached':
                cached_count += 1
            else:
                err_count += 1
            
            if (i + 1) % 500 == 0 or (i + 1) <= 10:
                elapsed = time.time() - start
                speed = (i + 1) / elapsed if elapsed > 0 else 0
                pct = (i + 1) / len(to_download) * 100
                eta = (len(to_download) - i - 1) / speed if speed > 0 else 0
                print(f"  [{pct:.0f}%] {i+1}/{len(to_download)} | ok={ok_count} err={err_count} | {speed:.0f}/s ETA:{eta:.0f}s")
    
    elapsed = time.time() - start
    total = len(to_download)
    print(f"\n  完成! 耗时: {elapsed:.0f}s ({total/elapsed:.1f}/s)")
    print(f"  下载成功: {ok_count} | 已有缓存: {cached_count} | 失败: {err_count}")

if __name__ == '__main__':
    main()
