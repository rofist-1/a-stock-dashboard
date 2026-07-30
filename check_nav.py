import json
with open('results/result_B_full.json', encoding='utf-8') as f:
    d = json.load(f)
print("Keys:", list(d.keys()))
print("NAV len:", len(d.get('nav', [])))
print("NAV[:3]:", d.get('nav', [])[:3])
print("NAV[-3:]:", d.get('nav', [])[-3:])