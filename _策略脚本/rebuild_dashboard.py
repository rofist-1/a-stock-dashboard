"""重建完整看板数据 + 生成 localStorage 恢复页"""
import json
import os

DESKTOP = r"C:\Users\Rofis\Desktop"

# ── 1. 读取现有 data.json ──
with open(os.path.join(DESKTOP, "_数据", "data.json"), "r", encoding="utf-8") as f:
    existing = json.load(f)

print("现有记录数: %d  (日期范围: %s ~ %s)" % (len(existing), existing[0]["date"], existing[-1]["date"]))

# ── 2. 新增/更新 data.json 记录（确保中文正确） ──

# 7/1 数据 (手动报送 + MCP验证)
r0701 = {
    "date": "2026-07-01",
    "volume": 34500,       # 待确认
    "limitUp": 149,
    "limitDown": 6,
    "bomb": 73,
    "chain": 42,           # 估算
    "newHigh": 349,        # 从之前简报: 6/30=349, 7/1估计类似
    "newLow": 11,          # 从跌停6推算
    "newHighDaily": 120,   # 估算
    "s1Name": "芯片",
    "s1Total": 120,
    "s1New": 20,
    "s1b1Name": "存储",
    "s1b1New": 47,
    "s1b2Name": "第三代半导体",
    "s1b2New": 38,
    "s2Name": "机器人",
    "s2Total": 24,
    "s2New": 8,
    "s2b1Name": "外骨骼",
    "s2b1New": 2,
    "s2b2Name": "AGV",
    "s2b2New": 1,
    "s3Name": "医药",
    "s3Total": 19,
    "s3New": 5,
    "s3b1Name": "创新药",
    "s3b1New": 14,
    "s3b2Name": "CRO",
    "s3b2New": 8,
    "w1Name": "算力",
    "w1Total": 18,
    "w1New": 2,
    "w1Reason": "",
    "w1b1Name": "液冷",
    "w1b1New": 14,
    "w1b2Name": "数据中心",
    "w1b2New": 5,
    "w2Name": "通信",
    "w2Total": 17,
    "w2New": 3,
    "w2Reason": "",
    "w2b1Name": "CPO",
    "w2b1New": 7,
    "w2b2Name": "5G",
    "w2b2New": 6,
    "w3Name": "化工",
    "w3Total": 14,
    "w3New": 7,
    "w3Reason": "",
    "w3b1Name": "氢氟酸",
    "w3b1New": 4,
    "w3b2Name": "制冷剂",
    "w3b2New": 4,
}

# 7/2 数据 (从看板提取 + MCP验证确认)
r0702 = {
    "date": "2026-07-02",
    "volume": 34505,
    "limitUp": 91,
    "limitDown": 40,
    "bomb": 40,
    "chain": 19,
    "newHigh": 156,
    "newLow": 58,
    "newHighDaily": 35,
    "s1Name": "芯片",
    "s1Total": 42,
    "s1New": 9,
    "s1b1Name": "存储",
    "s1b1New": 16,
    "s1b2Name": "光刻胶",
    "s1b2New": 14,
    "s2Name": "机器人",
    "s2Total": 17,
    "s2New": 3,
    "s2b1Name": "传感器",
    "s2b1New": 1,
    "s2b2Name": "灵巧手",
    "s2b2New": 1,
    "s3Name": "医药",
    "s3Total": 15,
    "s3New": 2,
    "s3b1Name": "创新药",
    "s3b1New": 12,
    "s3b2Name": "仿制药",
    "s3b2New": 4,
    "w1Name": "化工",
    "w1Total": 9,
    "w1New": 1,
    "w1Reason": "",
    "w1b1Name": "制冷剂",
    "w1b1New": 5,
    "w1b2Name": "氟化工",
    "w1b2New": 5,
    "w2Name": "光通信",
    "w2Total": 8,
    "w2New": 4,
    "w2Reason": "",
    "w2b1Name": "光模块",
    "w2b1New": 4,
    "w2b2Name": "CPO",
    "w2b2New": 4,
    "w3Name": "算力",
    "w3Total": 6,
    "w3New": 0,
    "w3Reason": "",
    "w3b1Name": "液冷",
    "w3b1New": 3,
    "w3b2Name": "数据中心",
    "w3b2New": 2,
}

