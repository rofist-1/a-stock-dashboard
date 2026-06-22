# -*- coding: utf-8 -*-
"""
容量核心监测
===========
扫 kline_cache → 识别容量核心票（成交额≥10亿+热点板块+MA60附近放量启动）
输出: 底部放量_YYYYMMDD.json (兼容看板)
"""

import sys, os, json, pickle, io, re, time
from datetime import datetime, date
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(DATA_DIR, 'kline_cache')

try:
    import akshare as ak
    _HAS_AK = True
except ImportError:
    _HAS_AK = False

def fetch_hot_concept_stocks():
    """用akshare获取今日热点概念成分股，返回 {stock_code: [concept_names]}"""
    hot_stock_codes = {}
    seen_names = set()
    if not _HAS_AK:
        return hot_stock_codes, seen_names
    try:
        boards = ak.stock_board_concept_name_em()
        if boards is None or boards.empty:
            return hot_stock_codes, seen_names
        if "涨停数" in boards.columns:
            hot = boards.sort_values("涨停数", ascending=False).head(8)
        else:
            hot = boards.head(8)
        print('  概念板块API: {}只候选, 取top8'.format(len(boards)))
        for _, br in hot.iterrows():
            bname = str(br.get("板块名称", ""))
            bcode = str(br.get("板块代码", ""))
            if not bcode: continue
            seen_names.add(bname)
            try:
                cons = ak.stock_board_concept_cons_em(symbol=bcode)
                if cons is not None and not cons.empty:
                    for _, cr2 in cons.iterrows():
                        ccode = str(cr2.get("股票代码", "")).zfill(6)
                        if ccode and len(ccode) == 6:
                            hot_stock_codes.setdefault(ccode, []).append(bname)
            except:
                pass
    except Exception:
        pass
    return hot_stock_codes, seen_names

def safe_float(v, default=0):
    try: return float(v)
    except: return default

def load_json_map(fname, key_field='code', val_field=None):
    """Load a JSON file into a dict mapping code→name or code→sector"""
    fpath = os.path.join(DATA_DIR, fname)
    if not os.path.exists(fpath):
        return {}
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        if val_field:
            return {item[key_field]: item.get(val_field, '') for item in data if key_field in item}
        return {item[key_field]: item.get(list(item.keys())[1], '') for item in data if key_field in item}
    elif isinstance(data, dict):
        return data
    return {}

def _find_val(df, names, default=None):
    """Search for first matching indicator name across all categories."""
    for _, row in df.iterrows():
        ind = str(row.iloc[1]).strip()
        if ind in names:
            return safe_float(row.iloc[2], default)
    return default

def fetch_fundamental_one(stock, price):
    code_raw = stock['code'].split('.')[0]
    try:
        df = ak.stock_financial_abstract(symbol=code_raw)
        if df is None or df.empty:
            return {}
        
        roe = _find_val(df, ['净资产收益率(ROE)', '净资产收益率', 'ROE'])
        eps = _find_val(df, ['基本每股收益', '稀释每股收益', '每股收益'])
        nav_ps = _find_val(df, ['每股净资产', '每股净资产_最新股本', '每股净资产_期末股本'])
        debt = _find_val(df, ['资产负债率', '资产负责率'])
        net_profit = _find_val(df, ['净利润'])
        revenue = _find_val(df, ['营业收入', '营业总收入'])
        net_margin = (net_profit / revenue * 100) if (net_profit and revenue and revenue != 0) else None
        
        result = {
            'roe': round(roe, 2) if roe else None,
            'eps': round(eps, 4) if eps else None,
            'nav_ps': round(nav_ps, 2) if nav_ps else None,
            'debt_ratio': round(debt, 1) if debt else None,
            'net_margin': round(net_margin, 1) if net_margin else None,
        }
        if eps and eps > 0 and price:
            result['pe'] = round(price / eps, 1)
        else:
            result['pe'] = None
        return result
    except:
        return {}

