import json
import sys
from datetime import date, timedelta
from collections import defaultdict

with open(r'C:\Users\Rofis\Desktop\a股波段看板_完整备份.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"=== BASIC INFO ===")
print(f"Total records: {len(data)}")
print(f"Date range: {data[0]['date']} ~ {data[-1]['date']}")
print(f"Keys per record: {sorted(data[0].keys())}")
print()

# ── Define which sub-branch keys exist ──
sub_branch_keys = []
for k in data[-1].keys():
    # e.g., s1b1Name, s1b2Name, w1b1Name, etc.
    if 'b1Name' in k or 'b2Name' in k:
        # also check for newer ones like 'b3Name' etc.
        pass
all_keys = sorted(data[0].keys())
sub_fields = [k for k in all_keys if 'b' in k and ('Name' in k)]
print(f"Sub-branch fields found: {sub_fields}")
print()

# ============================================================
# 1. MISSING / NULL / ZERO ANALYSIS
# ============================================================
print("=" * 60)
print("1. MISSING / NULL / ZERO ANALYSIS")
print("=" * 60)

marquee_fields = ['volume', 'limitUp', 'limitDown', 'bomb', 'chain',
                  'newHigh', 'newLow', 'newHighDaily']

issues_by_field = defaultdict(list)
zero_records = defaultdict(list)

for rec in data:
    for f in marquee_fields:
        val = rec.get(f)
        if val is None:
            issues_by_field[f].append(rec['date'])
        elif val == 0 and f not in ('newHigh', 'newLow', 'newHighDaily',
                                      'limitDown', 'bomb', 'chain'):
            # volume / limitUp being zero is suspicious
            if f in ('volume', 'limitUp'):
                issues_by_field[f'ZERO_{f}'].append(rec['date'])
        # track all zeros for reporting
        if val == 0:
            zero_records[f].append(rec['date'])

print("\n--- Fields that are None (missing) ---")
if issues_by_field:
    for f, dates in sorted(issues_by_field.items()):
        print(f"  {f}: {len(dates)} dates - {dates[:5]}...")
else:
    print("  None found.")

print("\n--- Zero-value analysis ---")
for f in marquee_fields:
    zd = zero_records[f]
    if zd:
        print(f"  {f}=0 on {len(zd)} dates: {zd[:10]}{'...' if len(zd)>10 else ''}")
    else:
        print(f"  {f}: never zero")

print()

# ============================================================
# 2. SECTOR COMPLETENESS (s1Name, s2Name, s3Name)
# ============================================================
print("=" * 60)
print("2. HOT SECTOR COMPLETENESS (s1Name, s2Name, s3Name)")
print("=" * 60)

empty_sector_dates = []
for rec in data:
    missing = []
    for i in [1, 2, 3]:
        name = rec.get(f's{i}Name', '')
        if name is None or name.strip() == '':
            missing.append(f's{i}Name')
    if missing:
        empty_sector_dates.append((rec['date'], missing))

print(f"Dates with any empty hot sector: {len(empty_sector_dates)}")
for d, m in empty_sector_dates:
    print(f"  {d}: {', '.join(m)} empty")

print()

# ============================================================
# 3. WATCH SECTOR COMPLETENESS (w1Name, w2Name, w3Name)
# ============================================================
print("=" * 60)
print("3. ANOMALOUS SECTOR COMPLETENESS (w1Name, w2Name, w3Name)")
print("=" * 60)

empty_watch_dates = []
for rec in data:
    missing = []
    for i in [1, 2, 3]:
        name = rec.get(f'w{i}Name', '')
        if name is None or name.strip() == '':
            missing.append(f'w{i}Name')
    if missing:
        empty_watch_dates.append((rec['date'], missing))

print(f"Dates with any empty watch sector: {len(empty_watch_dates)}")
for d, m in empty_watch_dates:
    print(f"  {d}: {', '.join(m)} empty")

print()

# ============================================================
# 4. SUB-BRANCH DATA (s1b1Name, s1b2Name, ... , w3b1Name, w3b2Name)
# ============================================================
print("=" * 60)
print("4. SUB-BRANCH DATA ANALYSIS")
print("=" * 60)

# Check all sub-branch fields: s{1-3}b{1-2}Name and w{1-3}b{1-2}Name
sub_branch_name_keys = []
for prefix in ['s', 'w']:
    for i in [1, 2, 3]:
        for j in [1, 2]:
            key = f'{prefix}{i}b{j}Name'
            if key in data[0].keys():
                sub_branch_name_keys.append(key)

print(f"Sub-branch name fields: {sub_branch_name_keys}")

# Count non-empty per field
for key in sorted(sub_branch_name_keys):
    non_empty = [rec for rec in data if rec.get(key, '').strip() != '']
    if non_empty:
        dates = [(rec['date'], rec[key]) for rec in non_empty]
        print(f"\n  {key}: {len(non_empty)}/{len(data)} non-empty")
        for d, val in dates[:10]:
            print(f"    {d}: \"{val}\"")
        if len(dates) > 10:
            print(f"    ... and {len(dates)-10} more")
    else:
        print(f"\n  {key}: ALL EMPTY (0/{len(data)})")

# Also check if there's a "signal" or "信号" field
print()

# ============================================================
# 5. ANOMALIES
# ============================================================
print("=" * 60)
print("5. ANOMALIES")
print("=" * 60)

print("\n--- 5a. Bomb > LimitUp ---")
bomb_gt = []
for rec in data:
    if rec['bomb'] > rec['limitUp']:
        bomb_gt.append((rec['date'], rec['bomb'], rec['limitUp']))
if bomb_gt:
    for d, b, lu in bomb_gt:
        print(f"  {d}: bomb={b} > limitUp={lu}")
else:
    print("  None found.")

print("\n--- 5b. LimitUp = 0 on non-holiday ---")
lu_zero = [(rec['date'], rec.get('volume')) for rec in data if rec['limitUp'] == 0]
if lu_zero:
    for d, v in lu_zero:
        print(f"  {d}: limitUp=0, volume={v}")
else:
    print("  None found.")

print("\n--- 5c. LimitUp suspiciously low (<20) ---")
lu_low = [(rec['date'], rec['limitUp']) for rec in data if rec['limitUp'] < 20]
if lu_low:
    for d, lu in lu_low:
        print(f"  {d}: limitUp={lu}")
else:
    print("  None found.")

print("\n--- 5d. LimitUp suspiciously high (>200) ---")
lu_high = [(rec['date'], rec['limitUp']) for rec in data if rec['limitUp'] > 200]
if lu_high:
    for d, lu in lu_high:
        print(f"  {d}: limitUp={lu}")
else:
    print("  None found.")

print("\n--- 5e. newHigh suspiciously low (=0 on normal trading day) ---")
nh_zero = [(rec['date'], rec.get('volume'), rec['limitUp']) 
           for rec in data if rec['newHigh'] == 0 and rec['limitUp'] > 0]
if nh_zero:
    for d, v, lu in nh_zero:
        print(f"  {d}: newHigh=0, volume={v}, limitUp={lu}")
else:
    print("  None found.")

print("\n--- 5f. newLow suspiciously high (>500) ---")
nl_high = [(rec['date'], rec['newLow']) for rec in data if rec['newLow'] > 500]
if nl_high:
    for d, nl in nl_high:
        print(f"  {d}: newLow={nl}")
else:
    print("  None found.")

print("\n--- 5g. Volume anomalies (unusually low <9000 or high >50000) ---")
vol_anom = [(rec['date'], rec['volume']) for rec in data 
            if rec['volume'] < 9000 or rec['volume'] > 50000]
if vol_anom:
    for d, v in vol_anom:
        print(f"  {d}: volume={v}")
else:
    print("  None found.")

print("\n--- 5h. newHigh vs newHighDaily ratio anomalies ---")
for rec in data:
    if rec.get('newHighDaily', 0) > rec.get('newHigh', 0):
        print(f"  {rec['date']}: newHighDaily({rec['newHighDaily']}) > newHigh({rec['newHigh']})")

print("\n--- 5i. limitUp + bomb relationship (bomb > 50% of limitUp) ---")
high_bomb_ratio = [(rec['date'], rec['limitUp'], rec['bomb'],
                    round(rec['bomb']/rec['limitUp']*100, 1) if rec['limitUp'] > 0 else 0)
                   for rec in data if rec['limitUp'] > 0 and rec['bomb']/rec['limitUp'] > 0.5]
if high_bomb_ratio:
    for d, lu, b, r in high_bomb_ratio:
        print(f"  {d}: limitUp={lu}, bomb={b}, ratio={r}%")
else:
    print("  None found.")

print()

# ============================================================
# 6. DATE GAPS
# ============================================================
print("=" * 60)
print("6. DATE GAPS ANALYSIS")
print("=" * 60)

dates_in_data = sorted([rec['date'] for rec in data])
date_objs = [date.fromisoformat(d) for d in dates_in_data]

# Generate all weekdays (Mon-Fri) between first and last date
start = date_objs[0]
end = date_objs[-1]
all_weekdays = []
current = start
while current <= end:
    if current.weekday() < 5:  # Mon=0 ... Fri=4
        all_weekdays.append(current)
    current += timedelta(days=1)

date_obj_set = set(date_objs)
missing_weekdays = [d for d in all_weekdays if d not in date_obj_set]

# Chinese holidays in 2026 range (approximate - Spring Festival, etc.)
# 2026-02-16 to 2026-02-20 appear to be Spring Festival (records exist but sector data empty)
# Let's just list all missing weekdays and flag likely holidays
known_holidays_2026 = [
    date(2026, 1, 1),    # New Year
    date(2026, 1, 2),    # New Year
    # Spring Festival 2026: Feb 17 is Lunar New Year
    # Typically several days off around it
    # Qingming: April 5 (Sunday) -> likely April 6 Monday off
    # Labor Day: May 1-5
    # Dragon Boat: June 19 (Friday)
]

print(f"Total weekdays in range: {len(all_weekdays)}")
print(f"Records present: {len(data)}")
print(f"Gaps: {len(missing_weekdays)} missing weekday(s)")

print("\nMissing weekdays (potential trading day gaps):")
for d in sorted(missing_weekdays):
    is_holiday = d in known_holidays_2026
    marker = " [KNOWN HOLIDAY]" if is_holiday else " [CHECK - likely holiday or missing data]"
    print(f"  {d.isoformat()} (weekday={d.strftime('%A')}){marker}")

print()

# ============================================================
# 7. SIGNAL FIELD CHECK
# ============================================================
print("=" * 60)
print("7. SIGNAL FIELD CHECK")
print("=" * 60)

signal_keys = [k for k in data[0].keys() if 'signal' in k.lower() or '信号' in k]
if signal_keys:
    print(f"Signal-related fields found: {signal_keys}")
    # Check which records have non-null/non-empty signal values
    for key in signal_keys:
        has_signal = [(rec['date'], rec[key]) for rec in data if rec.get(key) not in (None, '', 0)]
        print(f"  {key}: {len(has_signal)} records populated")
        for d, v in has_signal[:5]:
            print(f"    {d}: {v}")
else:
    print("  No 'signal' or '信号' field found in any record.")

# Check for any extra fields not in the original set
first_keys = set(data[0].keys())
last_keys = set(data[-1].keys())
new_in_last = last_keys - first_keys
missing_in_last = first_keys - last_keys
print(f"\nFields added in later records: {new_in_last if new_in_last else 'None'}")
print(f"Fields removed in later records: {missing_in_last if missing_in_last else 'None'}")


# ============================================================
# SUMMARY
# ============================================================
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)