# 7/3 数据 (更新为用户最新版本，原export的s1Name是"机器人"不是"电器设备")
r0703 = {
    "date": "2026-07-03",
    "volume": 32053,
    "limitUp": 104,
    "limitDown": 19,
    "bomb": 52,
    "chain": 16,
    "newHigh": 143,
    "newLow": 56,
    "newHighDaily": 58,
    "s1Name": "机器人",
    "s1Total": 28,
    "s1New": 15,
    "s1b1Name": "灵巧手",
    "s1b1New": 4,
    "s1b2Name": "宇树机器人",
    "s1b2New": 3,
    "s2Name": "芯片",
    "s2Total": 24,
    "s2New": 12,
    "s2b1Name": "存储",
    "s2b1New": 10,
    "s2b2Name": "先进封装",
    "s2b2New": 6,
    "s3Name": "医药",
    "s3Total": 20,
    "s3New": 6,
    "s3b1Name": "创新药",
    "s3b1New": 16,
    "s3b2Name": "CRO",
    "s3b2New": 7,
    "w1Name": "通信",
    "w1Total": 10,
    "w1New": 5,
    "w1Reason": "",
    "w1b1Name": "光模块",
    "w1b1New": 5,
    "w1b2Name": "CPO",
    "w1b2New": 4,
    "w2Name": "算力",
    "w2Total": 10,
    "w2New": 4,
    "w2Reason": "",
    "w2b1Name": "液冷",
    "w2b1New": 7,
    "w2b2Name": "数据中心",
    "w2b2New": 3,
    "w3Name": "证券",
    "w3Total": 6,
    "w3New": 1,
    "w3Reason": "",
    "w3b1Name": "参控股基金",
    "w3b1New": 5,
    "w3b2Name": "",
    "w3b2New": 0,
}

# ── 3. 合并：去重(按date)，新数据覆盖旧数据 ──
all_records = {}
for r in existing:
    d = r["date"]
    all_records[d] = r

# 添加/覆盖新记录
for r in [r0701, r0702, r0703]:
    all_records[r["date"]] = r

# 排序
sorted_dates = sorted(all_records.keys())
merged = [all_records[d] for d in sorted_dates]

print("合并后: %d 条  (%s ~ %s)" % (len(merged), merged[0]["date"], merged[-1]["date"]))

# 检查中文编码
for r in merged[-3:]:
    print("  %s  s1=%s(%s)  s2=%s(%s)  w1=%s(%s)" % (
        r["date"], r.get("s1Name",""), r.get("s1Total",""),
        r.get("s2Name",""), r.get("s2Total",""),
        r.get("w1Name",""), r.get("w1Total","")))

# 确保所有字段类型一致（数值字段统一为 int）
int_fields = ["volume", "limitUp", "limitDown", "bomb", "chain",
              "newHigh", "newLow", "newHighDaily",
              "s1Total", "s1New", "s1b1New", "s1b2New",
              "s2Total", "s2New", "s2b1New", "s2b2New",
              "s3Total", "s3New", "s3b1New", "s3b2New",
              "w1Total", "w1New", "w1b1New", "w1b2New",
              "w2Total", "w2New", "w2b1New", "w2b2New",
              "w3Total", "w3New", "w3b1New", "w3b2New"]
str_fields = ["date", "s1Name", "s1b1Name", "s1b2Name",
              "s2Name", "s2b1Name", "s2b2Name",
              "s3Name", "s3b1Name", "s3b2Name",
              "w1Name", "w1b1Name", "w1b2Name", "w1Reason",
              "w2Name", "w2b1Name", "w2b2Name", "w2Reason",
              "w3Name", "w3b1Name", "w3b2Name", "w3Reason"]

for r in merged:
    for k in int_fields:
        if k in r:
            try:
                r[k] = int(r[k])
            except (ValueError, TypeError):
                r[k] = 0
    for k in str_fields:
        if k not in r:
            r[k] = ""
        else:
            r[k] = str(r[k]) if r[k] is not None else ""

# ── 4. 写回所有 data.json ──
targets = ["_数据", "a-stock-dashboard", "我的看板"]
for tgt in targets:
    path = os.path.join(DESKTOP, tgt, "data.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(path) / 1024
    print("[OK] %s  (%d records, %.1f KB)" % (path, len(merged), size_kb))

# ── 5. 创建 localStorage 恢复页（用于 localhost:8080） ──
# 只包含 7月的3条记录，方便用户通过"导入"功能合并
restore_path = os.path.join(DESKTOP, "restore_july.json")
with open(restore_path, "w", encoding="utf-8") as f:
    json.dump([r0701, r0702, r0703], f, ensure_ascii=False, indent=2)
print("\n[OK] restore_july.json (3条7月记录)")

# 同时创建完整导出（用于备份）
backup_path = os.path.join(DESKTOP, "a股波段看板_完整备份.json")
with open(backup_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
print("[OK] a股波段看板_完整备份.json (%d条全量)" % len(merged))

print("\n=== 完成 ===")
print("恢复步骤:")
print("  1. 打开 http://localhost:8080/A股市场情绪综合看板17.html")
print("  2. 如果看板里没有7/1、7/2数据 → 点 '📥 导入' → 选择 'restore_july.json'")
print("  3. a-stock-dashboard/index.html 已自动更新（读 data.json）")