def fetch_fundamentals(stocks, with_fundamentals=False):
    """Add quality score and optionally fetch fundamentals."""
    if not _HAS_AK:
        for s in stocks:
            s.update({'quality': None, 'roe': None, 'pe': None, 'nav_ps': None, 'debt_ratio': None, 'net_margin': None})
        return stocks
    
    if not with_fundamentals:
        # Technical-only quality: 百日新高=强势, 低于MA60=价值
        for s in stocks:
            score = 0
            if s.get('in_new_high'): score += 2
            pm = s.get('pct_from_ma60', 0)
            if pm < 0: score += 1  # 低于MA60 = 低估
            elif pm < 3: score += 1  # 回踩确认 = 安全
            s['quality'] = 'A' if score >= 3 else 'B' if score >= 1 else 'C'
            s['roe'] = None; s['pe'] = None; s['nav_ps'] = None; s['debt_ratio'] = None; s['net_margin'] = None
        return stocks
    
    print(f'  获取 {len(stocks)} 只股票基本面数据（耗时较长）...')
    for i, s in enumerate(stocks):
        price = s.get('close', 0)
        fin = fetch_fundamental_one(s, price)
        s.update(fin)
        
        # Quality score
        score = 0
        roe = s.get('roe')
        pe = s.get('pe')
        debt = s.get('debt_ratio')
        nm = s.get('net_margin')
        if s.get('in_new_high'): score += 1
        if roe and roe > 5: score += 1
        if pe and 5 < pe < 50: score += 1
        if debt and debt < 60: score += 1
        if nm and nm > 10: score += 1
        
        if score >= 3: s['quality'] = 'A'
        elif score >= 1: s['quality'] = 'B'
        else: s['quality'] = 'C'
        
        if (i+1) % 5 == 0:
            print(f'    {i+1}/{len(stocks)}')
        time.sleep(1.5)  # rate limit
    print(f'  基本面完成: A级{sum(1 for s in stocks if s["quality"]=="A")} / B级{sum(1 for s in stocks if s["quality"]=="B")} / C级{sum(1 for s in stocks if s["quality"]=="C")}')
    return stocks

