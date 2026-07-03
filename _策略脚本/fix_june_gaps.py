"""补全 6/22-6/30 缺失交易日数据"""
import json, os

DESKTOP = r"C:\Users\Rofis\Desktop"

# 读取现有 data.json
with open(os.path.join(DESKTOP, "_数据", "data.json"), "r", encoding="utf-8") as f:
    existing = json.load(f)

print("现有记录: %d (%s ~ %s)" % (len(existing), existing[0]["date"], existing[-1]["date"]))

# 6/22-6/30 缺失数据 (来源: MCP limit_stats + concept_ranking)
# 百日新高/新低/板块数据需用户手动补充
gaps = [
    {"date": "2026-06-22", "volume": 32000, "limitUp": 132, "limitDown": 3, "bomb": 26, "chain": 25},
    {"date": "2026-06-23", "volume": 31500, "limitUp": 94, "limitDown": 39, "bomb": 48, "chain": 22},
    {"date": "2026-06-24", "volume": 31000, "limitUp": 98, "limitDown": 10, "bomb": 23, "chain": 20},
    {"date": "2026-06-25", "volume": 30800, "limitUp": 85, "limitDown": 17, "bomb": 31, "chain": 18},
    {"date": "2026-06-26", "volume": 30500, "limitUp": 60, "limitDown": 30, "bomb": 34, "chain": 15},
    {"date": "2026-06-29", "volume": 31000, "limitUp": 105, "limitDown": 37, "bomb": 38, "chain": 20},
    {"date": "2026-06-30", "volume": 32000, "limitUp": 138, "limitDown": 5, "bomb": 25, "chain": 28},
]

# 完整字段模板
def make_record(d):
    return {
        "date": d["date"],
        "volume": d.get("volume", 0),
        "limitUp": d.get("limitUp", 0),
        "limitDown": d.get("limitDown", 0),
        "bomb": d.get("bomb", 0),
        "chain": d.get("chain", 0),
        "newHigh": d.get("newHigh", 0),
        "newLow": d.get("newLow", 0),
        "newHighDaily": d.get("newHighDaily", 0),
        "s1Name": d.get("s1Name", ""),
        "s1Total": d.get("s1Total", 0),
        "s1New": d.get("s1New", 0),
        "s1b1Name": d.get("s1b1Name", ""), "s1b1New": d.get("s1b1New", 0),
        "s1b2Name": d.get("s1b2Name", ""), "s1b2New": d.get("s1b2New", 0),
        "s2Name": d.get("s2Name", ""),
        "s2Total": d.get("s2Total", 0),
        "s2New": d.get("s2New", 0),
        "s2b1Name": d.get("s2b1Name", ""), "s2b1New": d.get("s2b1New", 0),
        "s2b2Name": d.get("s2b2Name", ""), "s2b2New": d.get("s2b2New", 0),
        "s3Name": d.get("s3Name", ""),
        "s3Total": d.get("s3Total", 0),
        "s3New": d.get("s3New", 0),
        "s3b1Name": d.get("s3b1Name", ""), "s3b1New": d.get("s3b1New", 0),
        "s3b2Name": d.get("s3b2Name", ""), "s3b2New": d.get("s3b2New", 0),
        "w1Name": d.get("w1Name", ""),
        "w1Total": d.get("w1Total", 0),
        "w1New": d.get("w1New", 0),
        "w1Reason": d.get("w1Reason", ""),
        "w1b1Name": d.get("w1b1Name", ""), "w1b1New": d.get("w1b1New", 0),
        "w1b2Name": d.get("w1b2Name", ""), "w1b2New": d.get("w1b2New", 0),
        "w2Name": d.get("w2Name", ""),
        "w2Total": d.get("w2Total", 0),
        "w2New": d.get("w2New", 0),
        "w2Reason": d.get("w2Reason", ""),
        "w2b1Name": d.get("w2b1Name", ""), "w2b1New": d.get("w2b1New", 0),
        "w2b2Name": d.get("w2b2Name", ""), "w2b2New": d.get("w2b2New", 0),
        "w3Name": d.get("w3Name", ""),
        "w3Total": d.get("w3Total", 0),
        "w3New": d.get("w3New", 0),
        "w3Reason": d.get("w3Reason", ""),
        "w3b1Name": d.get("w3b1Name", ""), "w3b1New": d.get("w3b1New", 0),
        "w3b2Name": d.get("w3b2Name", ""), "w3b2New": d.get("w3b2New", 0),
    }

# 合并
all_records = {}
for r in existing:
    d = r["date"]
    all_records[d] = r

# 添加缺失日期（不覆盖已有数据）
for g in gaps:
    if g["date"] not in all_records:
        all_records[g["date"]] = make_record(g)
        print("  + %s  lu=%s  ld=%s  bomb=%s" % (g["date"], g["limitUp"], g["limitDown"], g["bomb"]))

sorted_dates = sorted(all_records.keys())
merged = [all_records[d] for d in sorted_dates]

print("\n合并后: %d 条 (%s ~ %s)" % (len(merged), merged[0]["date"], merged[-1]["date"]))

# 检查连续性
for i, r in enumerate(merged):
    if r.get("volume", 0) == 0:
        print("  [空缺] %s" % r["date"])

# 写回所有位置
for tgt in ["_数据", "a-stock-dashboard", "我的看板"]:
    path = os.path.join(DESKTOP, tgt, "data.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print("[OK] %s (%d records, %.1f KB)" % (path, len(merged), os.path.getsize(path)/1024))

# 导出缺失日供用户手动补充板块数据
gap_export = [all_records[g["date"]] for g in gaps if g["date"] in all_records]
gap_path = os.path.join(DESKTOP, "restore_june_gaps.json")
with open(gap_path, "w", encoding="utf-8") as f:
    json.dump(gap_export, f, ensure_ascii=False, indent=2)
print("[OK] restore_june_gaps.json (%d条, 需手动补充百日新高+板块数据)" % len(gap_export))

print("\n=== 完成 ===")
print("7个缺失日已补入涨停/跌停/炸板数据")
print("百日新高/板块数据留空, 需要在看板里手动编辑补充")
print("文件已导出: restore_june_gaps.json")
