import akshare as ak
import json

# Step 1: Get all concept board names and codes
boards = ak.stock_board_concept_name_em()
board_map = {}
for _, row in boards.iterrows():
    board_map[row['板块名称']] = row['板块代码']
print(f"Total boards: {len(board_map)}")

# Step 2: Our hot sector names across 10 days
daily_hot_sectors = {
    "06-30": ["芯片概念", "机器人概念", "华为概念", "新能源汽车", "专精特新", "人工智能", "比亚迪概念", "消费电子概念"],
    "06-29": ["芯片概念", "创新药", "专精特新", "一带一路", "新能源汽车", "仿制药一致性评价", "2025年报预增", "医疗器械概念"],
    "06-26": ["芯片概念", "专精特新", "商业航天", "储能", "光伏概念", "军工", "华为概念", "一带一路"],
    "06-25": ["芯片概念", "机器人概念", "锂电池概念", "新能源汽车", "华为概念", "数据中心", "储能", "军工"],
    "06-24": ["芯片概念", "新能源汽车", "华为概念", "5G", "比亚迪概念", "机器人概念", "数据中心", "专精特新"],
    "06-23": ["机器人概念", "新能源汽车", "锂电池概念", "股权转让/并购重组", "一带一路", "专精特新", "芯片概念", "创投"],
    "06-18": ["专精特新", "芯片概念", "比亚迪概念", "机器人概念", "新能源汽车", "华为概念", "军工", "5G"],
    "06-17": ["芯片概念", "新能源汽车", "华为概念", "锂电池概念", "储能", "消费电子概念", "PCB概念", "比亚迪概念"],
    "06-16": ["新能源汽车", "储能", "芯片概念", "数据中心", "华为概念", "机器人概念", "比亚迪概念", "5G"],
    "06-15": ["新能源汽车", "芯片概念", "华为概念", "5G", "储能", "数据中心", "一带一路", "锂电池概念"],
}

# Collect unique hot sector names
all_hot_sectors = set()
for sectors in daily_hot_sectors.values():
    for s in sectors:
        all_hot_sectors.add(s)
print(f"Unique hot sector names: {len(all_hot_sectors)}")

# Step 3: Map names to codes
sector_codes = {}
for name in all_hot_sectors:
    code = board_map.get(name)
    if code:
        sector_codes[name] = code
    else:
        print(f"WARNING: Cannot find board code for: {name}")

print(f"Matched sectors: {len(sector_codes)}")
for name, code in sector_codes.items():
    print(f"  {name} -> {code}")

# Step 4: Get constituent stocks for each hot sector
# Build a mapping: concept_name -> set of stock_codes
sector_stocks = {}
for concept_name, concept_code in sector_codes.items():
    try:
        cons = ak.stock_board_concept_cons_em(symbol=concept_code)
        codes = set()
        for _, row in cons.iterrows():
            code_str = str(row['代码']).strip()
            # Normalize to 6 digits
            code_str = code_str.zfill(6)
            codes.add(code_str)
        sector_stocks[concept_name] = codes
        print(f"  {concept_name}: {len(codes)} stocks")
    except Exception as e:
        print(f"  ERROR fetching {concept_name}: {e}")

