import akshare as ak
import time

# Get board list first
boards = ak.stock_board_industry_name_ths()
print(f"THS boards: {len(boards)}")
# Print first 10
for _, row in boards.head(10).iterrows():
    print(f"  {row['code']}: {row['name']}")

# Now try getting constituents for one board (半导体 = 881121)
time.sleep(1)
try:
    df = ak.stock_board_industry_cons_ths(symbol="881121")
    print(f"\n半导体 constituents: {len(df)}")
    print(df.head(10))
except Exception as e:
    print(f"THS cons failed: {e}")