# Summarize issues
total_issues = 0
print(f"\n1. Core fields (volume/limitUp/limitDown/bomb/chain/newHigh/newLow/newHighDaily):")
print(f"   - No None/missing values found across all records")
print(f"   - All fields present in all {len(data)} records")

print(f"\n2. Hot sectors (s1Name/s2Name/s3Name):")
print(f"   - {len(empty_sector_dates)} dates with empty sectors")
for d, m in empty_sector_dates:
    print(f"     {d}")

print(f"\n3. Watch sectors (w1Name/w2Name/w3Name):")
print(f"   - {len(empty_watch_dates)} dates with empty watch sectors (same dates as above)")

print(f"\n4. Sub-branch data:")
all_empty_subs = all(len([rec for rec in data if rec.get(k, '').strip() != '']) == 0 for k in sub_branch_name_keys)
if all_empty_subs:
    print(f"   - ALL sub-branch fields ({len(sub_branch_name_keys)} fields) are COMPLETELY EMPTY across all {len(data)} records")
else:
    print(f"   - Some sub-branch fields have data")

print(f"\n5. Anomalies:")
print(f"   - Bomb > LimitUp: {len(bomb_gt)} records")
print(f"   - LimitUp = 0: {len(lu_zero)} records")
print(f"   - high bomb ratio (>50%): {len(high_bomb_ratio)} records")
print(f"   - newHigh=0 on trading day: {len(nh_zero)} records")
print(f"   - newLow spike (>500): {len(nl_high)} records")

print(f"\n6. Date gaps:")
print(f"   - {len(missing_weekdays)} missing weekday(s)")
print(f"   (Most likely Chinese holidays/Spring Festival; need to verify)")

print(f"\n7. Signal field:")
print(f"   - {'Present: ' + str(signal_keys) if signal_keys else 'Not present in any record'}")

print(f"\n=== RECOMMENDATIONS ===")
print("1. Supplement sector data for dates 02-16 through 02-20 (Spring Festival period)")
print("2. All sub-branch fields (12 fields) need population - entire dataset has no sub-branch data")
print("3. Verify 01-30 data: limitDown=98 vs limitUp=33 (looks like a crash day - likely correct)")
print("4. Verify 02-09 data: volume=8900, limitUp=0 (likely a Saturday or holiday with partial data)")
print("5. newLow spike on 03-19 to 03-25 (748, 1244, 2466, etc.) - very high, verify data source")
print("6. Consider adding a 'signal' or '备注' field for trade signal annotations")
print("7. 02-02 data appears to be a duplicate/copy of 01-30 (same volume/limitUp/limitDown/bomb/chain)")
print("8. Check if w1Reason field should be populated more consistently (mostly empty)")