# Step 5: Our stock pool for each day (top 20 per day)
# Only the top 20 stocks listed in the md file
daily_stocks = {
    "06-30": [
        ("300932", "三友联众"), ("603983", "丸美生物"), ("603956", "威派格"),
        ("688589", "力合微"), ("600576", "祥源文旅"), ("000017", "深中华A"),
        ("300474", "景嘉微"), ("301365", "矩阵股份"), ("001390", "古麒绒材"),
        ("002628", "成都路桥"), ("300024", "机器人"), ("001237", "惠康科技"),
        ("300959", "线上线下"), ("603726", "朗迪集团"), ("002693", "双成药业"),
        ("688011", "新光光电"), ("002653", "海思科"), ("300434", "金石亚药"),
        ("301191", "菲菱科思"), ("300948", "冠中生态"),
    ],
    "06-29": [
        ("600962", "国投中鲁"), ("000521", "长虹美菱"), ("001390", "古麒绒材"),
        ("000404", "长虹华意"), ("605296", "神农集团"), ("301393", "昊帆生物"),
        ("688193", "仁度生物"), ("603956", "威派格"), ("603903", "中持股份"),
        ("301328", "维峰电子"), ("002559", "亚威股份"), ("688117", "圣诺生物"),
        ("688758", "赛分科技"), ("603687", "大胜达"), ("688103", "国力电子"),
        ("688156", "路德科技"), ("920017", "星昊医药"), ("605098", "行动教育"),
        ("300024", "机器人"), ("301051", "信濠光电"),
    ],
    "06-26": [
        ("000034", "神州数码"), ("000620", "盈新发展"), ("000551", "创元科技"),
        ("000766", "通化金马"), ("000728", "国元证券"), ("000700", "模塑科技"),
    ],
    "06-25": [
        ("301376", "致欧科技"), ("603948", "建业股份"), ("688093", "世华科技"),
        ("300227", "光韵达"), ("300195", "长荣股份"), ("000766", "通化金马"),
        ("300717", "华信新材"), ("603898", "好莱客"), ("605303", "园林股份"),
        ("002452", "长高电气"), ("002025", "航天电器"), ("002821", "凯莱英"),
        ("301211", "亨迪药业"), ("301051", "信濠光电"), ("300506", "名家汇"),
        ("603698", "航天工程"), ("605178", "时空科技"), ("002635", "安洁科技"),
        ("600531", "豫光金铅"), ("605369", "拱东医疗"),
    ],
    "06-24": [
        ("000756", "新华制药"), ("301211", "亨迪药业"), ("300412", "迦南科技"),
        ("605369", "拱东医疗"), ("002452", "长高电气"), ("600379", "宝光股份"),
        ("600851", "海欣股份"), ("002687", "乔治白"), ("688755", "汉邦科技"),
        ("301592", "六九一二"), ("600171", "上海贝岭"), ("002191", "劲嘉股份"),
        ("301305", "朗坤科技"), ("002833", "弘亚数控"), ("002653", "海思科"),
        ("001206", "依依股份"), ("603339", "四方科技"), ("300961", "深水海纳"),
        ("000751", "锌业股份"), ("002549", "凯美特气"),
    ],
    "06-23": [
        ("688367", "工大高科"), ("688338", "赛科希德"), ("603339", "四方科技"),
        ("688105", "诺唯赞"), ("000751", "锌业股份"), ("688179", "阿拉丁"),
        ("603351", "威尔药业"), ("920017", "星昊医药"), ("603607", "京华激光"),
        ("688653", "康希通信"), ("000828", "东莞控股"), ("688291", "金橙子"),
        ("000571", "新大洲A"), ("920808", "曙光数创"), ("920799", "艾融软件"),
        ("920139", "华岭股份"), ("688222", "成都先导"), ("605305", "中际联合"),
        ("000686", "东北证券"), ("603386", "骏亚科技"),
    ],
    "06-18": [
        ("000679", "大连友谊"), ("688105", "诺唯赞"), ("688729", "屹唐股份"),
        ("688657", "浩辰软件"), ("603339", "四方科技"), ("688131", "皓元医药"),
        ("688448", "磁谷科技"), ("603316", "诚邦股份"), ("603665", "康隆达"),
        ("688333", "铂力特"), ("603880", "南卫股份"), ("603777", "来伊份"),
        ("603579", "荣泰健康"), ("603358", "华达科技"), ("688306", "均普智能"),
        ("688290", "景业智能"), ("603285", "键邦股份"), ("000050", "深天马A"),
        ("603950", "长源东谷"), ("603813", "原尚股份"),
    ],
    "06-17": [
        ("000777", "中核科技"), ("603271", "永杰新材"), ("000679", "大连友谊"),
        ("000012", "南玻A"), ("688358", "祥生医疗"), ("688286", "敏芯股份"),
        ("000695", "滨海能源"), ("688479", "友车科技"), ("688069", "德林海"),
        ("603407", "长裕集团"), ("000791", "甘肃能源"), ("603335", "迪生力"),
        ("603488", "展鹏科技"), ("603261", "立航科技"), ("605288", "凯迪股份"),
        ("605166", "聚合顺"), ("000032", "深桑达A"), ("603777", "来伊份"),
        ("000672", "上峰材料"), ("000539", "粤电力A"),
    ],
    "06-16": [
        ("300506", "名家汇"), ("603261", "立航科技"), ("002303", "美盈森"),
        ("603335", "迪生力"), ("301310", "鑫宏业"), ("601696", "中银证券"),
        ("300921", "南凌科技"), ("300931", "通用电梯"), ("688590", "新致软件"),
        ("603813", "原尚股份"), ("000922", "佳电股份"), ("002992", "宝明科技"),
        ("002972", "科安达"), ("603271", "永杰新材"), ("300066", "三川智慧"),
        ("301055", "张小泉"), ("300249", "依米康"), ("301178", "天亿马"),
        ("300214", "日科化学"), ("688237", "超卓航科"),
    ],
    "06-15": [
        ("603586", "金麒麟"), ("002529", "海源复材"), ("300005", "探路者"),
        ("301276", "嘉曼服饰"), ("300193", "佳士科技"), ("600576", "祥源文旅"),
        ("002215", "诺普信"), ("002849", "威星智能"), ("300375", "鹏翎股份"),
        ("601696", "中银证券"), ("301348", "蓝箭电子"), ("605298", "必得科技"),
        ("300853", "申昊科技"), ("688353", "华盛锂电"), ("301059", "金三江"),
        ("300093", "金刚光伏"), ("601021", "春秋航空"), ("000758", "中色股份"),
        ("300688", "创业黑马"), ("002768", "国恩股份"),
    ],
}