def analyze():
    script_date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    select_date = datetime.now().strftime('%Y-%m-%d')
    today_str = str(date.today())
    date_str = today_str.replace('-', '')
    
    # Load reference maps
    name_map = load_json_map('stock_list.json')  # code → name
    sector_map = load_json_map('sector_map.json')  # code → sector
    
    # 扫描缓存，找出所有kline的最后交易日
    cache_files = [f for f in os.listdir(CACHE) if f.endswith('.pkl')]
    print(f'K线缓存: {len(cache_files)} 只')
    actual_trade_date = None
    # 抽检足够多（200只）找出最新交易日
    import random as _rr
    _rr.seed(0)
    sampled = _rr.sample(cache_files, min(200, len(cache_files)))
    for fname in sampled:
        try:
            with open(os.path.join(CACHE, fname), 'rb') as f:
                kd = pickle.load(f)
            df = kd.get('df')
            if df is None or len(df) < 5: continue
            last = df['date'].iloc[-1]
            if isinstance(last, date):
                if actual_trade_date is None or last > actual_trade_date:
                    actual_trade_date = last
        except: pass

    # 确定 trade_day (K线实际交易日) — 后续全局用此值
    if actual_trade_date:
        trade_day = str(actual_trade_date)
        trade_day_str = trade_day.replace('-', '')
    else:
        trade_day = today_str
        trade_day_str = date_str
        actual_trade_date = date.today()
    if trade_day != today_str:
        print(f'  数据实际交易日: {trade_day} (系统日期{today_str}可能非交易日)')
    else:
        print(f'  数据实际交易日: {trade_day}')
    date_str = trade_day_str  # 统一 trade_day 作为文件名日期
    
    # Load latest 百日新高 for cross-reference (自动找最近)
    nh_path = os.path.join(DATA_DIR, f'百日新高_{date_str}.json')
    if not os.path.exists(nh_path):
        import glob as _g
        nh_candidates = _g.glob(os.path.join(DATA_DIR, '百日新高_2*.json'))
        if nh_candidates:
            nh_path = max(nh_candidates, key=os.path.getmtime)
    nh_stocks = set()
    nh_sector_counts = {}
    nh_data = None
    if os.path.exists(nh_path):
        try:
            nh_data = json.load(open(nh_path, 'r', encoding='utf-8'))
            nh_stocks = {s['code'] for s in nh_data.get('stocks', [])}
            # Count sectors from 百日新高
            for s in nh_data.get('stocks', []):
                sc = s.get('sector', '') or ''
                if sc:
                    nh_sector_counts[sc] = nh_sector_counts.get(sc, 0) + 1
        except: pass
    
    results = []
    checked = 0
    for fname in cache_files:
        fpath = os.path.join(CACHE, fname)
        try:
            with open(fpath, 'rb') as f:
                kdata = pickle.load(f)
        except:
            continue
        
        df = kdata.get('df')
        if df is None or len(df) < 60:
            continue
        
        closes = df['close'].tolist()
        dates_list = df['date'].tolist()
        volumes = df['volume'].tolist()
        amounts = df['amount'].tolist()
        opens = df['open'].tolist()
        highs = df['high'].tolist()
        lows = df['low'].tolist()
        
        # 匹配实际交易日
        last_date = dates_list[-1]
        if isinstance(last_date, date):
            last_date_str = str(last_date)
        else:
            continue
        
        # 跳过：数据日期 ≠ 检测到的实际交易日
        if actual_trade_date and last_date != actual_trade_date:
            continue
        
        # 以全局 trade_day 为准（所有stock共享同一交易日）
        stock_trade_day = trade_day
        
        checked += 1
        
        # 今日涨幅
        today_open = safe_float(opens[-1])
        today_close = safe_float(closes[-1])
        today_high = safe_float(highs[-1])
        today_low = safe_float(lows[-1])
        today_vol = safe_float(volumes[-1])
        
        if today_open <= 0:
            continue
        
        change = (today_close - today_open) / today_open * 100
        
        # 今日成交额
        today_amount = safe_float(amounts[-1])
        
        # 条件1: 成交额 ≥ 10亿 (容量核心前提)
        if today_amount < 1e9:
            continue
        
        # 条件2: 今天涨幅 > 5% (容纳非涨停大阳线)
        if change < 5:
            continue
        
        # 60日最低价 (不含今天)
        recent_60_low = min(lows[-60:-1]) if len(lows) > 60 else min(lows[:-1])
        surge_from_low = (today_close - recent_60_low) / recent_60_low * 100
        
        # 今日量 vs 60日均量
        avg_vol_60 = sum(volumes[-60:-1]) / 60 if len(volumes) > 60 else sum(volumes[:-1]) / max(len(volumes)-1, 1)
        vol_ratio = today_vol / avg_vol_60 if avg_vol_60 else 0
        
        # 条件3: 放量 > 2倍 (更强资金确认)
        if vol_ratio < 2.0:
            continue
        
        # 计算MA60
        ma60 = sum(closes[-60:]) / 60
        pct_from_ma60 = (today_close - ma60) / ma60 * 100
        
        # 条件4: 距MA60 -5% ~ +15% (不追高, 不偏离太远)
        if pct_from_ma60 < -5 or pct_from_ma60 > 15:
            continue
        
        # MA60方向
        if len(closes) >= 70:
            ma60_ago = sum(closes[-70:-10]) / 60
            ma60_change = (ma60 - ma60_ago) / ma60_ago * 100
            if ma60_change > 0.5: ma60_dir = '上升'
            elif ma60_change < -0.5: ma60_dir = '下降'
            else: ma60_dir = '走平'
        else: ma60_dir = '--'
        
        # 股票名称
        code = fname.replace('.pkl', '')
        # Reformat code
        if code.startswith('sh') or code.startswith('sz') or code.startswith('bj'):
            market = code[:2].upper()
            num = code[2:]
            full_code = f'{num}.{market}'
        else:
            full_code = code
        
        name = name_map.get(full_code, '') or name_map.get(full_code.replace('.SH','').replace('.SZ','').replace('.BJ',''), '')
        # 过滤ST股
        if name.startswith('ST') or name.startswith('*ST'):
            continue
        sector = sector_map.get(full_code, '') or sector_map.get(full_code.split('.')[0], '')
        
        results.append({
            'code': full_code,
            'name': name,
            'sector': sector,
            'in_new_high': full_code in nh_stocks,
            'close': round(today_close, 2),
            'change': round(change, 2),
            'amount_yi': round(today_amount / 1e8, 1),
            'vol_ratio_vs_60': round(vol_ratio, 1),
            'surge_from_low': round(surge_from_low, 1),
            'low_60': round(recent_60_low, 2),
            'ma60': round(ma60, 2),
            'pct_from_ma60': round(pct_from_ma60, 1),
            'ma60_dir': ma60_dir,
            'date': last_date_str,
            'trade_day': stock_trade_day,
            'select_date': select_date,
        })
    
    # 板块分析：热门概念（悟道MCP）+ 本日异动板块（底部放量）
    print('  获取今日热点概念成分...')
    hot_concept_map, hot_concept_names = fetch_hot_concept_stocks()
    print('  热点概念股票集: {} 只, 概念数: {}'.format(len(hot_concept_map), len(hot_concept_names)))
    surge_sector_counts = {}
    for r in results:
        sc = r.get('sector', '') or ''
        if sc:
            surge_sector_counts[sc] = surge_sector_counts.get(sc, 0) + 1
    # Top hot sectors from 百日新高 (fallback) + hot concept names from API
    nh_top_sorted = sorted(nh_sector_counts.items(), key=lambda x: -x[1])
    fallback_sectors = {s for s, _ in nh_top_sorted[:7]}
    # Build hot concept name set for sector-name fuzzy matching
    hot_concept_names = set()
    for concepts in hot_concept_map.values():
        for c in concepts:
            hot_concept_names.add(c)
    # 用悟道概念匹配
    for r in results:
        code = r.get('code', '').split('.')[0].zfill(6)
        matched_concepts = hot_concept_map.get(code, [])
        r['hot_concepts'] = matched_concepts
        if matched_concepts:
            r['sector_in_hot'] = True
        else:
            # fallback 1: 百日新高top7 sector
            sc = r.get('sector', '') or ''
            r['sector_in_hot'] = sc in fallback_sectors and bool(sc)
            # fallback 2: sector name matches any hot concept keyword
            if not r['sector_in_hot'] and sc:
                for hcn in hot_concept_names:
                    if sc in hcn or hcn in sc:
                        r['sector_in_hot'] = True
                        r['hot_concepts'] = r.get('hot_concepts', []) + [hcn]
                        break
        r['sector_surge_count'] = surge_sector_counts.get(r.get('sector', ''), 0)
    
    surge_sectors_sorted = sorted(surge_sector_counts.items(), key=lambda x: -x[1])
    
    # 共振板块检测：同一板块≥3只容量核心候选 = 板块共振日
    RESONANCE_MIN = 3
    resonance_groups = []
    for sec, cnt in surge_sectors_sorted:
        if cnt < RESONANCE_MIN: break
        group_stocks = [r for r in results if (r.get('sector','') or '') == sec]
        resonance_groups.append({
            'sector': sec,
            'count': cnt,
            'stocks': group_stocks,
        })
    import sys as _sys
    with_fin = '--fundamentals' in _sys.argv
    results = fetch_fundamentals(results, with_fundamentals=with_fin)
    
    # ── 炒作逻辑 / 题材标签 ──
    SECTOR_CONCEPT = {
        '电子器件': '半导体/消费电子', '电子信息': '信创/软件', '计算机行业': 'AI算力/数字经济',
        '机械行业': '机器人/智能制造', '汽车制造': '智能驾驶/新能源车', '摩托车': '两轮电动车',
        '化工行业': '化工周期/新材料', '化纤行业': '化纤涨价', '有色金属': '有色周期/贵金属',
        '钢铁行业': '钢铁/基建周期', '煤炭行业': '煤炭/能源', '石油行业': '石油/天然气',
        '电力行业': '电力/特高压', '发电设备': '电力装备/新能源', '环保行业': '环保/碳中和',
        '生物制药': '创新药/生物医药', '医疗器械': '医疗设备/国产替代',
        '酿酒行业': '消费/白酒', '食品行业': '大消费/食品', '商业百货': '消费复苏/零售',
        '家电行业': '家电/出海', '服装鞋类': '消费/纺织',
        '房地产': '地产/政策催化', '建筑建材': '基建/一带一路', '水泥行业': '基建/水泥涨价',
        '金融行业': '大金融/券商', '保险行业': '多元金融',
        '交通运输': '物流/交运', '公路桥梁': '基建/交通', '船舶制造': '造船/航运周期',
        '飞机制造': '军工/航空航天', '航天军工': '军工/国防',
        '传媒娱乐': 'AI应用/传媒', '酒店旅游': '旅游/假日经济',
        '农林牧渔': '农业/猪周期', '农药化肥': '化工/化肥涨价',
        '电器行业': '电力设备/充电桩', '仪器仪表': '精密仪器/传感器',
        '开发区': '园区经济/地产', '物资外贸': '外贸/跨境电商',
        '纺织机械': '纺织设备/出海', '纺织行业': '纺织/出口',
        '造纸行业': '造纸/涨价', '印刷包装': '包装/消费',
        '供水供气': '公用事业/水务', '塑料制品': '化工/新材料',
        '玻璃行业': '光伏玻璃/建材', '陶瓷行业': '建材/瓷砖',
        '综合行业': '综合/控股', '次新股': '次新/高送转',
        '家具行业': '家居/地产后周期', '其它行业': '',
        '医疗器械': '医疗设备/出海',
    }
    NAME_KW = [
        ('中电', '央企/信创'), ('中科', '中科院系/科技'), ('中船', '军工/船舶'),
        ('航天', '军工/航天'), ('航发', '军工/航空发动机'), ('中航', '军工/航空'),
        ('长电', '半导体封测'), ('北方华创', '半导体设备'), ('中芯', '半导体/晶圆'),
        ('光刻', '光刻机/国产替代'), ('寒武纪', 'AI芯片'), ('海光', 'CPU/信创'),
        ('金山', 'AI办公/软件'), ('浪潮', 'AI算力/服务器'), ('曙光', '算力/服务器'),
        ('中际', '光模块/AI算力'), ('新易盛', '光模块/AI算力'), ('天孚', '光器件/AI算力'),
        ('宁德', '新能源车/锂电'), ('比亚迪', '新能源车/整车'), ('阳光', '光伏/逆变器'),
        ('通威', '光伏/硅料'), ('隆基', '光伏/组件'), ('晶澳', '光伏/组件'),
        ('茅台', '白酒/消费'), ('五粮液', '白酒/消费'), ('泸州', '白酒/消费'),
        ('药明', 'CXO/创新药'), ('恒瑞', '创新药/肿瘤'), ('迈瑞', '医疗设备'),
        ('美的', '家电/出海'), ('格力', '家电/出海'), ('海尔', '家电/出海'),
        ('科大讯飞', 'AI语音/大模型'), ('海康', '安防/AI视觉'), ('大华', '安防/AI视觉'),
        ('同花顺', '金融科技/AI'), ('东方财富', '券商/金融科技'),
        ('中信证券', '券商/龙头'), ('华泰', '券商/金融科技'),
        ('神华', '煤炭/高股息'), ('长电', '水电/高股息'),
        ('移动', '运营商/AI算力基建'), ('联通', '运营商/数据要素'),
        ('中兴', '通信设备/AI基建'),         ('烽火', '光通信/数据基建'),
        ('鲁信', '创投/金控'), ('贝达', '创新药/生物医药'),
        ('金田', '有色加工/铜材料'), ('思泉', '散热材料/消费电子'),
        ('美年', '医疗服务/体检'), ('双环', '减速器/机器人'),
        ('北方稀土', '稀土/有色周期'), ('赣锋', '锂矿/新能源'),
        ('天齐', '锂矿/新能源'), ('华友', '钴/有色周期'),
        ('中矿', '锂矿/有色'), ('洛阳钼业', '铜钴/有色周期'),
        ('紫金', '黄金/有色周期'), ('山东黄金', '黄金/避险'),
        ('中金', '黄金/有色'), ('西部矿业', '铜/有色周期'),
        ('江西铜业', '铜/有色周期'), ('云铝', '铝/有色周期'),
        ('神火', '铝/煤电一体化'), ('中国铝业', '铝/有色周期'),
        ('宝钢', '钢铁/央企'), ('鞍钢', '钢铁/周期'),
        ('海螺', '水泥/基建'), ('华新', '水泥/基建'),
        ('万华', '化工/MDI龙头'), ('华鲁', '化工/煤化工'),
        ('兴发', '化工/磷化工'), ('云天化', '化工/化肥'),
        ('巨化', '化工/氟化工'), ('宝丰能源', '煤化工/周期'),
        ('传化', '化工/物流'), ('合盛', '硅/化工'),
        ('卫星化学', '化工/轻烃'),
        ('中联重科', '机械/工程机械'), ('三一', '机械/工程机械'),
        ('徐工', '机械/工程机械'), ('恒立', '液压/工程机械'),
        ('汇川', '工控/机器人'), ('绿的谐波', '谐波减速器/机器人'),
        ('拓普', '汽车零部件/机器人'), ('三花', '热管理/机器人'),
        ('鸣志', '电机/机器人'), ('步科', '电机/机器人'),
    ]
    def make_narrative(r):
        nm = (r.get('sector', '') or '') + (r.get('name', '') or '')
        # name keyword match first
        for kw, concept in NAME_KW:
            if kw in nm:
                return concept
        # sector mapping fallback
        sec = r.get('sector', '') or ''
        return SECTOR_CONCEPT.get(sec, sec)
    for r in results:
        r['narrative'] = make_narrative(r)
    
    # ── 综合评分系统 (权重100分) ──
    for r in results:
        pma = r.get('pct_from_ma60', 0) or 0
        vr = r.get('vol_ratio_vs_60', 0) or 0
        md = r.get('ma60_dir', '--')
        amt = r.get('amount_yi', 0) or 0
        nh = r.get('in_new_high', False)
        hot = r.get('sector_in_hot', False)
        sc = r.get('sector', '') or ''
        surge_cnt = r.get('sector_surge_count', 0)
        roe_val = r.get('roe')
        pe_val = r.get('pe')
        
        # ① 成交额 (20分)
        if amt >= 50: s_amt = 20
        elif amt >= 30: s_amt = 16
        elif amt >= 20: s_amt = 12
        elif amt >= 15: s_amt = 8
        else: s_amt = 5
        
        # ② MA60位置 (20分) - 贴线最佳
        if -3 <= pma <= 3: s_ma = 20
        elif -5 <= pma < -3: s_ma = 15
        elif 3 < pma <= 8: s_ma = 12
        elif 8 < pma <= 12: s_ma = 6
        elif 12 < pma <= 15: s_ma = 3
        else: s_ma = 0
        
        # ③ 板块共振 (20分)
        if hot: s_sector = 20
        elif surge_cnt >= 3: s_sector = 12
        elif surge_cnt >= 2: s_sector = 6
        else: s_sector = 0
        
        # ④ 放量倍数 (15分)
        if 2.0 <= vr <= 3.0: s_vol = 15
        elif 3.0 < vr <= 5.0: s_vol = 12
        elif 1.5 <= vr < 2.0: s_vol = 8
        elif 5.0 < vr <= 7.0: s_vol = 5
        else: s_vol = 2
        
        # ⑤ MA60趋势 (10分)
        if md == '上升': s_trend = 10
        elif md == '走平': s_trend = 5
        else: s_trend = 0
        
        # ⑥ 基本面 (10分)
        s_fin = 0
        if roe_val:
            if roe_val > 10: s_fin += 5
            elif roe_val > 5: s_fin += 3
            else: s_fin += 1
        if pe_val:
            if 10 <= pe_val <= 50: s_fin += 3
            elif 50 < pe_val <= 100: s_fin += 1
        debt = r.get('debt_ratio')
        if debt is not None and debt < 50: s_fin += 2
        
        # ⑦ 百日新高加分 (5分)
        s_nh = 5 if nh else 0
        
        total = s_amt + s_ma + s_sector + s_vol + s_trend + s_fin + s_nh
        
        # 评级
        if total >= 80: rating = 'A+'
        elif total >= 65: rating = 'A'
        elif total >= 50: rating = 'B'
        elif total >= 35: rating = 'C'
        else: rating = 'D'
        
        r['score'] = total
        r['rating'] = rating
        r['score_detail'] = {
            '成交额': s_amt, 'MA60位置': s_ma, '板块共振': s_sector,
            '放量倍数': s_vol, '趋势': s_trend, '基本面': s_fin, '百日新高': s_nh
        }
        
        # risk_level/risk_note 保留兼容
        risks = []
        if pma > 12: risks.append('偏离均线')
        if pma < -4: risks.append('均线压制')
        if vr > 5: risks.append('放量过猛')
        if md == '下降': risks.append('趋势未转')
        if amt < 10: risks.append('容量偏小')
        if rating == 'D': risks.append('综合较差')
        if not risks:
            r['risk_level'] = 'A' if rating in ('A+','A') else 'B'
            r['risk_note'] = '较安全'
        elif len(risks) == 1:
            r['risk_level'] = 'B'
            r['risk_note'] = risks[0]
        else:
            r['risk_level'] = 'C'
            r['risk_note'] = ' '.join(risks[:2])
    
    # 过滤: 热点板块 + MA60附近 (pct_from_ma60 -3%~+8%)
    hot_near_ma60 = [r for r in results if r.get('sector_in_hot') and abs(r.get('pct_from_ma60', 0) or 0) < 8]
    
    # 排序: 评分倒序(高分优先)
    results.sort(key=lambda x: -(x.get('score', 0) or 0))
    hot_near_ma60.sort(key=lambda x: -(x.get('score', 0) or 0))
    
    # 评分统计
    rating_counts = Counter()
    for r in results:
        rating_counts[r.get('rating','?')] += 1
    
    output = {
        'trade_day': trade_day,
        'select_date': select_date,
        'mode': '容量核心',
        'total_checked': checked,
        'total_bottom_surge': len(results),
        'total_hot_resonance': len(hot_near_ma60),
        'rating_summary': dict(rating_counts.most_common()),
        'top_stocks': [s['code'] for s in results[:3]],
        'nh_top_sectors': dict(nh_top_sorted[:10]),
        'surge_sectors': dict(surge_sectors_sorted),
        'resonance_groups': resonance_groups,
        'stocks': results,
        'hot_resonance_stocks': hot_near_ma60,
    }
    
    out_path = os.path.join(DATA_DIR, f'底部放量_{trade_day_str}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f'\n行情交易日: {trade_day}  |  选股执行日: {select_date}')
    print(f'检查 {checked} 只, 容量核心候选: {len(results)} 只')
    print(f'其中热点板块+MA60附近: {len(hot_near_ma60)} 只')
    print(f'评分分布: {dict(rating_counts.most_common())}')
    out_path = os.path.join(DATA_DIR, f'底部放量_{trade_day_str}.json')
    print(f'输出: {out_path}')
    for r in results:
        nh = '★' if r['in_new_high'] else ' '
        s = r['sector'] or ''
        n = r['name'] or ''
        md = r.get('ma60_dir', '')
        dir_mark = {'上升': '↗', '下降': '↘', '走平': '→', '--': ''}.get(md, '')
        amt = r.get('amount_yi', 0)
        score = r.get('score', 0)
        rating = r.get('rating', '?')
        rn = r.get('risk_note', '')
        sd = r.get('score_detail', {})
        vr_val = r.get('vol_ratio_vs_60', 0)
        pma_val = r.get('pct_from_ma60', 0)
        narr = r.get('narrative', '')
        narr_tag = f' [{narr}]' if narr else ''
        hc = r.get('hot_concepts', [])
        hc_tag = '🔥' + ','.join(hc[:3]) if hc else ''
        print(f'  {nh}{r["code"]} {n}{narr_tag} [{s}] +{r["change"]}%  {amt}亿 量{vr_val:.1f}x 距MA60{pma_val:.1f}% {dir_mark}  {rating}({score}分) {rn} {hc_tag}')
        print(f'    └ 成交额{sd.get("成交额",0)} MA60{sd.get("MA60位置",0)} 板块{sd.get("板块共振",0)} 放量{sd.get("放量倍数",0)} 趋势{sd.get("趋势",0)} 基本面{sd.get("基本面",0)} 百日新高{sd.get("百日新高",0)}')

if __name__ == '__main__':
    analyze()
