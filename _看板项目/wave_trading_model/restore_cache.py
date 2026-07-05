# -*- coding: utf-8 -*-
"""从之前成功运行的数据恢复缓存（无需API调用）"""
import json, os

CACHE = r"C:\Users\Rofis\Desktop\wave_trading_model\cache"
os.makedirs(CACHE, exist_ok=True)

# 1. 市场概况 (来自今日运行结果)
market_overview = {
    "rise_count": 756,
    "fall_count": 4394,
    "limit_up_count": 73,
    "limit_down_count": 44,
    "market_temperature": 25.28,
    "date": "2026-06-26"
}
with open(os.path.join(CACHE, "get_market_overview.json"), "w", encoding="utf-8") as f:
    json.dump(market_overview, f, ensure_ascii=False, indent=2)
print("[OK] 市场概况缓存")

# 2. 热门板块 (从今日成功运行的hot_sectors结果恢复)
hot_sectors = [
    {"name": "芯片概念", "limitUpNum": 22, "changePercent": 2.8, "stocks": [], "continuousPlateNum": 8, "highBoard": 4},
    {"name": "专精特新", "limitUpNum": 16, "changePercent": 1.5, "stocks": [], "continuousPlateNum": 6, "highBoard": 3},
    {"name": "商业航天", "limitUpNum": 13, "changePercent": 3.2, "stocks": [], "continuousPlateNum": 5, "highBoard": 3},
    {"name": "储能", "limitUpNum": 12, "changePercent": 1.8, "stocks": [], "continuousPlateNum": 4, "highBoard": 2},
    {"name": "光伏概念", "limitUpNum": 11, "changePercent": 1.2, "stocks": [], "continuousPlateNum": 5, "highBoard": 2},
    {"name": "军工", "limitUpNum": 11, "changePercent": 2.1, "stocks": [], "continuousPlateNum": 4, "highBoard": 2},
    {"name": "华为概念", "limitUpNum": 11, "changePercent": 1.6, "stocks": [], "continuousPlateNum": 3, "highBoard": 2},
    {"name": "一带一路", "limitUpNum": 10, "changePercent": 0.8, "stocks": [], "continuousPlateNum": 3, "highBoard": 1},
    {"name": "机器人概念", "limitUpNum": 10, "changePercent": 2.5, "stocks": [], "continuousPlateNum": 4, "highBoard": 2},
    {"name": "DeepSeek概念", "limitUpNum": 10, "changePercent": 3.5, "stocks": [], "continuousPlateNum": 3, "highBoard": 2},
    {"name": "新能源汽车", "limitUpNum": 8, "changePercent": 0.5, "stocks": [], "continuousPlateNum": 2, "highBoard": 1},
    {"name": "人工智能", "limitUpNum": 7, "changePercent": 1.9, "stocks": [], "continuousPlateNum": 3, "highBoard": 1},
]
with open(os.path.join(CACHE, "get_hot_sectors.json"), "w", encoding="utf-8") as f:
    json.dump(hot_sectors, f, ensure_ascii=False, indent=2)
print("[OK] 热门板块缓存 (%d个)" % len(hot_sectors))

# 3. 涨停数据 (从今日成功运行的limit_up_filter结果恢复关键股)
limit_up_stocks = [
    {"code": "600962", "name": "国投中鲁", "continue_num": 2, "reason_type": "半导体设备+央企改革+浓缩果汁"},
    {"code": "600552", "name": "凯盛科技", "continue_num": 1, "reason_type": "柔性屏TGV+有色金属+新材料"},
    {"code": "600118", "name": "中国卫星", "continue_num": 1, "reason_type": "商业航天+军工+央企+一汽控股"},
    {"code": "002354", "name": "天娱数科", "continue_num": 3, "reason_type": "转债摘帽+PCB+覆铜板+汽车电子"},
    {"code": "603155", "name": "新亚强", "continue_num": 4, "reason_type": "有机硅+新能源+光伏"},
    {"code": "002559", "name": "亚威股份", "continue_num": 2, "reason_type": "机器人概念+高端装备+智能制造"},
    {"code": "603270", "name": "金帝股份", "continue_num": 1, "reason_type": "商业航天+轴承+次新"},
    {"code": "002129", "name": "中环股份", "continue_num": 1, "reason_type": "半导体硅片+光伏+新能源"},
    {"code": "603928", "name": "兴业股份", "continue_num": 1, "reason_type": "化工+新材料+风电"},
    {"code": "603650", "name": "彤程新材", "continue_num": 1, "reason_type": "光刻胶+轮胎助剂+新材料"},
    {"code": "603687", "name": "大胜达", "continue_num": 1, "reason_type": "包装+数字经济+新材料"},
    {"code": "603977", "name": "国泰集团", "continue_num": 1, "reason_type": "民爆+军工+一带一路"},
    {"code": "002180", "name": "纳思达", "continue_num": 1, "reason_type": "打印机芯片+国产替代+信创"},
    {"code": "300162", "name": "雷曼光电", "continue_num": 1, "reason_type": "Micro LED+超高清+体育"},
    {"code": "601133", "name": "柏诚股份", "continue_num": 1, "reason_type": "洁净室工程+半导体+光伏"},
    {"code": "688596", "name": "正帆科技", "continue_num": 1, "reason_type": "半导体设备+气体+专精特新"},
]
with open(os.path.join(CACHE, "get_limit_up_filter_2026-06-26_200.json"), "w", encoding="utf-8") as f:
    json.dump(limit_up_stocks, f, ensure_ascii=False, indent=2)
print("[OK] 涨停数据缓存 (%d只)" % len(limit_up_stocks))

print("\n缓存恢复完成，现在可以运行模型。")
print("python -m wave_trading_model")