# Step 6: Match each day's stocks against that day's hot sectors
print("\n\n=== MATCHING RESULTS ===")
markdown_lines = []

for date_str in sorted(daily_stocks.keys()):
    hot_sectors_today = daily_hot_sectors.get(date_str, [])
    
    # Build combined set of all stocks in any hot sector that day
    hot_stock_set = set()
    stock_to_sectors = {}  # stock_code -> [sector_names]
    
    for sector_name in hot_sectors_today:
        stocks_in_sector = sector_stocks.get(sector_name, set())
        hot_stock_set.update(stocks_in_sector)
        for s_code in stocks_in_sector:
            if s_code not in stock_to_sectors:
                stock_to_sectors[s_code] = []
            stock_to_sectors[s_code].append(sector_name)
    
    print(f"\n--- {date_str} ---")
    print(f"Hot sectors: {', '.join(hot_sectors_today[:4])}...")
    
    for code, name in daily_stocks[date_str]:
        matched_sectors = stock_to_sectors.get(code, [])
        if matched_sectors:
            # Filter to only sectors that were hot THAT day
            relevant = [s for s in matched_sectors if s in hot_sectors_today]
            if relevant:
                print(f"  {code} {name}: YES ({', '.join(relevant[:3])})")
                markdown_lines.append((date_str, name, code, "是", "; ".join(relevant[:3])))
            else:
                print(f"  {code} {name}: 否 (only in non-hot: {', '.join(matched_sectors[:2])})")
                markdown_lines.append((date_str, name, code, "否", ""))
        else:
            print(f"  {code} {name}: 否")
            markdown_lines.append((date_str, name, code, "否", ""))

# Step 7: Output markdown table
print("\n\n=== MARKDOWN TABLE ===")
print("| 日期 | 股票 | 是否命中热点 | 匹配概念 |")
print("|------|------|-------------|---------|")
for date_str, name, code, hit, sectors in markdown_lines:
    sector_text = sectors if sectors else "-"
    print(f"| {date_str} | {name}({code}) | {hit} | {sector_text} |")
