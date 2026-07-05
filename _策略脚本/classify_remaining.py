# -*- coding: utf-8 -*-
import json

with open("C:/Users/Rofis/Desktop/sector_map.json", "r", encoding="utf-8") as f:
    sector_map = json.load(f)

with open("C:/Users/Rofis/Desktop/百日新高_20260605.json", "r", encoding="utf-8") as f:
    nh = json.load(f)

missing = [s for s in nh["stocks"] if s["sector"] == "其他"]
mapped = [s for s in nh["stocks"] if s["sector"] != "其他"]
print(f"Total new highs: {len(nh['stocks'])}")
print(f"Mapped: {len(mapped)}, Missing: {len(missing)}")

for s in missing:
    code = s["code"].split(".")[0]
    name = s["name"]
    status = "IN MAP" if code in sector_map else "NOT IN MAP"
    print(f"  {code} {name[:4]} -> {status}")
